#!/usr/bin/env python3
"""Capture the read-only preflight for the chapter 29 migration lab."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_NAMES = [
    "requirements.json",
    "migration-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "remote_experiment.py",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]


class CaptureError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--bastion", default="10.10.10.10")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise CaptureError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(command[:2])}: {completed.stderr.strip()[-2400:]}"
        )
    return completed.stdout


def remote_json(user: str, host: str, script: str) -> Any:
    output = run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            f"{user}@{host}",
            "python3",
            "-",
        ],
        input_text=script,
    )
    rows = [line for line in output.splitlines() if line.lstrip().startswith("{")]
    if len(rows) != 1:
        raise CaptureError(f"remote preflight returned {len(rows)} JSON rows")
    return json.loads(rows[0])


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    output = args.output.resolve()
    requirements = read_json(source_dir / "requirements.json")
    contract = read_json(source_dir / "migration-contract.json")
    deployment = read_json(upstream_root / "ch19" / "deployment-run.json")
    security = read_json(upstream_root / "ch23" / "security-run.json")
    observability = read_json(upstream_root / "ch25" / "observability-run.json")
    maintenance = read_json(upstream_root / "ch28" / "maintenance-run.json")
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    if missing:
        raise CaptureError(f"chapter 29 source is incomplete: {missing}")
    if (
        deployment.get("observed_acceptance", {}).get("postgresql_clusters") != 2
        or deployment.get("boundary", {}).get("production_data_permitted") is not False
        or deployment.get("observed_acceptance", {}).get("production_ch19_gate")
        != "pending"
    ):
        raise CaptureError("chapter 19 two-cluster sandbox boundary is not acceptable")
    if (
        security.get("target", {}).get("production_data") is not False
        or security.get("target", {}).get("production_traffic") is not False
    ):
        raise CaptureError("chapter 23 security boundary is not acceptable")
    if (
        observability.get("postgresql_baseline", {}).get("role") != "primary"
        or observability.get("production_ch25_gate") != "pending"
    ):
        raise CaptureError("chapter 25 observation baseline is not acceptable")
    if (
        maintenance.get("cleanup", {}).get("database_absent") is not True
        or maintenance.get("decision", {}).get("production_ch28_gate") != "pending"
    ):
        raise CaptureError("chapter 28 cleanup boundary is not acceptable")
    forbidden = set(contract.get("forbidden_mutations", []))
    for required in (
        "ALTER SYSTEM",
        "change HAProxy, PgBouncer, DNS, VIP, or application routes",
        "DROP DATABASE FORCE",
        "touch production data or traffic",
    ):
        if required not in forbidden:
            raise CaptureError(f"migration contract misses forbidden action: {required}")

    remote_script = r'''
import json
import subprocess

def command(args, sql):
    cp = subprocess.run(
        args,
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        raise SystemExit(cp.stderr)
    rows = [
        line.strip() for line in cp.stdout.splitlines()
        if line.lstrip().startswith("{")
    ]
    if len(rows) != 1:
        raise SystemExit(f"expected one JSON row, got {len(rows)}")
    return json.loads(rows[0])

def probe(service, side):
    if side == "source":
        object_sql = """
          'database_absent', NOT EXISTS (
            SELECT FROM pg_database WHERE datname = 'pg36_shop_src'
          ),
          'owner_role_absent', NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'pg36_ch29_source_owner'
          ),
          'runtime_role_absent', NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'dbuser_pg36source'
          ),
          'replication_role_absent', NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'dbuser_pg36repl'
          ),
          'slot_absent', NOT EXISTS (
            SELECT FROM pg_replication_slots WHERE slot_name = 'pg36_shop_slot'
          ),
          'logical_slots', (
            SELECT count(*) FROM pg_replication_slots
            WHERE slot_type = 'logical'
          ),
        """
    else:
        object_sql = """
          'database_absent', NOT EXISTS (
            SELECT FROM pg_database WHERE datname = 'pg36_shop_dst'
          ),
          'owner_role_absent', NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'pg36_ch29_target_owner'
          ),
          'runtime_role_absent', NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'dbuser_pg36target'
          ),
          'subscription_absent', NOT EXISTS (
            SELECT FROM pg_subscription WHERE subname = 'pg36_shop_sub'
          ),
          'logical_slots', (
            SELECT count(*) FROM pg_replication_slots
            WHERE slot_type = 'logical'
          ),
        """
    sql = (
        "\\pset format unaligned\n"
        "\\pset tuples_only on\n"
        "SELECT jsonb_build_object("
        "'cluster_name', current_setting('cluster_name'),"
        "'server_version', current_setting('server_version'),"
        "'server_version_num', current_setting('server_version_num')::int,"
        "'in_recovery', pg_is_in_recovery(),"
        "'system_identifier', (SELECT system_identifier FROM pg_control_system()),"
        "'wal_level', current_setting('wal_level'),"
        "'max_replication_slots', current_setting('max_replication_slots')::int,"
        "'max_wal_senders', current_setting('max_wal_senders')::int,"
        "'max_logical_replication_workers', "
        "current_setting('max_logical_replication_workers')::int,"
        "'max_sync_workers_per_subscription', "
        "current_setting('max_sync_workers_per_subscription')::int,"
        "'max_slot_wal_keep_size', current_setting('max_slot_wal_keep_size'),"
        + object_sql
        + "'data_checksums', current_setting('data_checksums')"
        ");\n"
    )
    return command([
        "psql", "-X", "-w", "--quiet", "--set=ON_ERROR_STOP=1",
        "--no-psqlrc", "--dbname",
        f"service={service} dbname=postgres application_name=pg36-ch29-preflight",
        "--file=-",
    ], sql)

print(json.dumps({
    "source": probe("pg-test-1", "source"),
    "target": probe("pg-meta-1", "target"),
}, separators=(",", ":")))
'''
    remote = remote_json(args.ssh_user, args.bastion, remote_script)
    source = remote["source"]
    target = remote["target"]
    if (
        source.get("cluster_name") != requirements["source"]["cluster"]
        or target.get("cluster_name")
        != requirements["target_database"]["cluster"]
        or source.get("in_recovery") is not False
        or target.get("in_recovery") is not False
        or source.get("wal_level") != "logical"
        or int(source.get("server_version_num", 0)) // 10000 != 18
        or int(target.get("server_version_num", 0)) // 10000 != 18
        or source.get("system_identifier") == target.get("system_identifier")
    ):
        raise CaptureError("live source/target identity is not acceptable")
    clean_start = {
        "source": {
            key: source[key]
            for key in (
                "database_absent",
                "owner_role_absent",
                "runtime_role_absent",
                "replication_role_absent",
                "slot_absent",
            )
        },
        "target": {
            key: target[key]
            for key in (
                "database_absent",
                "owner_role_absent",
                "runtime_role_absent",
                "subscription_absent",
            )
        },
    }
    if any(value is not True for side in clean_start.values() for value in side.values()):
        raise CaptureError(f"chapter 29 fixture did not start clean: {clean_start}")
    evidence = {
        "schema": "pg36-ch29-preflight-evidence-v1",
        "captured_at": utc_now(),
        "run_id": str(uuid.uuid4()),
        "target": requirements["target"],
        "mode": "read-only-two-cluster-preflight",
        "mutation": "none",
        "clean_start": clean_start,
        "upstream": {
            "ch19_release": deployment["release"],
            "ch23_run_id": security["run_id"],
            "ch25_run_id": observability["run_id"],
            "ch28_run_id": maintenance["run_id"],
        },
        "source_hashes": {
            name: sha256(source_dir / name) for name in SOURCE_NAMES
        },
        "remote": remote,
        "risk": requirements["risk"],
        "production_ch29_gate": "pending",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "capture-ok",
                "run_id": evidence["run_id"],
                "target": evidence["target"],
                "mutation": "none",
                "distinct_system_identifiers": True,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CaptureError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(f"chapter 29 capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
