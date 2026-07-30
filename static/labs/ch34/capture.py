#!/usr/bin/env python3
"""Capture a read-only, secret-free projection of the managed Pigsty cluster."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import LabError, read_json, run, ssh_base, utc_now, write_json


SQL_FACTS = r"""
WITH control AS (
    SELECT system_identifier::text AS system_identifier
    FROM pg_catalog.pg_control_system()
),
checkpoint AS (
    SELECT timeline_id
    FROM pg_catalog.pg_control_checkpoint()
),
activity AS (
    SELECT
        count(*)::int AS total,
        count(*) FILTER (
            WHERE application_name LIKE 'pg36-ch34-%'
        )::int AS chapter_fixture_sessions,
        count(*) FILTER (
            WHERE wait_event_type = 'Lock'
        )::int AS lock_waiters
    FROM pg_catalog.pg_stat_activity
),
slots AS (
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'slot_name', slot_name,
                'slot_type', slot_type,
                'active', active,
                'database', database,
                'wal_status', wal_status,
                'invalidation_reason', invalidation_reason
            )
            ORDER BY slot_name
        ),
        '[]'::jsonb
    ) AS rows
    FROM pg_catalog.pg_replication_slots
)
SELECT jsonb_build_object(
    'server_version', current_setting('server_version'),
    'cluster_name', current_setting('cluster_name'),
    'system_identifier', control.system_identifier,
    'timeline', checkpoint.timeline_id,
    'in_recovery', pg_is_in_recovery(),
    'max_connections', current_setting('max_connections')::int,
    'superuser_reserved_connections',
        current_setting('superuser_reserved_connections')::int,
    'database_size_bytes', pg_database_size(current_database()),
    'activity', jsonb_build_object(
        'total', activity.total,
        'chapter_fixture_sessions', activity.chapter_fixture_sessions,
        'lock_waiters', activity.lock_waiters
    ),
    'replication_slots', slots.rows
)
FROM control, checkpoint, activity, slots;
"""


DISPOSABLE_PROJECTION = r"""
import glob
import json
import os
from pathlib import Path

roots = []
for raw in glob.glob("/tmp/pg36-ch34-overload-*"):
    path = Path(raw)
    roots.append({
        "path": str(path),
        "is_dir": path.is_dir(),
        "owner_uid": path.stat().st_uid if path.exists() else None,
    })
print(json.dumps({
    "matching_roots": sorted(roots, key=lambda row: row["path"]),
    "effective_uid": os.geteuid(),
}))
"""


def normalize_role(role: Any) -> str:
    value = str(role or "").strip().lower().replace(" ", "-")
    if value in {"leader", "primary", "master"}:
        return "primary"
    if value in {"replica", "standby", "sync-standby"}:
        return "replica"
    return value


def capture_patroni(user: str, host: str, cluster: str) -> list[dict[str, Any]]:
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
            cluster,
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
            }
        )
    members.sort(key=lambda row: str(row["member"]))
    return members


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
        timeout=20,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError("managed SQL projection returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError("managed SQL projection returned no object")
    return value


def capture_disposable_roots(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host)
        + ["sudo", "-n", "-iu", "postgres", "python3", "-"],
        stdin=DISPOSABLE_PROJECTION,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError("disposable-root projection returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError("disposable-root projection returned no object")
    return value


def require_managed_baseline(
    members: list[dict[str, Any]],
    sql: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    expected = {"pg-test-1", "pg-test-2", "pg-test-3"}
    by_name = {str(row.get("member")): row for row in members}
    if set(by_name) != expected:
        raise LabError("managed Patroni membership drifted")
    primaries = [
        name
        for name, row in by_name.items()
        if row.get("role") == "primary" and row.get("state") == "running"
    ]
    if primaries != [requirements["target"]["managed_primary"]]:
        raise LabError("managed baseline does not have pg-test-1 as sole primary")
    if any(
        row.get("role") != "replica"
        or row.get("state") != "streaming"
        for name, row in by_name.items()
        if name != primaries[0]
    ):
        raise LabError("managed baseline does not have two streaming replicas")
    if sql.get("in_recovery") is not False:
        raise LabError("managed SQL endpoint is not primary")
    if sql.get("cluster_name") != requirements["target"]["cluster"]:
        raise LabError("managed SQL cluster name drifted")
    if sql.get("activity", {}).get("chapter_fixture_sessions") != 0:
        raise LabError("chapter 34 fixture sessions exist on managed PostgreSQL")


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
        requirements = read_json(args.requirements)
        target = requirements["target"]
        observer = str(target["observer_address"])
        primary = str(target["managed_primary_address"])
        members = capture_patroni(
            args.ssh_user,
            observer,
            str(target["cluster"]),
        )
        sql = capture_sql(args.ssh_user, primary)
        roots = capture_disposable_roots(args.ssh_user, observer)
        require_managed_baseline(members, sql, requirements)
        value = {
            "schema": "pg36-ch34-managed-capture-v1",
            "captured_at": utc_now(),
            "phase": args.phase,
            "target": target["id"],
            "patroni": {
                "cluster": target["cluster"],
                "members": members,
            },
            "postgres": sql,
            "disposable_host": {
                "member": target["observer"],
                "address": observer,
                "matching_roots": roots["matching_roots"],
                "effective_uid": roots["effective_uid"],
            },
            "mutation": "none",
        }
        write_json(args.output, value)
    except (KeyError, TypeError, LabError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
