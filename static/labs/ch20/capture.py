#!/usr/bin/env python3
"""Capture secret-free PostgreSQL and Patroni HA facts for chapter 20."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class CaptureError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"{path} must contain an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


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
        detail = result.stderr.strip().splitlines()
        raise CaptureError(
            f"command failed ({args[0]}): "
            + (detail[-1] if detail else f"exit {result.returncode}")
        )
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
        "-o",
        "LogLevel=ERROR",
        f"{user}@{host}",
    ]


def capture_postgresql(
    source_dir: Path,
    user: str,
    host: str,
) -> dict[str, Any]:
    sql = (source_dir / "ha-facts.sql").read_text(encoding="utf-8")
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
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"PostgreSQL on {host} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"PostgreSQL on {host} did not return an object")
    value["target_ip"] = host
    return value


def normalize_role(role: Any) -> str:
    value = str(role or "").strip().lower().replace(" ", "-")
    if value in {"leader", "primary", "master"}:
        return "primary"
    if value in {"replica", "standby", "sync-standby"}:
        return "replica"
    return value


def capture_patroni(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "list",
            "pg-test",
            "--format=json",
        ],
    )
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError("patronictl list returned invalid JSON") from exc
    if not isinstance(rows, list):
        raise CaptureError("patronictl list must return an array")
    members: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise CaptureError("patronictl list row must be an object")
        lower = {
            str(key).lower().replace(" ", "_"): value
            for key, value in row.items()
        }
        members.append(
            {
                "member": lower.get("member"),
                "host": lower.get("host"),
                "role": normalize_role(lower.get("role")),
                "state": str(lower.get("state", "")).lower(),
                "timeline": lower.get("tl", lower.get("timeline")),
                "lag_mb": lower.get("lag_in_mb", lower.get("lag")),
            }
        )
    members.sort(key=lambda row: str(row["member"]))
    return {
        "schema": "pg36-ch20-patroni-members-v1",
        "cluster": "pg-test",
        "members": members,
    }


LOCAL_CONFIG_PROJECTION = r"""
import importlib.metadata
import json
import yaml

document = yaml.safe_load(open("/etc/patroni/patroni.yml"))
dcs_kind = next(
    (
        key
        for key in ("etcd3", "etcd", "consul", "zookeeper", "kubernetes")
        if key in document
    ),
    None,
)
dcs = document.get(dcs_kind) or {} if dcs_kind else {}
hosts = dcs.get("hosts")
if isinstance(hosts, str):
    endpoints = [value.strip() for value in hosts.split(",") if value.strip()]
elif isinstance(hosts, (list, tuple, dict)):
    endpoints = list(hosts)
elif dcs.get("host"):
    endpoints = [dcs.get("host")]
else:
    endpoints = []
print(
    json.dumps(
        {
            "scope": document.get("scope"),
            "member_name": document.get("name"),
            "patroni_version": importlib.metadata.version("patroni"),
            "watchdog": document.get("watchdog") or {},
            "dcs_kind": dcs_kind,
            "dcs_endpoint_count": len(endpoints),
            "restapi_connect_address": (
                document.get("restapi") or {}
            ).get("connect_address"),
            "postgresql_connect_address": (
                document.get("postgresql") or {}
            ).get("connect_address"),
        },
        sort_keys=True,
    )
)
"""


def capture_local_config(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host) + ["sudo", "-n", "python3", "-"],
        stdin=LOCAL_CONFIG_PROJECTION,
    )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaptureError("local Patroni projection returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise CaptureError("local Patroni projection must be an object")
    return value


def capture_dynamic_config(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "show-config",
            "pg-test",
        ],
    )
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise CaptureError("Patroni dynamic config is invalid YAML") from exc
    if not isinstance(document, dict):
        raise CaptureError("Patroni dynamic config must be a mapping")
    postgresql = document.get("postgresql") or {}
    parameters = postgresql.get("parameters") or {}
    return {
        "schema": "pg36-ch20-patroni-policy-v1",
        "ttl": document.get("ttl"),
        "loop_wait": document.get("loop_wait"),
        "retry_timeout": document.get("retry_timeout"),
        "maximum_lag_on_failover": document.get("maximum_lag_on_failover"),
        "maximum_lag_on_syncnode": document.get("maximum_lag_on_syncnode"),
        "synchronous_mode": bool(document.get("synchronous_mode", False)),
        "synchronous_mode_strict": bool(
            document.get("synchronous_mode_strict", False)
        ),
        "synchronous_node_count": document.get("synchronous_node_count"),
        "failsafe_mode": bool(document.get("failsafe_mode", False)),
        "pause": bool(document.get("pause", False)),
        "postgresql": {
            "use_pg_rewind": bool(postgresql.get("use_pg_rewind", False)),
            "use_slots": bool(postgresql.get("use_slots", False)),
            "parameters": {
                key: parameters[key]
                for key in (
                    "synchronous_commit",
                    "synchronous_standby_names",
                    "wal_log_hints",
                )
                if key in parameters
            },
        },
    }


def capture_phase(
    requirements: dict[str, Any],
    source_dir: Path,
    user: str,
    phase: str,
) -> dict[str, Any]:
    member_map = requirements["members"]
    hosts = [
        str(member_map[name]["address"])
        for name in sorted(member_map)
    ]
    observer = str(member_map["pg-test-3"]["address"])
    return {
        "schema": "pg36-ch20-ha-phase-v1",
        "release": requirements["release"],
        "phase": phase,
        "captured_at": utc_now(),
        "target": requirements["target"]["id"],
        "postgres": {
            host: capture_postgresql(source_dir, user, host)
            for host in hosts
        },
        "patroni": capture_patroni(user, observer),
        "dynamic_policy": capture_dynamic_config(user, observer),
        "local_patroni": {
            host: capture_local_config(user, host)
            for host in hosts
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        phase = capture_phase(
            read_json(args.requirements),
            args.source_dir,
            args.ssh_user,
            args.phase,
        )
        write_json(args.output, phase)
    except (CaptureError, KeyError, TypeError, OSError) as error:
        sys.stderr.write(f"HA capture failed: {error}\n")
        return 1
    print(f"status=captured phase={args.phase}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
