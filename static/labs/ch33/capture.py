#!/usr/bin/env python3
"""Capture secret-free PostgreSQL, Patroni, and process-fence evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from common import LabError, read_json, run, ssh_base, utc_now, write_json


SQL_FACTS = r"""
WITH control AS (
    SELECT
        system_identifier::text AS system_identifier
    FROM pg_catalog.pg_control_system()
),
checkpoint AS (
    SELECT timeline_id
    FROM pg_catalog.pg_control_checkpoint()
),
senders AS (
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'application_name', application_name,
                'client_addr', client_addr::text,
                'state', state,
                'sync_state', sync_state,
                'sent_lsn', sent_lsn::text,
                'write_lsn', write_lsn::text,
                'flush_lsn', flush_lsn::text,
                'replay_lsn', replay_lsn::text,
                'replay_gap_bytes',
                    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
            )
            ORDER BY application_name
        ),
        '[]'::jsonb
    ) AS rows
    FROM pg_catalog.pg_stat_replication
),
receiver AS (
    SELECT COALESCE(
        (
            SELECT jsonb_build_object(
                'status', status,
                'sender_host', sender_host,
                'sender_port', sender_port,
                'written_lsn', written_lsn::text,
                'flushed_lsn', flushed_lsn::text,
                'latest_end_lsn', latest_end_lsn::text
            )
            FROM pg_catalog.pg_stat_wal_receiver
            LIMIT 1
        ),
        '{}'::jsonb
    ) AS row
)
SELECT jsonb_build_object(
    'server_version', current_setting('server_version'),
    'cluster_name', current_setting('cluster_name'),
    'system_identifier', control.system_identifier,
    'in_recovery', pg_is_in_recovery(),
    'timeline', checkpoint.timeline_id,
    'current_or_replay_lsn',
        CASE
            WHEN pg_is_in_recovery()
            THEN pg_last_wal_replay_lsn()::text
            ELSE pg_current_wal_lsn()::text
        END,
    'receive_lsn', pg_last_wal_receive_lsn()::text,
    'replay_lsn', pg_last_wal_replay_lsn()::text,
    'replay_paused',
        CASE
            WHEN pg_is_in_recovery()
            THEN pg_is_wal_replay_paused()
            ELSE false
        END,
    'data_checksums', current_setting('data_checksums'),
    'wal_log_hints', current_setting('wal_log_hints'),
    'full_page_writes', current_setting('full_page_writes'),
    'senders', senders.rows,
    'receiver', receiver.row
)
FROM control, checkpoint, senders, receiver;
"""


NODE_PROJECTION = r"""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(Path("/etc/patroni/patroni.yml").read_text())
data_dir = Path(cfg["postgresql"]["data_dir"])
pidfile = data_dir / "postmaster.pid"
pid = None
alive = False
if pidfile.exists():
    try:
        pid = int(pidfile.read_text().splitlines()[0])
        os.kill(pid, 0)
        alive = True
    except (OSError, ValueError, IndexError):
        alive = False

service = subprocess.run(
    ["systemctl", "is-active", "patroni"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    check=False,
).stdout.strip()

connect = (cfg.get("restapi") or {}).get("connect_address")
rest = False
rest_role = None
if connect:
    try:
        with urllib.request.urlopen(
            "http://" + str(connect) + "/patroni",
            timeout=1,
        ) as response:
            value = json.loads(response.read())
        rest = True
        rest_role = value.get("role")
    except Exception:
        pass

print(json.dumps({
    "member_name": cfg.get("name"),
    "scope": cfg.get("scope"),
    "data_dir": str(data_dir),
    "service_state": service,
    "service_active": service == "active",
    "postmaster_pid_present": pid is not None,
    "postmaster_alive": alive,
    "patroni_rest_reachable": rest,
    "patroni_rest_role": rest_role,
}))
"""


def capture_node(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host) + ["sudo", "-n", "python3", "-"],
        stdin=NODE_PROJECTION,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError(f"node projection on {host} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError(f"node projection on {host} returned no object")
    value["address"] = host
    return value


def capture_sql(user: str, host: str) -> dict[str, Any]:
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
        stdin=SQL_FACTS,
        timeout=15,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError(f"SQL projection on {host} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError(f"SQL projection on {host} returned no object")
    value["address"] = host
    value["available"] = True
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
        ]
    ).stdout
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError("patronictl list returned invalid JSON") from exc
    if not isinstance(rows, list):
        raise LabError("patronictl list did not return an array")
    members: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise LabError("patronictl member row is not an object")
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
                "tags": lower.get("tags"),
            }
        )
    members.sort(key=lambda row: str(row["member"]))
    return {
        "schema": "pg36-ch33-patroni-members-v1",
        "cluster": "pg-test",
        "members": members,
    }


def capture_dynamic_policy(user: str, host: str) -> dict[str, Any]:
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
        ]
    ).stdout
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise LabError("Patroni dynamic config is invalid YAML") from exc
    if not isinstance(value, dict):
        raise LabError("Patroni dynamic config is not a mapping")
    postgresql = value.get("postgresql") or {}
    return {
        "ttl": value.get("ttl"),
        "loop_wait": value.get("loop_wait"),
        "retry_timeout": value.get("retry_timeout"),
        "maximum_lag_on_failover": value.get("maximum_lag_on_failover"),
        "synchronous_mode": bool(value.get("synchronous_mode", False)),
        "synchronous_mode_strict": bool(
            value.get("synchronous_mode_strict", False)
        ),
        "failsafe_mode": bool(value.get("failsafe_mode", False)),
        "pause": bool(value.get("pause", False)),
        "postgresql": {
            "use_pg_rewind": bool(postgresql.get("use_pg_rewind", False)),
            "use_slots": bool(postgresql.get("use_slots", False)),
        },
    }


def capture_phase(
    requirements: dict[str, Any],
    user: str,
    phase: str,
) -> dict[str, Any]:
    members = requirements["members"]
    observer = str(members["pg-test-3"]["address"])
    sql: dict[str, Any] = {}
    nodes: dict[str, Any] = {}
    for name in sorted(members):
        host = str(members[name]["address"])
        try:
            nodes[name] = capture_node(user, host)
        except LabError:
            nodes[name] = {"address": host, "capture_available": False}
        try:
            sql[name] = capture_sql(user, host)
        except LabError:
            sql[name] = {
                "address": host,
                "available": False,
            }
    return {
        "schema": "pg36-ch33-phase-v1",
        "captured_at": utc_now(),
        "phase": phase,
        "target": requirements["target"]["id"],
        "patroni": capture_patroni(user, observer),
        "dynamic_policy": capture_dynamic_policy(user, observer),
        "nodes": nodes,
        "postgres": sql,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        value = capture_phase(
            read_json(args.requirements),
            args.ssh_user,
            args.phase,
        )
        write_json(args.output, value)
    except (KeyError, TypeError, LabError, OSError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    print(f"status=captured phase={args.phase}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
