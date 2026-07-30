#!/usr/bin/env python3
"""Capture a read-only projection around the chapter 35 sandbox."""

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
    SELECT count(*) FILTER (
        WHERE application_name LIKE 'pg36-ch35-%'
    )::int AS chapter_fixture_sessions
    FROM pg_catalog.pg_stat_activity
)
SELECT jsonb_build_object(
    'server_version', current_setting('server_version'),
    'cluster_name', current_setting('cluster_name'),
    'system_identifier', control.system_identifier,
    'timeline', checkpoint.timeline_id,
    'in_recovery', pg_is_in_recovery(),
    'data_checksums', current_setting('data_checksums'),
    'chapter_fixture_sessions', activity.chapter_fixture_sessions,
    'database_collation_version',
        (
            SELECT datcollversion
            FROM pg_catalog.pg_database
            WHERE datname = current_database()
        ),
    'database_collation_actual_version',
        pg_catalog.pg_database_collation_actual_version(
            (
                SELECT oid
                FROM pg_catalog.pg_database
                WHERE datname = current_database()
            )
        )
)
FROM control, checkpoint, activity;
"""


ROOT_PROJECTION = r"""
import glob
import json
import os
from pathlib import Path

roots = []
for raw in glob.glob("/tmp/pg36-ch35-forensics-*"):
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
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise LabError("patronictl member row is not an object")
        lower = {
            str(key).lower().replace(" ", "_"): value
            for key, value in row.items()
        }
        result.append(
            {
                "member": lower.get("member"),
                "host": lower.get("host"),
                "role": normalize_role(lower.get("role")),
                "state": str(lower.get("state", "")).lower(),
                "timeline": lower.get("tl", lower.get("timeline")),
            }
        )
    result.sort(key=lambda row: str(row["member"]))
    return result


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


def capture_roots(user: str, host: str) -> dict[str, Any]:
    raw = run(
        ssh_base(user, host)
        + ["sudo", "-n", "-iu", "postgres", "python3", "-"],
        stdin=ROOT_PROJECTION,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError("forensic-root projection returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError("forensic-root projection returned no object")
    return value


def require_baseline(
    members: list[dict[str, Any]],
    sql: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    by_name = {str(row.get("member")): row for row in members}
    if set(by_name) != {"pg-test-1", "pg-test-2", "pg-test-3"}:
        raise LabError("managed Patroni membership drifted")
    if (
        by_name["pg-test-1"].get("role") != "primary"
        or by_name["pg-test-1"].get("state") != "running"
        or any(
            by_name[name].get("role") != "replica"
            or by_name[name].get("state") != "streaming"
            for name in ("pg-test-2", "pg-test-3")
        )
    ):
        raise LabError("managed baseline is not one primary and two replicas")
    if (
        sql.get("in_recovery") is not False
        or sql.get("cluster_name")
        != requirements["target"]["cluster"]
        or sql.get("chapter_fixture_sessions") != 0
    ):
        raise LabError("managed SQL baseline drifted")


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
        members = capture_patroni(
            args.ssh_user,
            str(target["observer_address"]),
            str(target["cluster"]),
        )
        sql = capture_sql(
            args.ssh_user,
            str(target["managed_primary_address"]),
        )
        roots = capture_roots(
            args.ssh_user,
            str(target["observer_address"]),
        )
        require_baseline(members, sql, requirements)
        write_json(
            args.output,
            {
                "schema": "pg36-ch35-managed-capture-v1",
                "captured_at": utc_now(),
                "phase": args.phase,
                "target": target["id"],
                "patroni": {
                    "cluster": target["cluster"],
                    "members": members,
                },
                "postgres": sql,
                "forensic_host": {
                    "member": target["observer"],
                    "address": target["observer_address"],
                    "matching_roots": roots["matching_roots"],
                    "effective_uid": roots["effective_uid"],
                },
                "mutation": "none",
            },
        )
    except (KeyError, TypeError, LabError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
