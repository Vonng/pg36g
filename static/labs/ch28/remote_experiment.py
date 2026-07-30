#!/usr/bin/env python3
"""Run the bounded chapter 28 maintenance experiment on the Pigsty meta node."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


DATABASE = "pg36_maintenance"
ROLE = "dbuser_pg36maint"
PRIMARY_ADDRESS = "10.10.10.11"
MARKER_PREFIX = "pg36-ch28-disposable-maintenance-fixture-v1"
HOLDER_APPLICATION = "pg36-ch28-old-snapshot"


class ExperimentError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        env=env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        raise ExperimentError(
            f"command failed ({completed.returncode}): {' '.join(command[:2])}: "
            f"{completed.stderr.strip()[-2400:]}"
        )
    return completed


def admin_connection(database: str, application: str) -> str:
    return f"service=pg-test-1 dbname={database} application_name={application}"


def fixture_connection(application: str) -> str:
    return (
        f"host={PRIMARY_ADDRESS} port=5432 dbname={DATABASE} "
        f"user={ROLE} sslmode=disable application_name={application}"
    )


def psql(
    connection: str,
    *,
    sql: str,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "psql",
            "-X",
            "-w",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            "--no-psqlrc",
            "--dbname",
            connection,
            "--file",
            "-",
        ],
        env=env,
        input_text=sql,
        timeout=timeout,
        check=check,
    )


def parse_single_json(text: str, label: str) -> Any:
    rows = [
        line.strip()
        for line in text.splitlines()
        if line.lstrip().startswith(("{", "["))
    ]
    for row in reversed(rows):
        try:
            return json.loads(row, parse_float=Decimal)
        except json.JSONDecodeError:
            continue
    raise ExperimentError(f"{label} did not return one JSON value")


def json_psql(
    connection: str,
    sql: str,
    label: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> Any:
    prefix = "\\pset format unaligned\n\\pset tuples_only on\n"
    completed = psql(
        connection,
        sql=prefix + sql,
        env=env,
        timeout=timeout,
    )
    return parse_single_json(completed.stdout, label)


def decimal_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=decimal_default,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relation_snapshot(label: str) -> dict[str, Any]:
    connection = admin_connection(DATABASE, f"pg36-ch28-snapshot-{label}")
    psql(connection, sql="SELECT pg_stat_force_next_flush();\n", timeout=20)
    sql = r"""
WITH tuple_info AS (
  SELECT to_jsonb(p) AS value
  FROM pgstattuple('maint.churn'::regclass) AS p
), vm AS (
  SELECT to_jsonb(v) AS value
  FROM pg_visibility_map_summary('maint.churn'::regclass) AS v
), cls AS (
  SELECT
    c.oid,
    age(c.relfrozenxid) AS relfrozenxid_age,
    age(c.relminmxid) AS relminmxid_age,
    c.reltuples::bigint AS planner_rows,
    c.relpages
  FROM pg_class c
  WHERE c.oid = 'maint.churn'::regclass
), stats AS (
  SELECT
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_tup_newpage_upd,
    vacuum_count,
    analyze_count,
    autovacuum_count,
    autoanalyze_count,
    last_vacuum,
    last_analyze
  FROM pg_stat_user_tables
  WHERE relid = 'maint.churn'::regclass
)
SELECT jsonb_build_object(
  'captured_at', clock_timestamp(),
  'label', '__LABEL__',
  'relation_bytes', pg_relation_size('maint.churn'::regclass),
  'total_relation_bytes', pg_total_relation_size('maint.churn'::regclass),
  'fsm_available_bytes', (
    SELECT coalesce(sum(avail), 0)
    FROM pg_freespace('maint.churn'::regclass)
  ),
  'tuple_physical', (SELECT value FROM tuple_info),
  'visibility_map', (SELECT value FROM vm),
  'catalog', (SELECT to_jsonb(cls) FROM cls),
  'cumulative_stats', (SELECT to_jsonb(stats) FROM stats),
  'current_rows', (SELECT count(*) FROM maint.churn)
);
""".replace("__LABEL__", label)
    result = json_psql(connection, sql, f"relation snapshot {label}")
    if not isinstance(result, dict):
        raise ExperimentError(f"invalid relation snapshot {label}")
    return result


def poll_holder() -> dict[str, Any]:
    sql = rf"""
SELECT coalesce(
  (
    SELECT jsonb_build_object(
      'pid', pid,
      'datname', datname,
      'usename', usename,
      'application_name', application_name,
      'state', state,
      'wait_event_type', wait_event_type,
      'wait_event', wait_event,
      'backend_xid', backend_xid::text,
      'backend_xmin', backend_xmin::text,
      'xact_age_seconds',
        extract(epoch FROM clock_timestamp() - xact_start)
    )
    FROM pg_stat_activity
    WHERE datname = '{DATABASE}'
      AND usename = '{ROLE}'
      AND application_name = '{HOLDER_APPLICATION}'
  ),
  '{{}}'::jsonb
);
"""
    for _ in range(100):
        row = json_psql(
            admin_connection("postgres", "pg36-ch28-holder-poll"),
            sql,
            "holder poll",
            timeout=15,
        )
        if (
            row.get("backend_xmin")
            and row.get("wait_event") == "PgSleep"
            and row.get("state") == "active"
        ):
            return row
        time.sleep(0.1)
    raise ExperimentError("old-snapshot holder did not expose backend_xmin")


def progress_snapshot() -> list[dict[str, Any]]:
    sql = rf"""
SELECT coalesce(
  jsonb_agg(
    jsonb_build_object(
      'captured_at', clock_timestamp(),
      'pid', pid,
      'phase', phase,
      'heap_blks_total', heap_blks_total,
      'heap_blks_scanned', heap_blks_scanned,
      'heap_blks_vacuumed', heap_blks_vacuumed,
      'index_vacuum_count', index_vacuum_count,
      'max_dead_tuple_bytes', max_dead_tuple_bytes,
      'dead_tuple_bytes', dead_tuple_bytes,
      'num_dead_item_ids', num_dead_item_ids,
      'indexes_total', indexes_total,
      'indexes_processed', indexes_processed,
      'delay_time_ms', delay_time
    )
    ORDER BY pid
  ),
  '[]'::jsonb
)
FROM pg_stat_progress_vacuum
WHERE datname = '{DATABASE}'
  AND relid = 'maint.churn'::regclass;
"""
    value = json_psql(
        admin_connection(DATABASE, "pg36-ch28-progress-poll"),
        sql,
        "vacuum progress",
        timeout=15,
    )
    if not isinstance(value, list):
        raise ExperimentError("invalid progress sample")
    return value


def run_vacuum(label: str, freeze: bool, output_dir: Path) -> dict[str, Any]:
    options = "FREEZE, ANALYZE, VERBOSE" if freeze else "ANALYZE, VERBOSE"
    sql = (
        "\\set ON_ERROR_STOP on\n"
        "SET vacuum_cost_delay = '10ms';\n"
        "SET vacuum_cost_limit = 20;\n"
        "SET track_cost_delay_timing = on;\n"
        f"VACUUM ({options}) maint.churn;\n"
    )
    command = [
        "psql",
        "-X",
        "-w",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
        "--no-psqlrc",
        "--dbname",
        admin_connection(DATABASE, f"pg36-ch28-vacuum-{label}"),
        "--file",
        "-",
    ]
    started_at = utc_now()
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    process.stdin.write(sql)
    process.stdin.close()
    samples: list[dict[str, Any]] = []
    while process.poll() is None:
        rows = progress_snapshot()
        samples.extend(rows)
        time.sleep(0.05)
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    elapsed = time.monotonic() - started
    ended_at = utc_now()
    (output_dir / f"{label}-vacuum.stdout").write_text(stdout, encoding="utf-8")
    (output_dir / f"{label}-vacuum.stderr").write_text(stderr, encoding="utf-8")
    (output_dir / f"{label}-vacuum.stdout").chmod(0o600)
    (output_dir / f"{label}-vacuum.stderr").chmod(0o600)
    if process.returncode != 0:
        raise ExperimentError(
            f"{label} VACUUM failed ({process.returncode}): {stderr[-2000:]}"
        )
    phases = sorted({row["phase"] for row in samples})
    return {
        "label": label,
        "freeze": freeze,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": elapsed,
        "progress_sample_count": len(samples),
        "progress_phases": phases,
        "progress_samples": samples,
        "session_local_cost_controls": {
          "vacuum_cost_delay": "10ms",
          "vacuum_cost_limit": 20,
          "track_cost_delay_timing": "on"
        },
        "persistent_setting_change": False,
    }


def start_holder(fixture_env: dict[str, str], output_dir: Path) -> subprocess.Popen[str]:
    sql = r"""
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM maint.churn;
SELECT pg_backend_pid();
SELECT pg_sleep(300);
COMMIT;
"""
    stdout_file = (output_dir / "old-snapshot.stdout").open("w", encoding="utf-8")
    stderr_file = (output_dir / "old-snapshot.stderr").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "psql",
            "-X",
            "-w",
            "--quiet",
            "--set=ON_ERROR_STOP=1",
            "--no-psqlrc",
            "--dbname",
            fixture_connection(HOLDER_APPLICATION),
            "--file",
            "-",
        ],
        env=fixture_env,
        stdin=subprocess.PIPE,
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
    )
    stdout_file.close()
    stderr_file.close()
    assert process.stdin is not None
    process.stdin.write(sql)
    process.stdin.close()
    return process


def release_holder(pid: int, process: subprocess.Popen[str]) -> dict[str, Any]:
    sql = rf"""
WITH target AS (
  SELECT pid
  FROM pg_stat_activity
  WHERE pid = {pid}
    AND datname = '{DATABASE}'
    AND usename = '{ROLE}'
    AND application_name = '{HOLDER_APPLICATION}'
    AND backend_xmin IS NOT NULL
), terminated AS (
  SELECT pg_terminate_backend(pid) AS ok FROM target
)
SELECT jsonb_build_object(
  'matched_sessions', (SELECT count(*) FROM target),
  'terminated_sessions', (
    SELECT count(*) FROM terminated WHERE ok
  )
);
"""
    result = json_psql(
        admin_connection("postgres", "pg36-ch28-holder-release"),
        sql,
        "holder release",
        timeout=20,
    )
    try:
        return_code = process.wait(timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise ExperimentError("holder client did not exit after exact termination") from exc
    result["client_return_code"] = return_code
    remaining = json_psql(
        admin_connection("postgres", "pg36-ch28-holder-verify"),
        rf"""
SELECT jsonb_build_object(
  'remaining_sessions', count(*),
  'remaining_with_xmin',
    count(*) FILTER (WHERE backend_xmin IS NOT NULL)
)
FROM pg_stat_activity
WHERE datname = '{DATABASE}'
  AND application_name = '{HOLDER_APPLICATION}';
""",
        "holder release verification",
    )
    result.update(remaining)
    if (
        result["matched_sessions"] != 1
        or result["terminated_sessions"] != 1
        or result["remaining_sessions"] != 0
    ):
        raise ExperimentError(f"exact holder release failed: {result}")
    return result


def timed_check(connection: str, sql: str, label: str) -> dict[str, Any]:
    started_at = utc_now()
    started = time.monotonic()
    completed = psql(connection, sql=sql, timeout=180)
    return {
        "label": label,
        "started_at": started_at,
        "ended_at": utc_now(),
        "elapsed_seconds": time.monotonic() - started,
        "return_code": completed.returncode,
    }


def index_state() -> dict[str, Any]:
    sql = r"""
SELECT jsonb_build_object(
  'oid', c.oid,
  'relname', c.relname,
  'relfilenode', pg_relation_filenode(c.oid),
  'relation_bytes', pg_relation_size(c.oid),
  'indisready', i.indisready,
  'indisvalid', i.indisvalid,
  'indislive', i.indislive,
  'matching_named_indexes', (
    SELECT count(*) FROM pg_class x
    JOIN pg_namespace n ON n.oid = x.relnamespace
    WHERE n.nspname = 'maint'
      AND x.relname = 'churn_status_idx'
  ),
  'invalid_fixture_indexes', (
    SELECT count(*)
    FROM pg_index x
    JOIN pg_class y ON y.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = y.relnamespace
    WHERE n.nspname = 'maint'
      AND (NOT x.indisready OR NOT x.indisvalid OR NOT x.indislive)
  ),
  'concurrent_artifacts', (
    SELECT coalesce(jsonb_agg(x.relname ORDER BY x.relname), '[]'::jsonb)
    FROM pg_class x
    JOIN pg_namespace n ON n.oid = x.relnamespace
    WHERE n.nspname = 'maint'
      AND x.relkind = 'i'
      AND x.relname ~ '(_ccnew|_ccold)'
  )
)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
WHERE n.nspname = 'maint'
  AND c.relname = 'churn_status_idx';
"""
    return json_psql(
        admin_connection(DATABASE, "pg36-ch28-index-state"),
        sql,
        "index state",
    )


def partition_manifest(relation: str) -> dict[str, Any]:
    sql = rf"""
SELECT jsonb_build_object(
  'relation', '{relation}',
  'rows', count(*),
  'min_id', min(id),
  'max_id', max(id),
  'amount_sum', sum(amount),
  'logical_digest', md5(
    string_agg(
      id::text || ':' || event_date::text || ':' ||
      amount::text || ':' || payload,
      '|' ORDER BY id
    )
  )
)
FROM {relation};
"""
    return json_psql(
        admin_connection(DATABASE, "pg36-ch28-partition-manifest"),
        sql,
        f"partition manifest {relation}",
    )


def archive_round_trip(output_dir: Path) -> dict[str, Any]:
    before = partition_manifest("maint.events_2024")
    detach = timed_check(
        admin_connection(DATABASE, "pg36-ch28-detach"),
        "ALTER TABLE maint.events DETACH PARTITION maint.events_2024 CONCURRENTLY;\n",
        "detach-partition-concurrently",
    )
    topology = json_psql(
        admin_connection(DATABASE, "pg36-ch28-detach-verify"),
        r"""
SELECT jsonb_build_object(
  'still_attached', EXISTS (
    SELECT 1 FROM pg_inherits
    WHERE inhparent = 'maint.events'::regclass
      AND inhrelid = 'maint.events_2024'::regclass
  ),
  'parent_rows', (SELECT count(*) FROM maint.events),
  'standalone_rows', (SELECT count(*) FROM maint.events_2024)
);
""",
        "partition topology after detach",
    )
    export = psql(
        admin_connection(DATABASE, "pg36-ch28-archive-export"),
        sql=r"""
\copy (SELECT id,event_date,amount,payload FROM maint.events_2024 ORDER BY id) TO STDOUT WITH (FORMAT csv)
""",
        timeout=120,
    )
    archive_bytes = export.stdout.encode("utf-8")
    archive_path = output_dir / "events-2024.csv"
    archive_path.write_bytes(archive_bytes)
    archive_path.chmod(0o600)
    psql(
        admin_connection(DATABASE, "pg36-ch28-restore-create"),
        sql=r"""
CREATE TABLE maint.events_restore_check
  (LIKE maint.events_2024 INCLUDING ALL);
""",
    )
    # Use a client-side \copy so the archive remains in the private evidence tree.
    restore_script = (
        "\\set ON_ERROR_STOP on\n"
        f"\\copy maint.events_restore_check "
        f"(id,event_date,amount,payload) FROM '{archive_path}' WITH (FORMAT csv)\n"
    )
    psql(
        admin_connection(DATABASE, "pg36-ch28-archive-restore"),
        sql=restore_script,
        timeout=120,
    )
    after = partition_manifest("maint.events_restore_check")
    comparable_before = {
        key: before[key]
        for key in ("rows", "min_id", "max_id", "amount_sum", "logical_digest")
    }
    comparable_after = {
        key: after[key]
        for key in ("rows", "min_id", "max_id", "amount_sum", "logical_digest")
    }
    validated = comparable_before == comparable_after
    if (
        topology != {
            "still_attached": False,
            "parent_rows": 5000,
            "standalone_rows": 10000,
        }
        or not validated
        or len(archive_bytes) == 0
    ):
        raise ExperimentError(
            f"partition archive validation failed: {topology}, {validated}"
        )
    psql(
        admin_connection(DATABASE, "pg36-ch28-partition-retire"),
        sql=r"""
DROP TABLE maint.events_restore_check;
DROP TABLE maint.events_2024;
""",
    )
    post_drop = json_psql(
        admin_connection(DATABASE, "pg36-ch28-partition-post-drop"),
        r"""
SELECT jsonb_build_object(
  'expired_partition_absent', to_regclass('maint.events_2024') IS NULL,
  'restore_check_absent', to_regclass('maint.events_restore_check') IS NULL,
  'parent_rows', (SELECT count(*) FROM maint.events)
);
""",
        "partition post-drop",
    )
    return {
        "manifest_before_detach": before,
        "detach": detach,
        "topology_after_detach": topology,
        "archive": {
            "filename": archive_path.name,
            "bytes": len(archive_bytes),
            "sha256": sha256_bytes(archive_bytes),
        },
        "restore_manifest": after,
        "round_trip_validated": validated,
        "post_drop": post_drop,
        "drop_performed_only_after_validation": True,
    }


def create_fixture(
    run_id: str,
    password: str,
    fixture_env: dict[str, str],
) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    create_sql = rf"""
\set ON_ERROR_STOP on
CREATE ROLE {ROLE}
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  INHERIT
  PASSWORD :'fixture_password';
GRANT dbrole_readwrite TO {ROLE} WITH INHERIT FALSE, SET FALSE;
COMMENT ON ROLE {ROLE} IS '{marker}';
CREATE DATABASE {DATABASE}
  OWNER {ROLE}
  TEMPLATE template0
  ENCODING 'UTF8'
  ALLOW_CONNECTIONS false;
REVOKE CONNECT ON DATABASE {DATABASE} FROM PUBLIC;
GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE};
ALTER DATABASE {DATABASE} ALLOW_CONNECTIONS true;
COMMENT ON DATABASE {DATABASE} IS '{marker}';
"""
    command = [
        "psql",
        "-X",
        "-w",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
        "--set",
        f"fixture_password={password}",
        "--no-psqlrc",
        "--dbname",
        admin_connection("postgres", "pg36-ch28-create"),
        "--file",
        "-",
    ]
    run(command, input_text=create_sql, timeout=60)
    psql(
        admin_connection(DATABASE, "pg36-ch28-extensions"),
        sql=r"""
CREATE EXTENSION amcheck;
CREATE EXTENSION pg_freespacemap;
CREATE EXTENSION pg_visibility;
CREATE EXTENSION pgstattuple;
""",
        timeout=60,
    )
    setup_sql = r"""
CREATE SCHEMA maint AUTHORIZATION CURRENT_USER;

CREATE TABLE maint.churn (
  id bigint PRIMARY KEY,
  status integer NOT NULL,
  revision integer NOT NULL DEFAULT 0,
  payload text NOT NULL
) WITH (
  fillfactor = 70,
  autovacuum_enabled = false
);

INSERT INTO maint.churn (id, status, payload)
SELECT g, g % 17, repeat(md5(g::text), 20)
FROM generate_series(1, 60000) AS g;

CREATE INDEX churn_status_idx ON maint.churn (status, id);

CREATE TABLE maint.events (
  id bigint NOT NULL,
  event_date date NOT NULL,
  amount numeric(12,2) NOT NULL,
  payload text NOT NULL
) PARTITION BY RANGE (event_date);

CREATE TABLE maint.events_2024 PARTITION OF maint.events
  FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE maint.events_2026 PARTITION OF maint.events
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

INSERT INTO maint.events
SELECT
  g,
  DATE '2024-01-01' + ((g - 1) % 366),
  (g % 10000)::numeric / 100,
  md5(g::text)
FROM generate_series(1, 10000) AS g;

INSERT INTO maint.events
SELECT
  10000 + g,
  DATE '2026-01-01' + ((g - 1) % 365),
  (g % 10000)::numeric / 100,
  md5((10000 + g)::text)
FROM generate_series(1, 5000) AS g;

ANALYZE maint.churn;
ANALYZE maint.events_2024;
ANALYZE maint.events_2026;
ANALYZE maint.events;
"""
    psql(
        fixture_connection("pg36-ch28-setup"),
        sql=setup_sql,
        env=fixture_env,
        timeout=240,
    )
    psql(
        admin_connection(DATABASE, "pg36-ch28-baseline-vacuum"),
        sql="VACUUM (FREEZE, ANALYZE) maint.churn;\n",
        timeout=240,
    )
    psql(
        admin_connection(DATABASE, "pg36-ch28-reset-stats"),
        sql=(
            "SELECT pg_stat_reset_single_table_counters("
            "'maint.churn'::regclass);\n"
        ),
    )
    initialized = json_psql(
        admin_connection(DATABASE, "pg36-ch28-setup-check"),
        r"""
SELECT jsonb_build_object(
  'churn_rows', (SELECT count(*) FROM maint.churn),
  'expired_rows', (SELECT count(*) FROM maint.events_2024),
  'current_rows', (SELECT count(*) FROM maint.events_2026),
  'parent_rows', (SELECT count(*) FROM maint.events),
  'autovacuum_enabled', (
    SELECT coalesce(
      (
        SELECT option_value::boolean
        FROM pg_options_to_table(c.reloptions)
        WHERE option_name = 'autovacuum_enabled'
      ),
      true
    )
    FROM pg_class c WHERE c.oid = 'maint.churn'::regclass
  )
);
""",
        "fixture initialization",
    )
    expected = {
        "churn_rows": 60000,
        "expired_rows": 10000,
        "current_rows": 5000,
        "parent_rows": 15000,
        "autovacuum_enabled": False,
    }
    if initialized != expected:
        raise ExperimentError(f"fixture initialization mismatch: {initialized}")
    return {"marker": marker, "initialized": initialized}


def cleanup_fixture(run_id: str) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    inspect_sql = rf"""
SELECT jsonb_build_object(
  'database_exists', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'role_exists', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'
  ),
  'role_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{ROLE}'
  ),
  'sessions', (
    SELECT coalesce(
      jsonb_agg(
        jsonb_build_object(
          'pid', pid,
          'usename', usename,
          'application_name', application_name,
          'state', state,
          'backend_xmin', backend_xmin::text
        )
        ORDER BY pid
      ),
      '[]'::jsonb
    )
    FROM pg_stat_activity WHERE datname = '{DATABASE}'
  )
);
"""
    observed = json_psql(
        admin_connection("postgres", "pg36-ch28-cleanup-inspect"),
        inspect_sql,
        "cleanup inspection",
    )
    if observed["database_exists"] and observed["database_marker"] != marker:
        raise ExperimentError("database marker mismatch; refusing cleanup")
    if observed["role_exists"] and observed["role_marker"] != marker:
        raise ExperimentError("role marker mismatch; refusing cleanup")
    lab_sessions = [
        row
        for row in observed["sessions"]
        if row["usename"] == ROLE
        and row["application_name"].startswith("pg36-ch28-")
    ]
    unrelated = [
        row for row in observed["sessions"] if row not in lab_sessions
    ]
    if unrelated:
        raise ExperimentError(
            f"unrelated sessions prevent ordinary cleanup: {unrelated}"
        )
    terminated_on_failure = 0
    if lab_sessions:
        pid_list = ",".join(str(row["pid"]) for row in lab_sessions)
        result = json_psql(
            admin_connection("postgres", "pg36-ch28-cleanup-owned"),
            rf"""
SELECT jsonb_build_object(
  'terminated', count(*) FILTER (WHERE ok)
)
FROM (
  SELECT pg_terminate_backend(pid) AS ok
  FROM pg_stat_activity
  WHERE pid = ANY (ARRAY[{pid_list}])
    AND datname = '{DATABASE}'
    AND usename = '{ROLE}'
    AND application_name LIKE 'pg36-ch28-%'
) AS q;
""",
            "owned-session cleanup",
        )
        terminated_on_failure = result["terminated"]
    if observed["database_exists"]:
        for _ in range(50):
            remaining = json_psql(
                admin_connection("postgres", "pg36-ch28-cleanup-wait"),
                rf"""
SELECT jsonb_build_object(
  'sessions', count(*)
)
FROM pg_stat_activity WHERE datname = '{DATABASE}';
""",
                "cleanup session wait",
            )
            if remaining["sessions"] == 0:
                break
            time.sleep(0.1)
        else:
            raise ExperimentError("fixture sessions did not exit")
        psql(
            admin_connection("postgres", "pg36-ch28-cleanup-drop-db"),
            sql=rf"""
ALTER DATABASE {DATABASE} ALLOW_CONNECTIONS false;
DROP DATABASE {DATABASE};
""",
            timeout=60,
        )
    if observed["role_exists"]:
        psql(
            admin_connection("postgres", "pg36-ch28-cleanup-drop-role"),
            sql=f"DROP ROLE {ROLE};\n",
            timeout=30,
        )
    verified = json_psql(
        admin_connection("postgres", "pg36-ch28-cleanup-verify"),
        rf"""
SELECT jsonb_build_object(
  'database_absent', NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'role_absent', NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'
  ),
  'sessions_remaining', (
    SELECT count(*) FROM pg_stat_activity WHERE datname = '{DATABASE}'
  )
);
""",
        "cleanup verification",
    )
    return {
        "marker_matched": True,
        "ordinary_drop": True,
        "force_drop_used": False,
        "unrelated_sessions_terminated": 0,
        "owned_sessions_terminated_during_finally": terminated_on_failure,
        **verified,
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, mode=0o700)
    requirements = json.loads(
        (source_dir / "requirements.json").read_text(encoding="utf-8")
    )
    run_id = str(uuid.uuid4())
    password = secrets.token_urlsafe(32)
    fixture_env = os.environ.copy()
    fixture_env["PGPASSWORD"] = password
    holder: subprocess.Popen[str] | None = None
    cleanup: dict[str, Any] | None = None
    evidence: dict[str, Any] = {
        "schema": "pg36-ch28-maintenance-evidence-v1",
        "release": "1.0-sandbox",
        "captured_at": utc_now(),
        "run_id": run_id,
        "target": requirements["target"],
        "status": "running",
        "production_ch28_gate": "pending",
    }
    try:
        fixture = create_fixture(run_id, password, fixture_env)
        baseline = relation_snapshot("baseline")
        holder = start_holder(fixture_env, output_dir)
        holder_observed = poll_holder()
        churn = json_psql(
            fixture_connection("pg36-ch28-churn"),
            r"""
WITH updated AS (
  UPDATE maint.churn
  SET payload = reverse(payload),
      revision = revision + 1
  WHERE id <= 40000
  RETURNING 1
), deleted AS (
  DELETE FROM maint.churn
  WHERE id BETWEEN 40001 AND 50000
  RETURNING 1
)
SELECT jsonb_build_object(
  'updated_rows', (SELECT count(*) FROM updated),
  'deleted_rows', (SELECT count(*) FROM deleted)
);
""",
            "fixture churn",
            env=fixture_env,
            timeout=240,
        )
        post_churn = json_psql(
            fixture_connection("pg36-ch28-churn-count"),
            r"""
SELECT jsonb_build_object(
  'remaining_rows', count(*)
)
FROM maint.churn;
""",
            "post-commit churn count",
            env=fixture_env,
            timeout=30,
        )
        churn.update(post_churn)
        psql(
            fixture_connection("pg36-ch28-churn-analyze"),
            sql="ANALYZE maint.churn;\n",
            env=fixture_env,
            timeout=60,
        )
        after_churn = relation_snapshot("after-churn")
        blocked_vacuum = run_vacuum(
            "old-snapshot-present", False, output_dir
        )
        after_blocked = relation_snapshot("after-vacuum-with-old-snapshot")
        holder_release = release_holder(int(holder_observed["pid"]), holder)
        holder = None
        release_vacuum = run_vacuum(
            "old-snapshot-released", True, output_dir
        )
        after_release = relation_snapshot("after-release-vacuum-freeze")

        dead_with_holder = int(
            after_blocked["tuple_physical"]["dead_tuple_count"]
        )
        dead_after_release = int(
            after_release["tuple_physical"]["dead_tuple_count"]
        )
        if dead_with_holder <= 0 or dead_after_release != 0:
            raise ExperimentError(
                "old-snapshot reclamation hypothesis was not observed: "
                f"{dead_with_holder=} {dead_after_release=}"
            )
        if churn != {
            "updated_rows": 40000,
            "deleted_rows": 10000,
            "remaining_rows": 50000,
        }:
            raise ExperimentError(f"unexpected churn result: {churn}")

        checks = {
            "bt_index_check": timed_check(
                admin_connection(DATABASE, "pg36-ch28-amcheck-light"),
                (
                    "SELECT bt_index_check("
                    "'maint.churn_pkey'::regclass, true, true);\n"
                ),
                "bt_index_check-heapallindexed-checkunique",
            ),
            "bt_index_parent_check": timed_check(
                admin_connection(DATABASE, "pg36-ch28-amcheck-deep"),
                (
                    "SELECT bt_index_parent_check("
                    "'maint.churn_pkey'::regclass, true, true, true);\n"
                ),
                "bt_index_parent_check-heapallindexed-rootdescend-checkunique",
            ),
        }
        index_before = index_state()
        concurrent_reindex = timed_check(
            admin_connection(DATABASE, "pg36-ch28-reindex"),
            "REINDEX INDEX CONCURRENTLY maint.churn_status_idx;\n",
            "reindex-index-concurrently",
        )
        index_after = index_state()
        if (
            index_before["relfilenode"] == index_after["relfilenode"]
            or index_after["matching_named_indexes"] != 1
            or index_after["invalid_fixture_indexes"] != 0
            or index_after["concurrent_artifacts"] != []
            or not index_after["indisready"]
            or not index_after["indisvalid"]
            or not index_after["indislive"]
        ):
            raise ExperimentError("concurrent reindex postconditions failed")

        partition = archive_round_trip(output_dir)
        evidence.update(
            {
                "status": "passed",
                "environment": {
                    "cluster": "pg-test",
                    "server": PRIMARY_ADDRESS,
                    "database": DATABASE,
                    "role": ROLE,
                    "fixture_marker": fixture["marker"],
                },
                "safety": {
                    "production_data_touched": False,
                    "production_traffic_touched": False,
                    "persistent_configuration_change": False,
                    "cluster_autovacuum_changed": False,
                    "fixture_table_autovacuum_enabled": False,
                    "vacuum_full_used": False,
                    "force_drop_used": False,
                },
                "fixture": fixture["initialized"],
                "old_snapshot": {
                    "observed": holder_observed,
                    "released": holder_release,
                },
                "churn": churn,
                "snapshots": {
                    "baseline": baseline,
                    "after_churn": after_churn,
                    "after_vacuum_with_old_snapshot": after_blocked,
                    "after_release_vacuum_freeze": after_release,
                },
                "vacuum_runs": {
                    "with_old_snapshot": blocked_vacuum,
                    "after_release": release_vacuum,
                },
                "integrity_checks": checks,
                "concurrent_reindex": {
                    "operation": concurrent_reindex,
                    "before": index_before,
                    "after": index_after,
                },
                "partition_retirement": partition,
            }
        )
    finally:
        if holder is not None and holder.poll() is None:
            # Exact final cleanup will only terminate marker-bound chapter sessions.
            pass
        cleanup = cleanup_fixture(run_id)
        evidence["cleanup"] = cleanup
        if evidence.get("status") == "passed":
            if (
                cleanup.get("database_absent") is not True
                or cleanup.get("role_absent") is not True
                or cleanup.get("sessions_remaining") != 0
                or cleanup.get("unrelated_sessions_terminated") != 0
            ):
                evidence["status"] = "failed-cleanup"
        write_json(output_dir / "maintenance-evidence.json", evidence)
    if evidence["status"] != "passed":
        raise ExperimentError(f"experiment ended with {evidence['status']}")
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run_id,
                "dead_with_old_snapshot": evidence["snapshots"][
                    "after_vacuum_with_old_snapshot"
                ]["tuple_physical"]["dead_tuple_count"],
                "dead_after_release": evidence["snapshots"][
                    "after_release_vacuum_freeze"
                ]["tuple_physical"]["dead_tuple_count"],
                "partition_round_trip": True,
                "cleanup": "verified",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ExperimentError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"chapter 28 remote experiment failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
