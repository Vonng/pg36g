#!/usr/bin/env python3
"""Run the guarded chapter 22 pooling, routing, and switchover lab."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import random
import stat
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
import yaml

from capture import capture_snapshot
from common import (
    LabError,
    current_leader,
    patroni_list,
    pgbouncer_config,
    pgbouncer_pools,
    project_pgbouncer_config,
    read_json,
    reconnect_database,
    remote_json_psql,
    remote_psql,
    set_pgbouncer_config,
    sha256,
    switchover,
    topology_index,
    topology_stable,
    utc_now,
    wait_for_topology,
    write_json,
)


OUTCOME_FILES = {"connection-run.json", "migration-effort.json"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--credential-inventory", type=Path, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--authority", required=True)
    return parser.parse_args()


def require_authority(
    args: argparse.Namespace,
    requirements: dict[str, Any],
) -> None:
    target = requirements["target"]
    if (
        args.target_token != "pg36-l2-vagrant/pg-test"
        or args.target_token != target["id"]
        or args.confirmation != "POOL_ROUTE_SWITCH_AND_RESTORE_CH22"
        or args.authority != "nonproduction-no-data-no-traffic"
        or target["production_data_permitted"] is not False
        or target["production_traffic_permitted"] is not False
    ):
        raise LabError("direct service-drill authority guard failed")
    if args.output.exists() and any(args.output.iterdir()):
        raise LabError("refusing to overwrite a non-empty evidence directory")


def baseline_pool_settings(
    requirements: dict[str, Any],
) -> dict[str, int]:
    pool = requirements["pgbouncer"]
    return {
        "default_pool_size": int(pool["default_pool_size"]),
        "reserve_pool_size": int(pool["reserve_pool_size"]),
        "reserve_pool_timeout": int(
            pool["reserve_pool_timeout_seconds"]
        ),
        "query_wait_timeout": int(
            pool["query_wait_timeout_seconds"]
        ),
    }


def override_pool_settings(
    requirements: dict[str, Any],
) -> dict[str, int]:
    values = requirements["pgbouncer"]["lab_override"]
    return {
        "default_pool_size": int(values["default_pool_size"]),
        "reserve_pool_size": int(values["reserve_pool_size"]),
        "reserve_pool_timeout": int(
            requirements["pgbouncer"]["reserve_pool_timeout_seconds"]
        ),
        "query_wait_timeout": int(
            values["query_wait_timeout_seconds"]
        ),
    }


def selected_pool_settings(
    user: str,
    host: str,
) -> dict[str, int]:
    config = pgbouncer_config(user, host)
    return {
        key: int(config[key])
        for key in (
            "default_pool_size",
            "reserve_pool_size",
            "reserve_pool_timeout",
            "query_wait_timeout",
        )
    }


def require_initial_snapshot(
    snapshot: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    if not topology_stable(snapshot["topology"], "pg-test-1"):
        raise LabError("initial topology is not the retained baseline")
    target = requirements["target"]
    if (
        snapshot.get("schema") != "pg36-ch22-service-snapshot-v1"
        or snapshot.get("target") != target["id"]
        or snapshot.get("phase") != "before"
    ):
        raise LabError("initial snapshot identity drifted")
    entry = snapshot["entry"]
    versions = entry["package_versions"]
    expected_versions = {
        "haproxy": target["haproxy_observed"],
        "pgbouncer": target["pgbouncer_observed"],
        "postgresql-18": target["postgresql_observed"],
    }
    for package, expected in expected_versions.items():
        if not str(versions.get(package, "")).startswith(expected):
            raise LabError(f"{package} version drifted from the contract")
    if not {5432, 5433, 5434, 5436, 5438, 6432, 8008}.issubset(
        set(entry["tcp_listener_ports"])
    ):
        raise LabError("required service listeners are missing")
    for name, contract in requirements["services"].items():
        actual = entry["services"].get(name, {})
        if (
            actual.get("port") != contract["port"]
            or actual.get("health_path") != contract["health_path"]
            or actual.get("expected_status") != 200
            or actual.get("mode") != "tcp"
        ):
            raise LabError(f"HAProxy service {name} drifted")
        destination = 6432 if name in {"primary", "replica"} else 5432
        if {
            row.get("destination_port")
            for row in actual.get("servers", [])
        } != {destination}:
            raise LabError(f"HAProxy destination drifted for {name}")
    expected_pool = baseline_pool_settings(requirements)
    for host, actual in snapshot["pgbouncer"].items():
        if (
            actual.get("pool_mode") != "transaction"
            or actual.get("listen_port") != 6432
            or actual.get("max_client_conn")
            != requirements["pgbouncer"]["max_client_conn"]
            or actual.get("max_prepared_statements")
            != requirements["pgbouncer"]["max_prepared_statements"]
            or {
                key: actual.get(key)
                for key in expected_pool
            }
            != expected_pool
        ):
            raise LabError(f"PgBouncer baseline drifted on {host}")
    expected_postgres = requirements["postgresql"]
    for host, actual in snapshot["postgres"].items():
        settings = actual["settings"]
        if (
            not str(actual.get("server_version", "")).startswith(
                target["postgresql_observed"]
            )
            or settings.get("max_connections")
            != expected_postgres["max_connections"]
            or settings.get("superuser_reserved_connections")
            != expected_postgres["superuser_reserved_connections"]
            or settings.get("reserved_connections")
            != expected_postgres["reserved_connections"]
            or settings.get("idle_in_transaction_session_timeout")
            != expected_postgres[
                "idle_in_transaction_session_timeout_ms"
            ]
            or settings.get("statement_timeout")
            != expected_postgres["statement_timeout_ms"]
            or settings.get("max_locks_per_transaction")
            != expected_postgres["max_locks_per_transaction"]
            or settings.get("work_mem") != "65536"
            or settings.get("temp_buffers") != "1024"
        ):
            raise LabError(f"PostgreSQL connection policy drifted on {host}")


def setup_fixture(
    source_dir: Path,
    requirements: dict[str, Any],
    user: str,
    primary_host: str,
) -> dict[str, Any]:
    role = requirements["fixture"]["login_role"]
    if role != "test":
        raise LabError("fixture role crossed its allowlist")
    existing = remote_json_psql(
        user,
        primary_host,
        "test",
        r"""
SELECT COALESCE(
  (
    SELECT json_build_object(
      'exists', true,
      'comment', shobj_description(oid, 'pg_authid'),
      'can_login', rolcanlogin,
      'superuser', rolsuper,
      'create_db', rolcreatedb,
      'create_role', rolcreaterole,
      'replication', rolreplication,
      'bypass_rls', rolbypassrls,
      'inherit', rolinherit,
      'connection_limit', rolconnlimit,
      'busy_sessions', (
        SELECT count(*) FROM pg_stat_activity
        WHERE usename = 'test'
          AND state IS DISTINCT FROM 'idle'
      )
    )
    FROM pg_authid
    WHERE rolname = 'test'
  ),
  '{"exists":false}'::json
);
""",
    )
    if not isinstance(existing, dict):
        raise LabError("fixture role projection is invalid")
    if (
        existing.get("exists") is not True
        or existing.get("comment")
        != requirements["fixture"]["login_role_comment"]
        or existing.get("can_login") is not True
        or existing.get("superuser") is not False
        or existing.get("create_db") is not False
        or existing.get("create_role") is not False
        or existing.get("replication") is not False
        or existing.get("bypass_rls") is not False
        or existing.get("inherit") is not True
        or existing.get("connection_limit") != -1
        or existing.get("busy_sessions") != 0
    ):
        raise LabError("declared fixture role is absent, busy, or unsafe")
    remote_psql(
        user,
        primary_host,
        "test",
        (source_dir / "setup.sql").read_text(encoding="utf-8"),
    )
    fixture = remote_json_psql(
        user,
        primary_host,
        "test",
        r"""
SELECT json_build_object(
  'schema', 'pg36-ch22-fixture-v1',
  'database', current_database(),
  'role', (
    SELECT json_build_object(
      'name', rolname,
      'comment', shobj_description(oid, 'pg_authid'),
      'can_login', rolcanlogin,
      'superuser', rolsuper,
      'create_db', rolcreatedb,
      'create_role', rolcreaterole,
      'replication', rolreplication,
      'bypass_rls', rolbypassrls,
      'inherit', rolinherit,
      'connection_limit', rolconnlimit
    )
    FROM pg_authid
    WHERE rolname = 'test'
  ),
  'namespace', (
    SELECT json_build_object(
      'name', nspname,
      'owner', pg_get_userbyid(nspowner),
      'comment', obj_description(oid, 'pg_namespace')
    )
    FROM pg_namespace
    WHERE nspname = 'pg36_ch22'
  ),
  'table', (
    SELECT json_build_object(
      'name', c.oid::regclass::text,
      'owner', pg_get_userbyid(c.relowner),
      'comment', obj_description(c.oid, 'pg_class')
    )
    FROM pg_class AS c
    WHERE c.oid = 'pg36_ch22.route_probe'::regclass
  ),
  'declared_role_preserved', true,
  'credential_exported', false
);
""",
    )
    if not isinstance(fixture, dict):
        raise LabError("fixture projection is invalid")
    return fixture


def load_declared_credential(
    inventory_path: Path,
    requirements: dict[str, Any],
) -> str:
    try:
        mode = stat.S_IMODE(inventory_path.stat().st_mode)
    except OSError as exc:
        raise LabError(f"cannot stat private credential inventory: {exc}") from exc
    if (
        mode != 0o600
        or not inventory_path.is_file()
        or inventory_path.is_symlink()
    ):
        raise LabError(
            "private credential inventory must be a regular mode-0600 file"
        )
    try:
        document = yaml.safe_load(
            inventory_path.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise LabError(f"cannot parse private credential inventory: {exc}") from exc
    if not isinstance(document, dict):
        raise LabError("private credential inventory is not a mapping")
    try:
        groups = document["all"]["children"]
    except (KeyError, TypeError) as exc:
        raise LabError("private inventory hierarchy drifted") from exc
    matches: list[str] = []
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        variables = group.get("vars") or {}
        if variables.get("pg_cluster") != requirements["target"]["cluster"]:
            continue
        for candidate in variables.get("pg_users") or []:
            if (
                isinstance(candidate, dict)
                and candidate.get("name")
                == requirements["fixture"]["login_role"]
                and candidate.get("pgbouncer") is True
                and isinstance(candidate.get("password"), str)
                and candidate["password"]
            ):
                matches.append(candidate["password"])
    if len(matches) != 1:
        raise LabError(
            "exactly one declared PgBouncer credential was not found"
        )
    return matches[0]


def write_service_file(
    directory: Path,
    requirements: dict[str, Any],
    password: str,
) -> Path:
    target = requirements["target"]
    fixture = requirements["fixture"]
    service_file = directory / "pg_service.conf"
    parser = configparser.ConfigParser(interpolation=None)
    for name, contract in requirements["services"].items():
        readonly = name in {"replica", "offline"}
        parser[f"pg36-ch22-{name}"] = {
            "host": str(target["entry_address"]),
            "port": str(contract["port"]),
            "dbname": fixture["database"],
            "user": fixture["login_role"],
            "password": password,
            "sslmode": "prefer",
            "target_session_attrs": (
                "read-only" if readonly else "read-write"
            ),
            "connect_timeout": "2",
            "application_name": f"pg36_ch22_{name}",
        }
    descriptor = os.open(
        service_file,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        parser.write(stream, space_around_delimiters=False)
    mode = stat.S_IMODE(service_file.stat().st_mode)
    if (
        mode != 0o600
        or not service_file.is_file()
        or service_file.is_symlink()
    ):
        raise LabError("private service file is not a regular mode-0600 file")
    return service_file


def connect(service: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        f"service=pg36-ch22-{service}",
        autocommit=autocommit,
    )


def member_by_start(
    before: dict[str, Any],
    started_at: str,
) -> str | None:
    matches = [
        host
        for host, row in before["postgres"].items()
        if row.get("postmaster_started_at") == started_at
    ]
    return matches[0] if len(matches) == 1 else None


def endpoint_probe(
    requirements: dict[str, Any],
    before: dict[str, Any],
    user: str,
) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for name in ("primary", "replica", "default", "offline"):
        with connect(name, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_is_in_recovery(),
                           current_setting('transaction_read_only')::boolean,
                           current_setting('cluster_name'),
                           current_setting('port')::integer,
                           pg_backend_pid(),
                           to_char(
                             pg_postmaster_start_time() AT TIME ZONE 'UTC',
                             'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                           )
                    """
                )
                row = cursor.fetchone()
        started_at = str(row[5])
        observations[name] = {
            "service_port": requirements["services"][name]["port"],
            "in_recovery": bool(row[0]),
            "transaction_read_only": bool(row[1]),
            "cluster_name": str(row[2]),
            "postgres_port": int(row[3]),
            "backend_pid": int(row[4]),
            "postmaster_started_at": started_at,
            "selected_member_address": member_by_start(
                before, started_at
            ),
            "path": (
                "haproxy-pgbouncer-postgresql"
                if name in {"primary", "replica"}
                else "haproxy-postgresql"
            ),
        }
    pool_locations: dict[str, Any] = {}
    for member, host in requirements["target"]["members"].items():
        rows = pgbouncer_pools(user, str(host))
        matches = [
            row
            for row in rows
            if row.get("database") == "test"
            and row.get("user") == "test"
        ]
        pool_locations[member] = {
            "present": bool(matches),
            "pool_mode": matches[0].get("pool_mode") if matches else None,
        }
    return {
        "schema": "pg36-ch22-endpoint-observations-v1",
        "captured_at": utc_now(milliseconds=True),
        "entry_address": requirements["target"]["entry_address"],
        "observations": observations,
        "dedicated_pool_locations": pool_locations,
    }


def pool_target_row(
    user: str,
    host: str,
) -> dict[str, Any] | None:
    matches = [
        row
        for row in pgbouncer_pools(user, host)
        if row.get("database") == "test"
        and row.get("user") == "test"
    ]
    if not matches:
        return None
    row = matches[0]
    numeric = (
        "cl_active",
        "cl_waiting",
        "sv_active",
        "sv_idle",
        "sv_used",
        "sv_login",
        "maxwait",
        "maxwait_us",
    )
    return {
        key: int(row[key])
        for key in numeric
    } | {"pool_mode": row.get("pool_mode")}


def saturation_probe(
    requirements: dict[str, Any],
    user: str,
    host: str,
) -> dict[str, Any]:
    contract = requirements["pool_experiment"]
    clients = int(contract["clients"])
    sleep_seconds = float(contract["query_sleep_seconds"])
    barrier = threading.Barrier(clients + 1)

    def worker(worker_no: int) -> dict[str, Any]:
        with connect("primary") as connection:
            barrier.wait(timeout=10)
            started_ns = time.monotonic_ns()
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_sleep(%s), pg_backend_pid(),
                           current_setting('transaction_read_only')::boolean
                    """,
                    (sleep_seconds,),
                )
                row = cursor.fetchone()
            connection.commit()
            finished_ns = time.monotonic_ns()
        return {
            "worker_no": worker_no,
            "backend_pid": int(row[1]),
            "transaction_read_only": bool(row[2]),
            "duration_ms": (finished_ns - started_ns) / 1_000_000,
        }

    samples: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=clients) as executor:
        futures = [executor.submit(worker, i + 1) for i in range(clients)]
        barrier.wait(timeout=10)
        while not all(future.done() for future in futures):
            row = pool_target_row(user, host)
            if row is not None:
                row["sampled_at"] = utc_now(milliseconds=True)
                samples.append(row)
            time.sleep(0.025)
        for future in as_completed(futures):
            results.append(future.result())
    final_row = pool_target_row(user, host)
    if final_row is not None:
        final_row["sampled_at"] = utc_now(milliseconds=True)
        samples.append(final_row)
    if not samples:
        raise LabError("dedicated PgBouncer pool was never observable")
    return {
        "schema": "pg36-ch22-saturation-v1",
        "clients": clients,
        "query_sleep_seconds": sleep_seconds,
        "completed_clients": len(results),
        "maximum_server_active": max(
            row["sv_active"] for row in samples
        ),
        "maximum_client_waiting": max(
            row["cl_waiting"] for row in samples
        ),
        "unique_backend_pids": sorted(
            {row["backend_pid"] for row in results}
        ),
        "minimum_duration_ms": min(
            row["duration_ms"] for row in results
        ),
        "maximum_duration_ms": max(
            row["duration_ms"] for row in results
        ),
        "samples": samples,
        "results": sorted(results, key=lambda row: row["worker_no"]),
    }


def session_state_probe(user: str, host: str) -> dict[str, Any]:
    reconnect_database(user, host, "test")
    time.sleep(0.25)
    connection_a = connect("primary")
    connection_b = connect("primary")
    try:
        with connection_a.cursor() as cursor:
            cursor.execute("SET search_path = pg_catalog")
            cursor.execute(
                "SELECT pg_backend_pid(), current_setting('search_path')"
            )
            first = cursor.fetchone()
        connection_a.commit()

        with connection_b.cursor() as cursor:
            cursor.execute(
                "SELECT pg_backend_pid(), current_setting('search_path')"
            )
            borrowed = cursor.fetchone()

        with connection_a.cursor() as cursor:
            cursor.execute(
                "SELECT pg_backend_pid(), current_setting('search_path')"
            )
            reassigned = cursor.fetchone()
        connection_a.rollback()
        connection_b.rollback()
    finally:
        connection_a.close()
        connection_b.close()
        reconnect_database(user, host, "test")
        time.sleep(0.25)
    return {
        "schema": "pg36-ch22-session-state-v1",
        "client_a_first": {
            "backend_pid": int(first[0]),
            "search_path": str(first[1]),
        },
        "client_b_borrowed": {
            "backend_pid": int(borrowed[0]),
            "search_path": str(borrowed[1]),
        },
        "client_a_reassigned": {
            "backend_pid": int(reassigned[0]),
            "search_path": str(reassigned[1]),
        },
        "state_visible_to_other_client": (
            int(borrowed[0]) == int(first[0])
            and str(borrowed[1]) == "pg_catalog"
        ),
        "state_not_sticky_for_original_client": (
            int(reassigned[0]) != int(first[0])
            and str(reassigned[1]) != "pg_catalog"
        ),
        "backend_cleanup": "RECONNECT test issued after clients closed",
    }


def protocol_prepared_probe(
    requirements: dict[str, Any],
    user: str,
    host: str,
) -> dict[str, Any]:
    reconnect_database(user, host, "test")
    time.sleep(0.25)
    iterations = int(
        requirements["pool_experiment"]["protocol_prepared_iterations"]
    )
    connection_a = connect("primary")
    connection_a.prepare_threshold = 1
    results: list[dict[str, Any]] = []
    connection_b: psycopg.Connection | None = None
    held_pid: int | None = None
    try:
        for value in range(3):
            with connection_a.cursor() as cursor:
                cursor.execute(
                    "SELECT %s::integer + 1, pg_backend_pid()",
                    (value,),
                )
                row = cursor.fetchone()
            connection_a.commit()
            results.append(
                {
                    "input": value,
                    "output": int(row[0]),
                    "backend_pid": int(row[1]),
                }
            )
        connection_b = connect("primary")
        with connection_b.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            held_pid = int(cursor.fetchone()[0])
        for value in range(3, iterations):
            with connection_a.cursor() as cursor:
                cursor.execute(
                    "SELECT %s::integer + 1, pg_backend_pid()",
                    (value,),
                )
                row = cursor.fetchone()
            connection_a.commit()
            results.append(
                {
                    "input": value,
                    "output": int(row[0]),
                    "backend_pid": int(row[1]),
                }
            )
    finally:
        connection_a.close()
        if connection_b is not None:
            connection_b.rollback()
            connection_b.close()
        reconnect_database(user, host, "test")
        time.sleep(0.25)
    unique_pids = sorted({row["backend_pid"] for row in results})
    return {
        "schema": "pg36-ch22-protocol-prepare-v1",
        "driver": "psycopg",
        "prepare_threshold": 1,
        "iterations": iterations,
        "correct_results": all(
            row["output"] == row["input"] + 1 for row in results
        ),
        "held_backend_pid": held_pid,
        "unique_backend_pids": unique_pids,
        "backend_reassignment_observed": (
            held_pid == results[0]["backend_pid"]
            and len(unique_pids) >= 2
        ),
        "results": results,
    }


def sql_prepared_probe(user: str, host: str) -> dict[str, Any]:
    reconnect_database(user, host, "test")
    time.sleep(0.25)
    connection_a = connect("primary")
    connection_b = connect("primary")
    prepared_pid: int | None = None
    held_pid: int | None = None
    execute_pid: int | None = None
    failure: dict[str, Any] | None = None
    unexpectedly_succeeded = False
    try:
        with connection_a.cursor() as cursor:
            cursor.execute(
                "PREPARE pg36_ch22_sql(integer) AS SELECT $1 + 1"
            )
            cursor.execute("SELECT pg_backend_pid()")
            prepared_pid = int(cursor.fetchone()[0])
        connection_a.commit()
        with connection_b.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            held_pid = int(cursor.fetchone()[0])
        try:
            with connection_a.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                execute_pid = int(cursor.fetchone()[0])
                cursor.execute("EXECUTE pg36_ch22_sql(41)")
                cursor.fetchone()
            unexpectedly_succeeded = True
        except psycopg.Error as exc:
            failure = {
                "class": type(exc).__name__,
                "sqlstate": exc.sqlstate,
            }
        connection_a.rollback()
        connection_b.rollback()
    finally:
        connection_a.close()
        connection_b.close()
        reconnect_database(user, host, "test")
        time.sleep(0.25)
    return {
        "schema": "pg36-ch22-sql-prepare-v1",
        "prepared_backend_pid": prepared_pid,
        "held_backend_pid": held_pid,
        "execute_backend_pid": execute_pid,
        "backend_reassignment_forced": (
            prepared_pid is not None and held_pid == prepared_pid
        ),
        "unexpectedly_succeeded": unexpectedly_succeeded,
        "expected_failure": failure,
    }


def replica_visibility_probe(
    requirements: dict[str, Any],
    before: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    token = f"visibility-{uuid.uuid4()}"
    sent_at = datetime.now(timezone.utc)
    with connect("primary") as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pg36_ch22.route_probe
                  (run_id, worker_no, attempt_no, token, client_sent_at)
                VALUES (%s, 0, 1, %s, %s)
                RETURNING committed_at,
                          to_char(
                            pg_postmaster_start_time() AT TIME ZONE 'UTC',
                            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                          )
                """,
                (run_id, token, sent_at),
            )
            committed_at, primary_started = cursor.fetchone()
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_current_wal_lsn()::text")
            commit_lsn = str(cursor.fetchone()[0])
        connection.commit()
    started_ns = time.monotonic_ns()
    deadline = time.monotonic() + float(
        requirements["replica_read"]["visibility_timeout_seconds"]
    )
    observation: dict[str, Any] | None = None
    polls = 0
    connection_rejections: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        polls += 1
        try:
            with connect("replica", autocommit=True) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT EXISTS(
                                 SELECT 1
                                   FROM pg36_ch22.route_probe
                                  WHERE token = %s
                               ),
                               pg_last_wal_replay_lsn()::text,
                               pg_is_in_recovery(),
                               current_setting(
                                 'transaction_read_only'
                               )::boolean,
                               to_char(
                                 pg_postmaster_start_time() AT TIME ZONE 'UTC',
                                 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                               )
                        """,
                        (token,),
                    )
                    row = cursor.fetchone()
        except psycopg.OperationalError as exc:
            connection_rejections.append(
                {
                    "class": type(exc).__name__,
                    "sqlstate": exc.sqlstate,
                }
            )
            time.sleep(0.025)
            continue
        if bool(row[0]):
            observed_ns = time.monotonic_ns()
            observation = {
                "visible": True,
                "replay_lsn": str(row[1]),
                "in_recovery": bool(row[2]),
                "transaction_read_only": bool(row[3]),
                "postmaster_started_at": str(row[4]),
                "selected_member_address": member_by_start(
                    before, str(row[4])
                ),
                "visibility_delay_ms": (
                    observed_ns - started_ns
                )
                / 1_000_000,
            }
            break
        time.sleep(0.025)
    if observation is None:
        observation = {
            "visible": False,
            "visibility_delay_ms": (
                time.monotonic_ns() - started_ns
            )
            / 1_000_000,
        }
    return {
        "schema": "pg36-ch22-replica-visibility-v1",
        "run_id": run_id,
        "token_recorded": True,
        "token_value_exported": False,
        "primary": {
            "commit_lsn": commit_lsn,
            "committed_at": committed_at.isoformat(),
            "postmaster_started_at": str(primary_started),
            "selected_member_address": member_by_start(
                before, str(primary_started)
            ),
        },
        "replica": observation,
        "polls": polls,
        "connection_rejections": connection_rejections,
        "claim": requirements["replica_read"]["claim"],
    }


def run_switch_probe(
    requirements: dict[str, Any],
    user: str,
    output: Path,
    run_id: str,
) -> dict[str, Any]:
    contract = requirements["switch_probe"]
    workers = int(contract["workers"])
    duration = float(contract["duration_seconds"])
    interval = float(contract["interval_seconds"])
    maximum_backoff = float(contract["maximum_backoff_seconds"])
    event_path = output / "client-events.jsonl"
    writer_lock = threading.Lock()
    events: list[dict[str, Any]] = []
    stop = threading.Event()
    probe_started_ns = time.monotonic_ns()
    probe_ends = time.monotonic() + duration

    def record(event: dict[str, Any]) -> None:
        with writer_lock:
            events.append(event)
            with event_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )

    def worker(worker_no: int) -> None:
        attempt_no = 0
        failure_streak = 0
        while not stop.is_set() and time.monotonic() < probe_ends:
            attempt_no += 1
            token = f"switch-{uuid.uuid4()}"
            started_ns = time.monotonic_ns()
            sent_at = datetime.now(timezone.utc)
            stage = "connect"
            try:
                with connect("primary") as connection:
                    stage = "execute"
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO pg36_ch22.route_probe
                              (
                                run_id, worker_no, attempt_no,
                                token, client_sent_at
                              )
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING committed_at,
                                      pg_backend_pid(),
                                      to_char(
                                        pg_postmaster_start_time()
                                          AT TIME ZONE 'UTC',
                                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                                      )
                            """,
                            (
                                run_id,
                                worker_no,
                                attempt_no,
                                token,
                                sent_at,
                            ),
                        )
                        committed_at, backend_pid, postmaster_at = (
                            cursor.fetchone()
                        )
                    stage = "commit"
                    connection.commit()
                finished_ns = time.monotonic_ns()
                record(
                    {
                        "schema": "pg36-ch22-client-event-v1",
                        "worker_no": worker_no,
                        "attempt_no": attempt_no,
                        "token": token,
                        "outcome": "acknowledged",
                        "attempt_started_monotonic_ns": started_ns,
                        "attempt_finished_monotonic_ns": finished_ns,
                        "duration_ms": (
                            finished_ns - started_ns
                        )
                        / 1_000_000,
                        "committed_at": committed_at.isoformat(),
                        "backend_pid": int(backend_pid),
                        "postmaster_started_at": str(postmaster_at),
                    }
                )
                failure_streak = 0
                delay = interval
            except psycopg.Error as exc:
                finished_ns = time.monotonic_ns()
                record(
                    {
                        "schema": "pg36-ch22-client-event-v1",
                        "worker_no": worker_no,
                        "attempt_no": attempt_no,
                        "token": token,
                        "outcome": "unknown",
                        "stage": stage,
                        "error_class": type(exc).__name__,
                        "sqlstate": exc.sqlstate,
                        "attempt_started_monotonic_ns": started_ns,
                        "attempt_finished_monotonic_ns": finished_ns,
                        "duration_ms": (
                            finished_ns - started_ns
                        )
                        / 1_000_000,
                    }
                )
                failure_streak += 1
                delay = min(
                    maximum_backoff,
                    interval * (2 ** min(failure_streak, 6)),
                )
                delay *= random.uniform(0.75, 1.25)
            stop.wait(delay)

    def refresh_all_pools(phase: str) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for member, host in sorted(
            requirements["target"]["members"].items()
        ):
            started_ns = time.monotonic_ns()
            reconnect_database(user, str(host), "test")
            finished_ns = time.monotonic_ns()
            actions.append(
                {
                    "member": member,
                    "database": "test",
                    "started_monotonic_ns": started_ns,
                    "finished_monotonic_ns": finished_ns,
                    "duration_ms": (
                        finished_ns - started_ns
                    )
                    / 1_000_000,
                    "status": "issued",
                }
            )
        return {
            "phase": phase,
            "actions": actions,
            "finished_monotonic_ns": max(
                row["finished_monotonic_ns"] for row in actions
            ),
        }

    def wait_for_acknowledgement_after(
        threshold_ns: int,
        *,
        timeout: float = 8,
    ) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with writer_lock:
                candidates = [
                    int(row["attempt_finished_monotonic_ns"])
                    for row in events
                    if row.get("outcome") == "acknowledged"
                    and int(row["attempt_finished_monotonic_ns"])
                    >= threshold_ns
                ]
            if candidates:
                return min(candidates)
            time.sleep(0.05)
        raise LabError(
            "no acknowledged write followed stable topology and pool refresh"
        )

    executor = ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(worker, i + 1) for i in range(workers)]
    forward_action: dict[str, Any] | None = None
    restore_action: dict[str, Any] | None = None
    forward_topology: dict[str, Any] | None = None
    restored_topology: dict[str, Any] | None = None
    forward_stable_ns: int | None = None
    restore_stable_ns: int | None = None
    pool_refreshes: list[dict[str, Any]] = []
    try:
        warmup_deadline = time.monotonic() + float(
            contract["warmup_seconds"]
        )
        while time.monotonic() < warmup_deadline:
            if sum(
                event["outcome"] == "acknowledged"
                for event in events
            ) >= workers * 2:
                break
            time.sleep(0.05)
        if sum(
            event["outcome"] == "acknowledged"
            for event in events
        ) < workers:
            raise LabError("switch probe did not establish a warmup baseline")

        forward_action = switchover(
            requirements,
            user,
            leader="pg-test-1",
            candidate="pg-test-2",
        )
        write_json(output / "switch-forward.json", forward_action)
        forward_topology, forward_stable_ns = wait_for_topology(
            requirements,
            user,
            "pg-test-2",
        )
        write_json(
            output / "phases" / "after-forward.json",
            forward_topology,
        )
        forward_refresh = refresh_all_pools("after-forward")
        pool_refreshes.append(forward_refresh)
        forward_ack_ns = wait_for_acknowledgement_after(
            max(
                forward_stable_ns,
                int(forward_refresh["finished_monotonic_ns"]),
            )
        )
        forward_refresh["first_acknowledgement_monotonic_ns"] = (
            forward_ack_ns
        )
        time.sleep(0.75)
        restore_action = switchover(
            requirements,
            user,
            leader="pg-test-2",
            candidate="pg-test-1",
        )
        write_json(output / "switch-restore.json", restore_action)
        restored_topology, restore_stable_ns = wait_for_topology(
            requirements,
            user,
            "pg-test-1",
        )
        write_json(
            output / "phases" / "restored.json",
            restored_topology,
        )
        restore_refresh = refresh_all_pools("after-restore")
        pool_refreshes.append(restore_refresh)
        restore_ack_ns = wait_for_acknowledgement_after(
            max(
                restore_stable_ns,
                int(restore_refresh["finished_monotonic_ns"]),
            )
        )
        restore_refresh["first_acknowledgement_monotonic_ns"] = (
            restore_ack_ns
        )
        write_json(
            output / "pool-refresh-actions.json",
            {
                "schema": "pg36-ch22-pool-refresh-actions-v1",
                "phases": pool_refreshes,
            },
        )
        for future in futures:
            future.result(timeout=max(1.0, duration + 10))
    except BaseException:
        stop.set()
        for future in futures:
            try:
                future.result(timeout=5)
            except BaseException:
                pass
        raise
    finally:
        stop.set()
        executor.shutdown(wait=True, cancel_futures=False)

    if (
        forward_action is None
        or restore_action is None
        or forward_topology is None
        or restored_topology is None
        or forward_stable_ns is None
        or restore_stable_ns is None
    ):
        raise LabError("switch probe did not produce complete action evidence")
    return {
        "schema": "pg36-ch22-switch-probe-v1",
        "probe_started_monotonic_ns": probe_started_ns,
        "probe_finished_monotonic_ns": time.monotonic_ns(),
        "configured_duration_seconds": duration,
        "workers": workers,
        "events": events,
        "forward_action": forward_action,
        "restore_action": restore_action,
        "forward_topology": forward_topology,
        "restored_topology": restored_topology,
        "forward_stable_monotonic_ns": forward_stable_ns,
        "restore_stable_monotonic_ns": restore_stable_ns,
    }


def reconcile_switch_probe(
    switch: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    with connect("primary", autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT worker_no, attempt_no, token, committed_at
                  FROM pg36_ch22.route_probe
                 WHERE run_id = %s
                   AND worker_no > 0
                 ORDER BY worker_no, attempt_no
                """,
                (run_id,),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT count(*)
                  FROM (
                    SELECT token
                      FROM pg36_ch22.route_probe
                     WHERE run_id = %s
                       AND worker_no > 0
                     GROUP BY token
                    HAVING count(*) > 1
                  ) AS duplicate
                """,
                (run_id,),
            )
            duplicate_tokens = int(cursor.fetchone()[0])
    persisted = {
        str(row[2]): {
            "worker_no": int(row[0]),
            "attempt_no": int(row[1]),
            "committed_at": row[3].isoformat(),
        }
        for row in rows
    }
    events = switch["events"]
    acknowledged = [
        event for event in events
        if event["outcome"] == "acknowledged"
    ]
    unknown = [
        event for event in events
        if event["outcome"] == "unknown"
    ]
    ack_missing = [
        event["token"]
        for event in acknowledged
        if event["token"] not in persisted
    ]
    unknown_committed = [
        event["token"]
        for event in unknown
        if event["token"] in persisted
    ]
    unknown_absent = [
        event["token"]
        for event in unknown
        if event["token"] not in persisted
    ]
    ack_times = sorted(
        int(event["attempt_finished_monotonic_ns"])
        for event in acknowledged
    )
    if len(ack_times) < 2:
        raise LabError("too few acknowledged events for gap analysis")

    def transition_gap(
        action: dict[str, Any],
        stable_ns: int,
    ) -> float:
        before = [
            value for value in ack_times
            if value <= int(action["started_monotonic_ns"])
        ]
        after = [value for value in ack_times if value >= stable_ns]
        if not before or not after:
            raise LabError("acknowledgements do not bracket a role transition")
        return (min(after) - max(before)) / 1_000_000

    adjacent = [
        (right - left) / 1_000_000
        for left, right in zip(ack_times, ack_times[1:])
    ]
    forward_gap = transition_gap(
        switch["forward_action"],
        int(switch["forward_stable_monotonic_ns"]),
    )
    restore_gap = transition_gap(
        switch["restore_action"],
        int(switch["restore_stable_monotonic_ns"]),
    )
    member_starts: dict[str, set[str]] = {}
    for event in acknowledged:
        started = str(event["postmaster_started_at"])
        member_starts.setdefault(started, set()).add(
            str(event["backend_pid"])
        )
    return {
        "schema": "pg36-ch22-reconciliation-v1",
        "run_id": run_id,
        "status": "reconciled",
        "counts": {
            "events": len(events),
            "acknowledged": len(acknowledged),
            "unknown": len(unknown),
            "persisted_rows": len(persisted),
            "acknowledged_rows_missing": len(ack_missing),
            "duplicate_tokens": duplicate_tokens,
            "unknown_committed": len(unknown_committed),
            "unknown_absent": len(unknown_absent),
            "unreconciled_unknown_outcomes": 0,
        },
        "metrics": {
            "forward_conservative_write_gap_ms": forward_gap,
            "restore_conservative_write_gap_ms": restore_gap,
            "maximum_conservative_write_gap_ms": max(
                forward_gap, restore_gap
            ),
            "maximum_adjacent_ack_gap_ms": max(adjacent),
        },
        "acknowledged_missing_tokens": ack_missing,
        "unknown_committed_tokens": unknown_committed,
        "unknown_absent_tokens": unknown_absent,
        "distinct_postmaster_generations_seen": len(member_starts),
        "interpretation": (
            "every failed attempt keeps one idempotency token; final lookup "
            "classifies it as committed or absent without blind replay"
        ),
    }


def source_hashes(source_dir: Path) -> dict[str, str]:
    return {
        path.name: sha256(path)
        for path in sorted(source_dir.iterdir())
        if path.is_file() and path.name not in OUTCOME_FILES
    }


def safe_baseline_restore(
    requirements: dict[str, Any],
    user: str,
) -> dict[str, Any]:
    observer = str(
        requirements["target"]["members"]["pg-test-3"]
    )
    try:
        topology = patroni_list(user, observer)
    except LabError as exc:
        return {
            "attempted": False,
            "restored": False,
            "reason": f"topology-unavailable:{type(exc).__name__}",
        }
    leader = current_leader(topology)
    if topology_stable(topology, "pg-test-1"):
        return {
            "attempted": False,
            "restored": True,
            "reason": "already-at-baseline",
        }
    if leader != "pg-test-2" or not topology_stable(
        topology, "pg-test-2"
    ):
        return {
            "attempted": False,
            "restored": False,
            "reason": "topology-ambiguous-or-degraded",
        }
    action = switchover(
        requirements,
        user,
        leader="pg-test-2",
        candidate="pg-test-1",
    )
    restored, _ = wait_for_topology(
        requirements,
        user,
        "pg-test-1",
    )
    return {
        "attempted": True,
        "restored": topology_stable(restored, "pg-test-1"),
        "reason": "safe-planned-baseline-restore",
        "action": action,
    }


def main() -> int:
    args = parse_args()
    run_id = str(uuid.uuid4())
    requirements: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    old_service_file = os.environ.get("PGSERVICEFILE")
    pool_override_started = False
    pool_restored = False
    switch_started = False
    try:
        requirements = read_json(args.requirements)
        require_authority(args, requirements)
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema": "pg36-ch22-drill-manifest-v1",
            "release": requirements["release"],
            "captured_at": utc_now(milliseconds=True),
            "target": requirements["target"]["id"],
            "run_id": run_id,
            "mode": "service-pooling-and-two-planned-switchovers",
            "status": "started",
            "production_approval": False,
            "production_data": False,
            "production_traffic": False,
            "unplanned_failure_injected": False,
            "destructive_cleanup": False,
            "secret_values_exported": 0,
            "source_sha256": source_hashes(args.source_dir),
        }
        write_json(args.output / "drill-manifest.json", manifest)
        before = capture_snapshot(
            requirements,
            args.ssh_user,
            "before",
        )
        require_initial_snapshot(before, requirements)
        write_json(args.output / "before.json", before)
        entry_host = str(requirements["target"]["entry_address"])
        password = load_declared_credential(
            args.credential_inventory,
            requirements,
        )
        fixture = setup_fixture(
            args.source_dir,
            requirements,
            args.ssh_user,
            entry_host,
        )
        write_json(args.output / "fixture.json", fixture)

        with tempfile.TemporaryDirectory(
            prefix="pg36-ch22-client."
        ) as temporary:
            temporary_path = Path(temporary)
            os.chmod(temporary_path, 0o700)
            service_file = write_service_file(
                temporary_path,
                requirements,
                password,
            )
            os.environ["PGSERVICEFILE"] = str(service_file)
            reconnected_members: list[str] = []
            for member, host in sorted(
                requirements["target"]["members"].items()
            ):
                reconnect_database(
                    args.ssh_user,
                    str(host),
                    "test",
                )
                reconnected_members.append(member)
            time.sleep(0.25)
            before_pool = selected_pool_settings(
                args.ssh_user, entry_host
            )
            expected_before = baseline_pool_settings(requirements)
            if before_pool != expected_before:
                raise LabError(
                    "entry PgBouncer settings drifted before override"
                )
            pool_evidence: dict[str, Any] = {
                "schema": "pg36-ch22-pool-settings-v1",
                "host": entry_host,
                "before": before_pool,
                "override_scope": "one runtime process, nonproduction",
                "baseline_database_reconnect_members":
                    reconnected_members,
            }
            try:
                override = override_pool_settings(requirements)
                set_pgbouncer_config(
                    args.ssh_user,
                    entry_host,
                    override,
                )
                pool_override_started = True
                during = selected_pool_settings(
                    args.ssh_user, entry_host
                )
                if during != override:
                    raise LabError(
                        "PgBouncer runtime override did not take effect"
                    )
                pool_evidence["during"] = during
                write_json(
                    args.output / "endpoint-observations.json",
                    endpoint_probe(
                        requirements,
                        before,
                        args.ssh_user,
                    ),
                )
                write_json(
                    args.output / "pool-saturation.json",
                    saturation_probe(
                        requirements,
                        args.ssh_user,
                        entry_host,
                    ),
                )
                write_json(
                    args.output / "session-semantics.json",
                    session_state_probe(
                        args.ssh_user,
                        entry_host,
                    ),
                )
                protocol = protocol_prepared_probe(
                    requirements,
                    args.ssh_user,
                    entry_host,
                )
                sql_prepare = sql_prepared_probe(
                    args.ssh_user,
                    entry_host,
                )
                write_json(
                    args.output / "prepared-statements.json",
                    {
                        "schema":
                            "pg36-ch22-prepared-statements-v1",
                        "pgbouncer_version": requirements[
                            "target"
                        ]["pgbouncer_observed"],
                        "max_prepared_statements": requirements[
                            "pgbouncer"
                        ]["max_prepared_statements"],
                        "protocol": protocol,
                        "sql": sql_prepare,
                    },
                )
                write_json(
                    args.output / "replica-visibility.json",
                    replica_visibility_probe(
                        requirements,
                        before,
                        run_id,
                    ),
                )
            finally:
                if pool_override_started:
                    set_pgbouncer_config(
                        args.ssh_user,
                        entry_host,
                        before_pool,
                    )
                    restored = selected_pool_settings(
                        args.ssh_user, entry_host
                    )
                    pool_evidence["restored"] = restored
                    pool_evidence["restored_before_switch"] = (
                        restored == before_pool
                    )
                    pool_evidence["restored_at"] = utc_now(
                        milliseconds=True
                    )
                    pool_restored = restored == before_pool
                    reconnect_database(
                        args.ssh_user,
                        entry_host,
                        "test",
                    )
                write_json(
                    args.output / "pool-settings.json",
                    pool_evidence,
                )
            if not pool_restored:
                raise LabError(
                    "PgBouncer settings were not restored before switch"
                )
            before_switch = patroni_list(
                args.ssh_user,
                str(
                    requirements["target"]["members"]["pg-test-3"]
                ),
            )
            if not topology_stable(before_switch, "pg-test-1"):
                raise LabError("topology drifted before switch probe")
            write_json(
                args.output / "phases" / "pre-switch.json",
                before_switch,
            )
            switch_started = True
            switch = run_switch_probe(
                requirements,
                args.ssh_user,
                args.output,
                run_id,
            )
            reconciliation = reconcile_switch_probe(switch, run_id)
            write_json(
                args.output / "reconciliation.json",
                reconciliation,
            )
            after = capture_snapshot(
                requirements,
                args.ssh_user,
                "after",
            )
            write_json(args.output / "after.json", after)

        manifest.update(
            {
                "status": "completed",
                "completed_at": utc_now(milliseconds=True),
                "pool_settings_restored_before_switch": pool_restored,
                "final_leader": current_leader(after["topology"]),
                "secret_values_exported": 0,
                "private_service_file_removed": True,
                "declared_login_role_mutated": False,
            }
        )
        write_json(args.output / "drill-manifest.json", manifest)
    except (
        LabError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        psycopg.Error,
        threading.BrokenBarrierError,
    ) as exc:
        cleanup: dict[str, Any] = {
            "pool_restore_attempted": False,
            "pool_restored": pool_restored,
            "topology_restore": {
                "attempted": False,
                "restored": not switch_started,
                "reason": "switch-not-started",
            },
        }
        if requirements is not None:
            entry_host = str(requirements["target"]["entry_address"])
            if pool_override_started and not pool_restored:
                cleanup["pool_restore_attempted"] = True
                try:
                    baseline = baseline_pool_settings(requirements)
                    set_pgbouncer_config(
                        args.ssh_user, entry_host, baseline
                    )
                    pool_restored = (
                        selected_pool_settings(
                            args.ssh_user, entry_host
                        )
                        == baseline
                    )
                except LabError:
                    pool_restored = False
                cleanup["pool_restored"] = pool_restored
            if switch_started:
                try:
                    cleanup["topology_restore"] = (
                        safe_baseline_restore(
                            requirements,
                            args.ssh_user,
                        )
                    )
                except LabError as restore_exc:
                    cleanup["topology_restore"] = {
                        "attempted": True,
                        "restored": False,
                        "reason": type(restore_exc).__name__,
                    }
        if manifest is not None:
            manifest.update(
                {
                    "status": "failed",
                    "failed_at": utc_now(milliseconds=True),
                    "failure_class": type(exc).__name__,
                    "cleanup": cleanup,
                    "secret_values_exported": 0,
                }
            )
            write_json(args.output / "drill-manifest.json", manifest)
        sys.stderr.write(
            f"service drill failed: {type(exc).__name__}: {exc}\n"
        )
        return 1
    finally:
        if old_service_file is None:
            os.environ.pop("PGSERVICEFILE", None)
        else:
            os.environ["PGSERVICEFILE"] = old_service_file
    print(f"status=service-drill-ok run_id={run_id}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
