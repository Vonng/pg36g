#!/usr/bin/env python3
"""Capture a secret-free, read-only chapter 19 acceptance bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PORTS = (5432, 5433, 5434, 5436, 5438, 8008)


class CaptureError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    args: list[str],
    *,
    stdin: str | None = None,
    timeout: int = 60,
) -> str:
    try:
        result = subprocess.run(
            args,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaptureError(f"cannot execute {args[0]}: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else f"exit {result.returncode}"
        raise CaptureError(f"command failed ({args[0]}): {detail}")
    return result.stdout.strip()


def ssh_base(user: str, host: str) -> list[str]:
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=no",
        f"{user}@{host}",
    ]


def capture_host(
    source_dir: Path,
    output: Path,
    user: str,
    host: str,
) -> dict[str, Any]:
    script = (source_dir / "remote_host_facts.py").read_text(encoding="utf-8")
    raw = run(
        ssh_base(user, host)
        + ["python3", "-", "--target-ip", host],
        stdin=script,
    )
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"host {host} returned invalid JSON: {exc}") from exc
    write_json(output / "hosts" / f"{host}.json", facts)
    return facts


def capture_postgresql(
    source_dir: Path,
    output: Path,
    user: str,
    host: str,
) -> dict[str, Any]:
    sql = (source_dir / "postgresql-facts.sql").read_text(encoding="utf-8")
    raw = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "psql",
            "-X",
            "-qAt",
            "--dbname=postgres",
            "--set=ON_ERROR_STOP=1",
        ],
        stdin=sql,
    )
    try:
        facts = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"PostgreSQL on {host} returned invalid JSON: {exc}") from exc
    facts["target_ip"] = host
    write_json(output / "postgres" / f"{host}.json", facts)
    return facts


def normalize_patroni_rows(cluster: str, rows: Any) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise CaptureError(f"Patroni {cluster} result must be a list")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise CaptureError(f"Patroni {cluster} row must be an object")
        lower = {str(key).lower().replace(" ", "_"): value for key, value in row.items()}
        normalized.append(
            {
                "member": lower.get("member"),
                "host": lower.get("host"),
                "role": lower.get("role"),
                "state": lower.get("state"),
                "timeline": lower.get("tl", lower.get("timeline")),
                "lag_mb": lower.get("lag_in_mb", lower.get("lag")),
            }
        )
    normalized.sort(key=lambda row: (str(row["host"]), str(row["member"])))
    return {
        "schema": "pg36-ch19-patroni-facts-v1",
        "cluster": cluster,
        "members": normalized,
    }


def capture_patroni(
    output: Path,
    user: str,
    host: str,
    cluster: str,
) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "list",
            cluster,
            "--format=json",
        ],
    )
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"Patroni {cluster} returned invalid JSON: {exc}") from exc
    facts = normalize_patroni_rows(cluster, rows)
    write_json(output / "patroni" / f"{cluster}.json", facts)
    return facts


def tcp_probe(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def patroni_rest_probe(host: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"http://{host}:8008/", timeout=2) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        # Patroni deliberately uses non-2xx status codes on some health
        # endpoints to distinguish primary from replica.  An HTTP response
        # with a valid Patroni JSON body is still reachable identity evidence.
        status = error.code
        body = error.read()
    except (OSError, urllib.error.URLError):
        return {"reachable": False}
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"reachable": False, "http_status": status}
    if not isinstance(value, dict):
        return {"reachable": False, "http_status": status}
    return {
        "reachable": True,
        "http_status": status,
        "state": value.get("state"),
        "role": value.get("role"),
        "server_version": value.get("server_version"),
        "timeline": value.get("timeline"),
    }


def capture_endpoints(output: Path, hosts: list[str]) -> dict[str, Any]:
    result = {
        "schema": "pg36-ch19-endpoint-probes-v1",
        "hosts": {
            host: {
                "tcp": {
                    str(port): tcp_probe(host, port)
                    for port in DEFAULT_PORTS
                },
                "patroni": patroni_rest_probe(host),
            }
            for host in hosts
        },
        "interpretation": (
            "reachability and Patroni identity only; routing, pooling, "
            "failover, and saturation semantics belong to chapter 22"
        ),
    }
    write_json(output / "endpoints.json", result)
    return result


def project_inventory(
    source_dir: Path,
    inventory: Path,
    output: Path,
) -> dict[str, Any]:
    target = output / "inventory-projection.json"
    run(
        [
            sys.executable,
            str(source_dir / "inventory_projection.py"),
            str(inventory),
            "--output",
            str(target),
        ]
    )
    return read_json(target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        hosts = [
            str(member["address"])
            for unit in requirements["service_units"]
            for member in unit["members"]
        ]
        if len(hosts) != len(set(hosts)):
            raise CaptureError("requirements contain duplicate host addresses")

        args.output.mkdir(parents=True, exist_ok=True)
        inventory_projection = project_inventory(
            args.source_dir,
            args.inventory,
            args.output,
        )
        host_facts = {
            host: capture_host(
                args.source_dir,
                args.output,
                args.ssh_user,
                host,
            )
            for host in hosts
        }
        postgres_facts = {
            host: capture_postgresql(
                args.source_dir,
                args.output,
                args.ssh_user,
                host,
            )
            for host in hosts
        }
        patroni = {
            "pg-meta": capture_patroni(
                args.output,
                args.ssh_user,
                "10.10.10.10",
                "pg-meta",
            ),
            "pg-test": capture_patroni(
                args.output,
                args.ssh_user,
                "10.10.10.11",
                "pg-test",
            ),
        }
        endpoints = capture_endpoints(args.output, hosts)
        manifest = {
            "schema": "pg36-ch19-capture-manifest-v1",
            "captured_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "target": requirements["target"]["id"],
            "mode": "read-only-ssh-sql-rest-tcp",
            "ssh_user": args.ssh_user,
            "host_count": len(host_facts),
            "postgresql_member_count": len(postgres_facts),
            "patroni_cluster_count": len(patroni),
            "endpoint_host_count": len(endpoints["hosts"]),
            "pigsty_l1": "captured-for-disposable-sandbox",
            "production_approval": False,
            "source_sha256": {
                path.name: sha256(path)
                for path in sorted(args.source_dir.iterdir())
                if path.is_file()
            },
            "inventory_projection_sha256": sha256(
                args.output / "inventory-projection.json"
            ),
        }
        write_json(args.output / "capture-manifest.json", manifest)
    except (CaptureError, KeyError, TypeError) as error:
        sys.stderr.write(f"capture failed: {error}\n")
        return 1
    print("status=captured")
    print(f"target={requirements['target']['id']}")
    print(f"hosts={len(hosts)}")
    print("secrets=redacted")
    print("production_approval=false")
    print(f"evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
