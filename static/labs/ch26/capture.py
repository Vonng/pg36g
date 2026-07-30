#!/usr/bin/env python3
"""Capture the read-only preflight for the chapter 26 capacity exercise."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_NAMES = [
    "requirements.json",
    "workload-contract.json",
    "experiment-matrix.json",
    "capacity-model.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "reset-cell.sql",
    "read-product.sql",
    "read-order.sql",
    "place-order.sql",
    "stat-snapshot.sql",
    "wait-sampler.sql",
    "system_sampler.py",
    "remote_benchmark.py",
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


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
            f"{' '.join(command[:2])}: {completed.stderr.strip()[-2000:]}"
        )
    return completed.stdout


def remote_json(user: str, bastion: str, script: str) -> Any:
    output = run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            f"{user}@{bastion}",
            "python3",
            "-",
        ],
        input_text=script,
    )
    lines = [line for line in output.splitlines() if line.lstrip().startswith("{")]
    if len(lines) != 1:
        raise CaptureError(f"remote preflight returned {len(lines)} JSON rows")
    return json.loads(lines[0])


def reachable(url: str, *, require_ok_body: bool = False) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read(4096)
            return (
                response.status == 200
                and (
                    not require_ok_body
                    or body.strip().upper().startswith(b"OK")
                )
            )
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    requirements = read_json(source_dir / "requirements.json")
    ch19 = read_json(upstream_root / "ch19" / "deployment-run.json")
    ch25 = read_json(upstream_root / "ch25" / "observability-run.json")
    if (
        ch19.get("observed_acceptance", {}).get("sandbox_l2")
        != "accepted-with-exceptions"
        or ch19.get("observed_acceptance", {}).get("production_ch19_gate")
        != "pending"
        or ch19.get("boundary", {}).get("production_data_permitted") is not False
        or ch19.get("boundary", {}).get("production_traffic_permitted") is not False
    ):
        raise CaptureError("chapter 19 sandbox boundary is not acceptable")
    if (
        ch25.get("target") != "pg36-l2-vagrant/pg-test"
        or ch25.get("production_ch25_gate") != "pending"
        or ch25.get("postgresql_baseline", {}).get("role") != "primary"
    ):
        raise CaptureError("chapter 25 observation baseline is not acceptable")
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    if missing:
        raise CaptureError(f"chapter 26 source is incomplete: {missing}")
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
  'replica_count', (
    SELECT count(*) FROM pg_stat_replication WHERE state = 'streaming'
  ),
  'existing_database', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'pg36_capacity'
  ),
  'existing_role', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'dbuser_pg36bench'
  ),
  'settings', (
    SELECT jsonb_object_agg(name, setting ORDER BY name)
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'shared_buffers','effective_cache_size','work_mem','max_connections',
      'synchronous_commit','fsync','full_page_writes','data_checksums',
      'track_io_timing','track_wal_io_timing','stats_fetch_consistency'
    ])
  )
);
'''
pg = command([
    'psql','-X','-w','--set=ON_ERROR_STOP=1','--no-psqlrc',
    '--dbname=service=pg-test-1 dbname=postgres application_name=pg36-ch26-preflight',
    '--file=-'
], sql)
pg_rows = [line for line in pg.splitlines() if line.startswith('{')]
if len(pg_rows) != 1:
    raise SystemExit('preflight SQL did not return one JSON row')

def resources(local=True):
    if local:
        cpu = os.cpu_count()
        mem_lines = Path('/proc/meminfo').read_text().splitlines()
        vfs = os.statvfs('/')
        host = command(['hostname'])
    else:
        py = r'''
import json, os
from pathlib import Path
vfs=os.statvfs('/')
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
 k,_,v=line.partition(':')
 if k in {'MemTotal','MemAvailable','SwapTotal'}:
  mem[k]=int(v.strip().split()[0])*1024
print(json.dumps({'hostname':Path('/etc/hostname').read_text().strip(),
 'cpu_count':os.cpu_count(),'memory_bytes':mem,
 'root_total_bytes':vfs.f_frsize*vfs.f_blocks,
 'root_available_bytes':vfs.f_frsize*vfs.f_bavail}))
'''
        return json.loads(command(
            ['ssh','-o','BatchMode=yes','vagrant@10.10.10.11','python3','-'],
            py
        ))
    mem = {}
    for line in mem_lines:
        key, _, value = line.partition(':')
        if key in {'MemTotal','MemAvailable','SwapTotal'}:
            mem[key] = int(value.strip().split()[0]) * 1024
    return {
        'hostname': host,
        'cpu_count': cpu,
        'memory_bytes': mem,
        'root_total_bytes': vfs.f_frsize * vfs.f_blocks,
        'root_available_bytes': vfs.f_frsize * vfs.f_bavail,
    }

print(json.dumps({
  'client': resources(True),
  'server': resources(False),
  'postgresql': json.loads(pg_rows[0]),
  'pgbench_version': command(['pgbench','--version']),
  'psql_version': command(['psql','--version']),
}, separators=(',', ':')))
"""
    live = remote_json(args.ssh_user, args.bastion, remote_script)
    pg = live["postgresql"]
    if (
        live["client"]["hostname"] != "pg-meta-1"
        or live["server"]["hostname"] != "pg-test-1"
        or pg["cluster_name"] != "pg-test"
        or pg["in_recovery"] is not False
        or pg["address"] != "10.10.10.11"
        or pg["replica_count"] != 2
        or pg["existing_database"] is not False
        or pg["existing_role"] is not False
    ):
        raise CaptureError(f"live target or clean-start gate failed: {live!r}")
    evidence = {
        "schema": "pg36-ch26-preflight-evidence-v1",
        "release": requirements["release"],
        "run_id": str(uuid.uuid4()),
        "captured_at": utc_now(),
        "risk": "L0-read-only-preflight",
        "mutation": "none",
        "target": requirements["target"],
        "source_hashes": {
            name: sha256(source_dir / name) for name in SOURCE_NAMES
        },
        "upstream": {
            "chapter_19": {
                "release": ch19.get("release"),
                "sandbox_l2": ch19["observed_acceptance"]["sandbox_l2"],
                "production_ch19_gate": ch19["observed_acceptance"][
                    "production_ch19_gate"
                ],
                "source_hashes": {
                    name: sha256(upstream_root / "ch19" / name)
                    for name in (
                        "requirements.json",
                        "deployment-run.json",
                    )
                },
            },
            "chapter_25": {
                "run_id": ch25.get("run_id"),
                "production_ch25_gate": ch25.get("production_ch25_gate"),
                "source_hashes": {
                    name: sha256(upstream_root / "ch25" / name)
                    for name in (
                        "requirements.json",
                        "signal-contract.json",
                        "observability-run.json",
                    )
                },
            },
        },
        "live": live,
        "monitoring_health": {
            "VictoriaMetrics": reachable(
                "http://10.10.10.10:8428/health",
                require_ok_body=True,
            ),
            "pg_exporter": reachable("http://10.10.10.11:9630/metrics"),
        },
        "clean_start": {
            "database_absent": True,
            "role_absent": True,
        },
        "production_ch26_gate": "pending",
    }
    if not evidence["monitoring_health"]["VictoriaMetrics"]:
        raise CaptureError("VictoriaMetrics preflight is not healthy")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "capture-ok",
                "run_id": evidence["run_id"],
                "client_cpu": live["client"]["cpu_count"],
                "server_cpu": live["server"]["cpu_count"],
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CaptureError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"chapter 26 capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
