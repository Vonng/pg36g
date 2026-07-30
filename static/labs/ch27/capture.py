#!/usr/bin/env python3
"""Capture the read-only preflight for the chapter 27 tuning experiment."""

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
    "parameter-candidates.json",
    "change-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "reset-run.sql",
    "read-product.sql",
    "read-order.sql",
    "place-order.sql",
    "plan-probe-counts.sql",
    "plan-probe-product.sql",
    "plan-probe-order.sql",
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


def run(
    command: list[str],
    *,
    input_text: str | None = None,
) -> str:
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
            f"{' '.join(command[:2])}: {completed.stderr.strip()[-2000:]}"
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
    change_contract = read_json(source_dir / "change-contract.json")
    candidates = read_json(source_dir / "parameter-candidates.json")
    ch19 = read_json(upstream_root / "ch19" / "deployment-run.json")
    ch25 = read_json(upstream_root / "ch25" / "observability-run.json")
    ch26_path = upstream_root / "ch26" / "capacity-run.json"
    ch26 = read_json(ch26_path)
    if (
        ch19.get("boundary", {}).get("production_data_permitted") is not False
        or ch19.get("boundary", {}).get("production_traffic_permitted") is not False
        or ch19.get("observed_acceptance", {}).get("production_ch19_gate")
        != "pending"
    ):
        raise CaptureError("chapter 19 sandbox boundary is not acceptable")
    if (
        ch25.get("target") != "pg36-l2-vagrant/pg-test"
        or ch25.get("production_ch25_gate") != "pending"
        or ch25.get("postgresql_baseline", {}).get("role") != "primary"
    ):
        raise CaptureError("chapter 25 observation baseline is not acceptable")
    if (
        ch26.get("run_id")
        != requirements["upstream"]["required_run_id"]
        or ch26.get("capacity_model", {}).get("production_sustainable_tps")
        is not None
        or any(
            row.get("exact_knee_known") is not False
            for row in ch26.get("capacity_model", {}).get(
                "saturation_brackets", []
            )
        )
        or any(
            row.get("temp_bytes") != 0
            for row in ch26.get("experiment", {}).get("results", [])
        )
    ):
        raise CaptureError("chapter 26 evidence does not support this hypothesis boundary")
    tested = [row for row in candidates["candidates"] if row.get("tested") is True]
    if (
        len(tested) != 1
        or tested[0]["parameter"] != "plan_cache_mode"
        or change_contract["parameter"]["scope"] != "benchmark session"
        or change_contract["parameter"]["persistent"] is not False
    ):
        raise CaptureError("the chapter 27 experiment must test one session-local parameter")
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    if missing:
        raise CaptureError(f"chapter 27 source is incomplete: {missing}")
    remote_script = r"""
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

sql = r'''
\pset format unaligned
\pset tuples_only on
SELECT jsonb_build_object(
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'in_recovery', pg_is_in_recovery(),
  'address', inet_server_addr(),
  'port', inet_server_port(),
  'existing_database', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'pg36_tuning'
  ),
  'existing_role', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'dbuser_pg36tune'
  ),
  'settings', (
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
    )
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'plan_cache_mode','work_mem','shared_buffers','effective_cache_size',
      'max_connections','max_worker_processes','max_parallel_workers',
      'synchronous_commit','fsync','full_page_writes','wal_compression',
      'checkpoint_timeout','checkpoint_completion_target','max_wal_size',
      'random_page_cost','effective_io_concurrency'
    ])
  ),
  'file_error_count', (
    SELECT count(*) FROM pg_file_settings WHERE error IS NOT NULL
  )
);
'''
pg = command([
    'psql','-X','-w','--quiet','--set=ON_ERROR_STOP=1','--no-psqlrc',
    '--dbname=service=pg-test-1 dbname=postgres application_name=pg36-ch27-preflight',
    '--file=-'
], sql)
rows = [line for line in pg.splitlines() if line.startswith('{')]
if len(rows) != 1:
    raise SystemExit('preflight SQL did not return one JSON row')

def resources():
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in {'MemTotal','MemAvailable','SwapTotal'}:
            mem[key] = int(value.strip().split()[0]) * 1024
    return {
        'hostname': command(['hostname']),
        'cpu_count': os.cpu_count(),
        'memory_bytes': mem,
        'pgbench_version': command(['pgbench','--version'])
    }

server_script = r'''
import json, os
from pathlib import Path
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
 key,_,value=line.partition(':')
 if key in {'MemTotal','MemAvailable','SwapTotal'}:
  mem[key]=int(value.strip().split()[0])*1024
print(json.dumps({
 'hostname':Path('/etc/hostname').read_text().strip(),
 'cpu_count':os.cpu_count(),
 'memory_bytes':mem
}, separators=(',',':')))
'''
server = json.loads(command(
    ['ssh','-o','BatchMode=yes','vagrant@10.10.10.11','python3','-'],
    server_script
))
print(json.dumps({
  'postgresql': json.loads(rows[0]),
  'client': resources(),
  'server': server
}, separators=(',',':')))
"""
    remote = remote_json(args.ssh_user, args.bastion, remote_script)
    pg = remote["postgresql"]
    target = requirements["target"]
    if (
        pg.get("cluster_name") != target["cluster"]
        or pg.get("server_version_num", 0) < 180000
        or pg.get("in_recovery") is not False
        or pg.get("address") != target["primary_address"]
        or pg.get("port") != 5432
        or pg.get("existing_database") is not False
        or pg.get("existing_role") is not False
        or pg.get("file_error_count") != 0
        or remote["client"].get("hostname") != "pg-meta-1"
        or remote["server"].get("hostname") != "pg-test-1"
    ):
        raise CaptureError(f"target preflight failed: {remote}")
    setting_map = {row["name"]: row for row in pg["settings"]}
    plan_cache = setting_map.get("plan_cache_mode")
    if (
        plan_cache is None
        or plan_cache.get("setting") != "auto"
        or plan_cache.get("context") != "user"
        or setting_map.get("synchronous_commit", {}).get("setting") != "on"
        or setting_map.get("fsync", {}).get("setting") != "on"
        or setting_map.get("full_page_writes", {}).get("setting") != "on"
    ):
        raise CaptureError("parameter or durability precondition failed")
    source_hashes = {
        name: sha256(source_dir / name)
        for name in SOURCE_NAMES
    }
    evidence = {
        "schema": "pg36-ch27-preflight-evidence-v1",
        "captured_at": utc_now(),
        "preflight_run_id": str(uuid.uuid4()),
        "mutation": "none",
        "target": "pg36-l2-vagrant/pg-test",
        "risk": "L0-read-only-preflight",
        "clean_start": {
            "database_absent": True,
            "role_absent": True,
        },
        "upstream": {
            "chapter19_boundary_accepted": True,
            "chapter25_observation_accepted": True,
            "chapter26_run_id": ch26["run_id"],
            "chapter26_sha256": sha256(ch26_path),
            "chapter26_exact_knee_known": False,
            "chapter26_production_tps": None,
            "chapter26_all_temp_bytes_zero": True,
        },
        "experiment": {
            "tested_parameter_count": 1,
            "parameter": "plan_cache_mode",
            "baseline": "auto",
            "candidate": "force_generic_plan",
            "scope": "benchmark-session-only",
            "persistent_configuration_change": False,
        },
        "remote": remote,
        "source_hashes": source_hashes,
        "production_ch27_gate": "pending",
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
                "preflight_run_id": evidence["preflight_run_id"],
                "target": evidence["target"],
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
        print(f"chapter 27 capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
