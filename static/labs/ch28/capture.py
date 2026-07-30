#!/usr/bin/env python3
"""Capture the read-only preflight for the chapter 28 maintenance experiment."""

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
    "maintenance-contract.json",
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
    contract = read_json(source_dir / "maintenance-contract.json")
    deployment = read_json(upstream_root / "ch19" / "deployment-run.json")
    observability = read_json(upstream_root / "ch25" / "observability-run.json")
    tuning = read_json(upstream_root / "ch27" / "tuning-run.json")
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    if missing:
        raise CaptureError(f"chapter 28 source is incomplete: {missing}")
    if (
        deployment.get("boundary", {}).get("production_data_permitted") is not False
        or deployment.get("boundary", {}).get("production_traffic_permitted")
        is not False
        or deployment.get("observed_acceptance", {}).get("production_ch19_gate")
        != "pending"
    ):
        raise CaptureError("chapter 19 sandbox boundary is not acceptable")
    if (
        observability.get("target") != requirements["target"]
        or observability.get("postgresql_baseline", {}).get("role") != "primary"
        or observability.get("production_ch25_gate") != "pending"
    ):
        raise CaptureError("chapter 25 observation baseline is not acceptable")
    if (
        tuning.get("target") != requirements["target"]
        or tuning.get("decision", {}).get("persistent_change_applied") is not False
        or tuning.get("decision", {}).get("production_ch27_gate") != "pending"
    ):
        raise CaptureError("chapter 27 tuning boundary is not acceptable")
    forbidden = set(contract["forbidden_mutations"])
    if (
        "VACUUM FULL" not in forbidden
        or "DROP DATABASE FORCE" not in forbidden
        or "ALTER SYSTEM" not in forbidden
    ):
        raise CaptureError("maintenance contract is missing a hard safety boundary")

    remote_script = r'''
import json
import os
import subprocess
from pathlib import Path

def command(args, input_text=None):
    cp = subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        raise SystemExit(cp.stderr)
    return cp.stdout.strip()

sql = r"""
\pset format unaligned
\pset tuples_only on
WITH settings AS (
  SELECT jsonb_agg(
    jsonb_build_object(
      'name', name,
      'setting', setting,
      'unit', unit,
      'context', context,
      'source', source,
      'pending_restart', pending_restart
    )
    ORDER BY name
  ) AS value
  FROM pg_settings
  WHERE name = ANY (ARRAY[
    'autovacuum',
    'autovacuum_max_workers',
    'autovacuum_work_mem',
    'autovacuum_vacuum_threshold',
    'autovacuum_vacuum_max_threshold',
    'autovacuum_vacuum_scale_factor',
    'autovacuum_vacuum_insert_threshold',
    'autovacuum_vacuum_insert_scale_factor',
    'autovacuum_freeze_max_age',
    'vacuum_freeze_min_age',
    'vacuum_freeze_table_age',
    'vacuum_failsafe_age',
    'vacuum_cost_delay',
    'vacuum_cost_limit',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit',
    'maintenance_work_mem',
    'track_cost_delay_timing'
  ])
), extensions AS (
  SELECT jsonb_agg(
    jsonb_build_object(
      'name', name,
      'default_version', default_version,
      'installed_version', installed_version
    )
    ORDER BY name
  ) AS value
  FROM pg_available_extensions
  WHERE name = ANY (ARRAY[
    'amcheck','pg_freespacemap','pg_visibility','pgstattuple'
  ])
), slot_summary AS (
  SELECT jsonb_build_object(
    'total', count(*),
    'active', count(*) FILTER (WHERE active),
    'logical', count(*) FILTER (WHERE slot_type = 'logical'),
    'physical', count(*) FILTER (WHERE slot_type = 'physical'),
    'with_xmin', count(*) FILTER (WHERE xmin IS NOT NULL),
    'with_catalog_xmin', count(*) FILTER (WHERE catalog_xmin IS NOT NULL)
  ) AS value
  FROM pg_replication_slots
), prepared_summary AS (
  SELECT jsonb_build_object(
    'total', count(*),
    'oldest_age', coalesce(max(age(transaction)), 0)
  ) AS value
  FROM pg_prepared_xacts
), xmin_summary AS (
  SELECT jsonb_build_object(
    'sessions_with_backend_xmin',
      count(*) FILTER (
        WHERE backend_xmin IS NOT NULL AND pid <> pg_backend_pid()
      ),
    'sessions_idle_in_transaction',
      count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
          AND pid <> pg_backend_pid()
      ),
    'oldest_backend_xmin_age',
      coalesce(
        max(age(backend_xmin)) FILTER (
          WHERE backend_xmin IS NOT NULL AND pid <> pg_backend_pid()
        ),
        0
      )
  ) AS value
  FROM pg_stat_activity
)
SELECT jsonb_build_object(
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'current_user', current_user,
  'in_recovery', pg_is_in_recovery(),
  'address', inet_server_addr(),
  'port', inet_server_port(),
  'data_checksums', current_setting('data_checksums'),
  'existing_database', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'pg36_maintenance'
  ),
  'existing_role', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'dbuser_pg36maint'
  ),
  'available_extensions', (SELECT value FROM extensions),
  'settings', (SELECT value FROM settings),
  'replication_slots', (SELECT value FROM slot_summary),
  'prepared_transactions', (SELECT value FROM prepared_summary),
  'snapshot_holders', (SELECT value FROM xmin_summary),
  'xid_age', (
    SELECT jsonb_build_object(
      'oldest_database_age', max(age(datfrozenxid)),
      'oldest_database_name', (
        SELECT datname
        FROM pg_database
        ORDER BY age(datfrozenxid) DESC, datname
        LIMIT 1
      )
    )
    FROM pg_database
  ),
  'file_setting_errors', (
    SELECT count(*) FROM pg_file_settings WHERE error IS NOT NULL
  )
);
"""
pg = command([
    'psql','-X','-w','--quiet','--set=ON_ERROR_STOP=1','--no-psqlrc',
    '--dbname=service=pg-test-1 dbname=postgres application_name=pg36-ch28-preflight',
    '--file=-'
], sql)
rows = [line for line in pg.splitlines() if line.startswith('{')]
if len(rows) != 1:
    raise SystemExit('preflight SQL did not return one JSON row')

mem = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, _, value = line.partition(':')
    if key in {'MemTotal','MemAvailable','SwapTotal'}:
        mem[key] = int(value.strip().split()[0]) * 1024
disk = os.statvfs('/')
result = {
    'postgresql': json.loads(rows[0]),
    'host': {
        'hostname': command(['hostname']),
        'cpu_count': os.cpu_count(),
        'memory_bytes': mem,
        'root_filesystem_available_bytes': disk.f_bavail * disk.f_frsize,
        'psql_version': command(['psql','--version'])
    }
}
print(json.dumps(result, separators=(',', ':')))
'''
    remote = remote_json(args.ssh_user, args.bastion, remote_script)
    pg = remote["postgresql"]
    available = {
        row["name"] for row in pg.get("available_extensions", [])
    }
    if (
        pg.get("cluster_name") != "pg-test"
        or pg.get("in_recovery") is not False
        or int(pg.get("server_version_num", 0)) // 10000 != 18
        or pg.get("existing_database") is not False
        or pg.get("existing_role") is not False
        or set(requirements["required_extensions"]) - available
    ):
        raise CaptureError("live target does not satisfy the experiment preflight")
    source_hashes = {name: sha256(source_dir / name) for name in SOURCE_NAMES}
    evidence = {
        "schema": "pg36-ch28-preflight-evidence-v1",
        "captured_at": utc_now(),
        "run_id": str(uuid.uuid4()),
        "target": requirements["target"],
        "mode": "read-only-live-preflight",
        "mutation": "none",
        "clean_start": {
            "database_absent": True,
            "role_absent": True,
        },
        "upstream": {
            "ch19_release": deployment["release"],
            "ch25_run_id": observability["run_id"],
            "ch27_run_id": tuning["run_id"],
            "ch27_decision": tuning["decision"]["result"],
        },
        "source_hashes": source_hashes,
        "remote": remote,
        "risk": requirements["risk"],
        "production_ch28_gate": "pending",
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
        print(f"chapter 28 capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
