#!/usr/bin/env python3
"""Run the bounded two-cluster chapter 29 migration experiment."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


SOURCE_SERVICE = "pg-test-1"
TARGET_SERVICE = "pg-meta-1"
SOURCE_ADDRESS = "10.10.10.11"
TARGET_ADDRESS = "10.10.10.10"
SOURCE_DATABASE = "pg36_shop_src"
TARGET_DATABASE = "pg36_shop_dst"
SOURCE_OWNER = "pg36_ch29_source_owner"
TARGET_OWNER = "pg36_ch29_target_owner"
SOURCE_RUNTIME = "dbuser_pg36source"
TARGET_RUNTIME = "dbuser_pg36target"
REPLICATION_ROLE = "dbuser_pg36repl"
PUBLICATION = "pg36_shop_pub"
SUBSCRIPTION = "pg36_shop_sub"
SLOT = "pg36_shop_slot"
MARKER_PREFIX = "pg36-ch29-disposable-migration-fixture-v1"
CONFLICT_ID = 900000
DRIFT_ID = 1


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
            f"command failed ({completed.returncode}): "
            f"{' '.join(command[:2])}: {completed.stderr.strip()[-2400:]}"
        )
    return completed


def admin_connection(service: str, database: str, application: str) -> str:
    return f"service={service} dbname={database} application_name={application}"


def source_admin(database: str = SOURCE_DATABASE, application: str = "admin") -> str:
    return admin_connection(SOURCE_SERVICE, database, f"pg36-ch29-{application}")


def target_admin(database: str = TARGET_DATABASE, application: str = "admin") -> str:
    return admin_connection(TARGET_SERVICE, database, f"pg36-ch29-{application}")


def runtime_connection(
    *,
    address: str,
    database: str,
    user: str,
    application: str,
) -> str:
    return (
        f"host={address} port=5432 dbname={database} user={user} "
        f"sslmode=disable application_name={application}"
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
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    for row in reversed(rows):
        try:
            return json.loads(row, parse_float=Decimal)
        except json.JSONDecodeError:
            continue
    raise ExperimentError(f"{label} did not return a JSON value")


def json_psql(
    connection: str,
    sql: str,
    label: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> Any:
    completed = psql(
        connection,
        sql="\\pset format unaligned\n\\pset tuples_only on\n" + sql,
        env=env,
        timeout=timeout,
    )
    return parse_single_json(completed.stdout, label)


def decimal_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
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


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, Decimal)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def create_fixture(
    run_id: str,
    source_password: str,
    target_password: str,
    replication_password: str,
    source_env: dict[str, str],
    target_env: dict[str, str],
) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    psql(
        source_admin("postgres", "create-source"),
        sql=f"""
CREATE ROLE {SOURCE_OWNER} NOLOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
COMMENT ON ROLE {SOURCE_OWNER} IS '{marker}';
CREATE ROLE {SOURCE_RUNTIME} LOGIN PASSWORD '{source_password}'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT dbrole_readwrite TO {SOURCE_RUNTIME}
  WITH INHERIT FALSE, SET FALSE;
COMMENT ON ROLE {SOURCE_RUNTIME} IS '{marker}';
CREATE ROLE {REPLICATION_ROLE} LOGIN REPLICATION PASSWORD '{replication_password}'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT dbrole_readonly TO {REPLICATION_ROLE}
  WITH INHERIT FALSE, SET FALSE;
COMMENT ON ROLE {REPLICATION_ROLE} IS '{marker}';
CREATE DATABASE {SOURCE_DATABASE} ALLOW_CONNECTIONS false;
COMMENT ON DATABASE {SOURCE_DATABASE} IS '{marker}';
REVOKE CONNECT ON DATABASE {SOURCE_DATABASE} FROM PUBLIC;
GRANT CONNECT ON DATABASE {SOURCE_DATABASE}
  TO {SOURCE_RUNTIME}, {REPLICATION_ROLE};
ALTER DATABASE {SOURCE_DATABASE} ALLOW_CONNECTIONS true;
""",
        timeout=60,
    )
    psql(
        target_admin("postgres", "create-target"),
        sql=f"""
CREATE ROLE {TARGET_OWNER} NOLOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
COMMENT ON ROLE {TARGET_OWNER} IS '{marker}';
CREATE ROLE {TARGET_RUNTIME} LOGIN PASSWORD '{target_password}'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT dbrole_readwrite TO {TARGET_RUNTIME}
  WITH INHERIT FALSE, SET FALSE;
COMMENT ON ROLE {TARGET_RUNTIME} IS '{marker}';
CREATE DATABASE {TARGET_DATABASE} ALLOW_CONNECTIONS false;
COMMENT ON DATABASE {TARGET_DATABASE} IS '{marker}';
REVOKE CONNECT ON DATABASE {TARGET_DATABASE} FROM PUBLIC;
GRANT CONNECT ON DATABASE {TARGET_DATABASE} TO {TARGET_RUNTIME};
ALTER DATABASE {TARGET_DATABASE} ALLOW_CONNECTIONS true;
""",
        timeout=60,
    )

    source_schema = f"""
CREATE SCHEMA shop AUTHORIZATION {SOURCE_OWNER};
SET ROLE {SOURCE_OWNER};
CREATE TABLE shop.customers (
  customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  email text NOT NULL UNIQUE,
  tier text NOT NULL CHECK (tier IN ('standard', 'plus', 'vip')),
  created_at timestamptz NOT NULL
);
CREATE TABLE shop.orders (
  order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  customer_id bigint NOT NULL REFERENCES shop.customers(customer_id),
  status text NOT NULL CHECK (
    status IN ('new', 'paid', 'shipped', 'cancelled')
  ),
  amount numeric(12,2) NOT NULL CHECK (amount >= 0),
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  note text NOT NULL DEFAULT ''
);
RESET ROLE;
GRANT USAGE ON SCHEMA shop TO {SOURCE_RUNTIME}, {REPLICATION_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE
  ON shop.customers, shop.orders TO {SOURCE_RUNTIME};
GRANT USAGE, SELECT, UPDATE
  ON ALL SEQUENCES IN SCHEMA shop TO {SOURCE_RUNTIME};
GRANT SELECT ON shop.customers, shop.orders TO {REPLICATION_ROLE};
CREATE PUBLICATION {PUBLICATION}
  FOR TABLE shop.customers, shop.orders;
COMMENT ON PUBLICATION {PUBLICATION} IS '{marker}';
"""
    target_schema = f"""
CREATE SCHEMA shop AUTHORIZATION {TARGET_OWNER};
SET ROLE {TARGET_OWNER};
CREATE TABLE shop.customers (
  customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  email text NOT NULL UNIQUE,
  tier text NOT NULL CHECK (tier IN ('standard', 'plus', 'vip')),
  created_at timestamptz NOT NULL
);
CREATE TABLE shop.orders (
  order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  customer_id bigint NOT NULL REFERENCES shop.customers(customer_id),
  status text NOT NULL CHECK (
    status IN ('new', 'paid', 'shipped', 'cancelled')
  ),
  amount numeric(12,2) NOT NULL CHECK (amount >= 0),
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  note text NOT NULL DEFAULT ''
);
RESET ROLE;
GRANT USAGE ON SCHEMA shop TO {TARGET_RUNTIME};
GRANT SELECT, INSERT, UPDATE, DELETE
  ON shop.customers, shop.orders TO {TARGET_RUNTIME};
GRANT USAGE, SELECT, UPDATE
  ON ALL SEQUENCES IN SCHEMA shop TO {TARGET_RUNTIME};
"""
    psql(source_admin(application="source-schema"), sql=source_schema, timeout=60)
    psql(target_admin(application="target-schema"), sql=target_schema, timeout=60)

    initial = json_psql(
        runtime_connection(
            address=SOURCE_ADDRESS,
            database=SOURCE_DATABASE,
            user=SOURCE_RUNTIME,
            application="pg36-ch29-source-initial",
        ),
        r"""
INSERT INTO shop.customers (email, tier, created_at)
SELECT
  format('customer-%s@example.test', to_char(i, 'FM00000')),
  (ARRAY['standard', 'plus', 'vip'])[(i % 3) + 1],
  timestamptz '2025-01-01 00:00:00+00'
    + (i * interval '1 second')
FROM generate_series(1, 5000) AS g(i);

INSERT INTO shop.orders (
  customer_id, status, amount, created_at, updated_at, note
)
SELECT
  ((i - 1) % 5000) + 1,
  (ARRAY['new', 'paid', 'shipped'])[(i % 3) + 1],
  ((i % 100000) + 1)::numeric / 100,
  timestamptz '2025-02-01 00:00:00+00'
    + (i * interval '1 second'),
  timestamptz '2025-02-01 00:00:00+00'
    + (i * interval '1 second'),
  repeat(md5(i::text), 4)
FROM generate_series(1, 20000) AS g(i);

SELECT jsonb_build_object(
  'customers', (SELECT count(*) FROM shop.customers),
  'orders', (SELECT count(*) FROM shop.orders)
);
""",
        "initial fixture",
        env=source_env,
        timeout=180,
    )
    psql(source_admin(application="source-analyze"), sql="ANALYZE;\n", timeout=60)

    conninfo = (
        f"host={SOURCE_ADDRESS} port=5432 dbname={SOURCE_DATABASE} "
        f"user={REPLICATION_ROLE} password={replication_password} "
        "sslmode=disable application_name=pg36_shop_sub "
        "options=-crow_security=off"
    )
    psql(
        target_admin(application="create-subscription"),
        sql=f"""
CREATE SUBSCRIPTION {SUBSCRIPTION}
CONNECTION '{conninfo}'
PUBLICATION {PUBLICATION}
WITH (
  copy_data = true,
  create_slot = true,
  enabled = true,
  slot_name = '{SLOT}',
  streaming = on,
  binary = false
);
COMMENT ON SUBSCRIPTION {SUBSCRIPTION} IS '{marker}';
""",
        timeout=60,
    )
    return {
        "marker": marker,
        "initial": initial,
        "source_runtime_connection_proved": True,
        "target_runtime_connection_deferred_to_cutover": True,
        "replication_secret_published": False,
        "source_credentials_equal_target_credentials":
            source_password == target_password,
        "source_system_identifier": json_psql(
            source_admin("postgres", "source-system-id"),
            "SELECT to_jsonb(system_identifier) FROM pg_control_system();\n",
            "source system identifier",
        ),
        "target_system_identifier": json_psql(
            target_admin("postgres", "target-system-id"),
            "SELECT to_jsonb(system_identifier) FROM pg_control_system();\n",
            "target system identifier",
        ),
    }


def manifest(connection: str, label: str) -> dict[str, Any]:
    sql = r"""
WITH customer_summary AS (
  SELECT
    count(*)::bigint AS rows,
    min(customer_id) AS min_id,
    max(customer_id) AS max_id,
    md5(coalesce(string_agg(
      md5(concat_ws(
        '|',
        customer_id::text,
        email,
        tier,
        to_char(
          created_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US'
        )
      )),
      '' ORDER BY customer_id
    ), '')) AS digest
  FROM shop.customers
), order_summary AS (
  SELECT
    count(*)::bigint AS rows,
    min(order_id) AS min_id,
    max(order_id) AS max_id,
    coalesce(sum(amount), 0)::text AS amount_sum,
    md5(coalesce(string_agg(
      md5(concat_ws(
        '|',
        order_id::text,
        customer_id::text,
        status,
        amount::text,
        to_char(
          created_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US'
        ),
        to_char(
          updated_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US'
        ),
        note
      )),
      '' ORDER BY order_id
    ), '')) AS digest
  FROM shop.orders
), status_summary AS (
  SELECT coalesce(
    jsonb_object_agg(status, rows ORDER BY status),
    '{}'::jsonb
  ) AS value
  FROM (
    SELECT status, count(*) AS rows
    FROM shop.orders
    GROUP BY status
  ) AS s
), sequence_summary AS (
  SELECT jsonb_build_object(
    'last_value', last_value,
    'is_called', is_called
  ) AS value
  FROM shop.orders_order_id_seq
)
SELECT jsonb_build_object(
  'customers', (SELECT to_jsonb(customer_summary) FROM customer_summary),
  'orders', (SELECT to_jsonb(order_summary) FROM order_summary),
  'status_counts', (SELECT value FROM status_summary),
  'business_invariants', jsonb_build_object(
    'orphan_orders', (
      SELECT count(*)
      FROM shop.orders AS o
      LEFT JOIN shop.customers AS c USING (customer_id)
      WHERE c.customer_id IS NULL
    ),
    'negative_amounts', (
      SELECT count(*) FROM shop.orders WHERE amount < 0
    ),
    'invalid_statuses', (
      SELECT count(*)
      FROM shop.orders
      WHERE status NOT IN ('new', 'paid', 'shipped', 'cancelled')
    )
  ),
  'order_sequence', (SELECT value FROM sequence_summary)
);
"""
    result = json_psql(connection, sql, f"{label} manifest", timeout=120)
    if not isinstance(result, dict):
        raise ExperimentError(f"{label} manifest is not an object")
    return result


def logical_manifest(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "customers",
            "orders",
            "status_counts",
            "business_invariants",
        )
    }


def bucket_manifest(connection: str, label: str) -> list[dict[str, Any]]:
    sql = r"""
SELECT coalesce(
  jsonb_agg(
    jsonb_build_object(
      'bucket', bucket,
      'rows', rows,
      'amount_sum', amount_sum,
      'digest', digest
    )
    ORDER BY bucket
  ),
  '[]'::jsonb
)
FROM (
  SELECT
    mod(order_id, 16) AS bucket,
    count(*)::bigint AS rows,
    sum(amount)::text AS amount_sum,
    md5(string_agg(
      md5(concat_ws(
        '|',
        order_id::text,
        customer_id::text,
        status,
        amount::text,
        to_char(
          updated_at AT TIME ZONE 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US'
        ),
        note
      )),
      '' ORDER BY order_id
    )) AS digest
  FROM shop.orders
  GROUP BY mod(order_id, 16)
) AS b;
"""
    value = json_psql(connection, sql, f"{label} buckets", timeout=120)
    if not isinstance(value, list):
        raise ExperimentError(f"{label} bucket manifest is not an array")
    return value


def differing_buckets(
    source_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
) -> list[int]:
    source = {int(row["bucket"]): row for row in source_rows}
    target = {int(row["bucket"]): row for row in target_rows}
    return sorted(
        bucket
        for bucket in source.keys() | target.keys()
        if source.get(bucket) != target.get(bucket)
    )


def slot_state() -> dict[str, Any]:
    sql = f"""
SELECT coalesce(
  (
    SELECT jsonb_build_object(
      'slot_name', slot_name,
      'plugin', plugin,
      'slot_type', slot_type,
      'database', database,
      'active', active,
      'active_pid', active_pid,
      'restart_lsn', restart_lsn::text,
      'confirmed_flush_lsn', confirmed_flush_lsn::text,
      'wal_status', wal_status,
      'safe_wal_size', safe_wal_size,
      'two_phase', two_phase,
      'failover', failover,
      'invalidation_reason', invalidation_reason,
      'retained_bytes',
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    )
    FROM pg_replication_slots
    WHERE slot_name = '{SLOT}'
  ),
  '{{}}'::jsonb
);
"""
    value = json_psql(
        source_admin("postgres", "slot-state"),
        sql,
        "slot state",
        timeout=20,
    )
    if not isinstance(value, dict):
        raise ExperimentError("slot state is not an object")
    return value


def source_lsn() -> str:
    value = json_psql(
        source_admin("postgres", "source-lsn"),
        "SELECT to_jsonb(pg_current_wal_flush_lsn()::text);\n",
        "source LSN",
        timeout=20,
    )
    if not isinstance(value, str):
        raise ExperimentError("source LSN is not text")
    return value


def subscription_state() -> dict[str, Any]:
    sql = f"""
WITH rels AS (
  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'relation', srrelid::regclass::text,
        'state', srsubstate,
        'lsn', srsublsn::text
      )
      ORDER BY srrelid::regclass::text
    ),
    '[]'::jsonb
  ) AS value
  FROM pg_subscription_rel
  WHERE srsubid = (
    SELECT oid FROM pg_subscription WHERE subname = '{SUBSCRIPTION}'
  )
), workers AS (
  SELECT jsonb_build_object(
    'count', count(*),
    'active_count', count(*) FILTER (WHERE pid IS NOT NULL),
      'latest_end_lsn', max(latest_end_lsn::text),
    'last_msg_receipt_time', max(last_msg_receipt_time)
  ) AS value
  FROM pg_stat_subscription
  WHERE subname = '{SUBSCRIPTION}'
), conflicts AS (
  SELECT coalesce(
    (
      SELECT to_jsonb(s)
      FROM pg_stat_subscription_stats AS s
      WHERE subname = '{SUBSCRIPTION}'
    ),
    '{{}}'::jsonb
  ) AS value
)
SELECT coalesce(
  (
    SELECT jsonb_build_object(
      'name', subname,
      'enabled', subenabled,
      'slot_name', subslotname,
      'publications', subpublications,
      'streaming', substream,
      'binary', subbinary,
      'relations', (SELECT value FROM rels),
      'workers', (SELECT value FROM workers),
      'conflicts', (SELECT value FROM conflicts)
    )
    FROM pg_subscription
    WHERE subname = '{SUBSCRIPTION}'
  ),
  '{{}}'::jsonb
);
"""
    value = json_psql(
        target_admin(application="subscription-state"),
        sql,
        "subscription state",
        timeout=20,
    )
    if not isinstance(value, dict):
        raise ExperimentError("subscription state is not an object")
    return value


def lsn_acknowledged(marker: str) -> bool:
    sql = f"""
SELECT to_jsonb(coalesce(
  (
    SELECT pg_wal_lsn_diff(confirmed_flush_lsn, '{marker}'::pg_lsn) >= 0
    FROM pg_replication_slots
    WHERE slot_name = '{SLOT}'
  ),
  false
));
"""
    return bool(
        json_psql(
            source_admin("postgres", "lsn-ack"),
            sql,
            "LSN acknowledgement",
            timeout=20,
        )
    )


def wait_ready(
    label: str,
    *,
    marker: str | None = None,
    require_manifest: bool = True,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    last_source: dict[str, Any] | None = None
    last_target: dict[str, Any] | None = None
    while time.monotonic() - started < timeout_seconds:
        state = subscription_state()
        relation_states = [
            row.get("state") for row in state.get("relations", [])
        ]
        ready = (
            state.get("enabled") is True
            and len(relation_states) == 2
            and set(relation_states) == {"r"}
            and state.get("workers", {}).get("active_count", 0) >= 1
        )
        ack = marker is None or lsn_acknowledged(marker)
        equal = False
        if ready and ack and require_manifest:
            last_source = manifest(source_admin(application=f"{label}-source"), label)
            last_target = manifest(target_admin(application=f"{label}-target"), label)
            equal = logical_manifest(last_source) == logical_manifest(last_target)
        elif ready and ack:
            equal = True
        samples.append(
            {
                "captured_at": utc_now(),
                "enabled": state.get("enabled"),
                "relation_states": relation_states,
                "active_workers": state.get("workers", {}).get("active_count", 0),
                "marker_acknowledged": ack,
                "logical_manifest_equal": equal,
            }
        )
        if ready and ack and equal:
            return {
                "label": label,
                "elapsed_seconds": time.monotonic() - started,
                "sample_count": len(samples),
                "samples": samples,
                "subscription": state,
                "source_manifest": last_source,
                "target_manifest": last_target,
                "marker_lsn": marker,
                "marker_acknowledged": ack,
                "logical_manifest_equal": equal,
            }
        time.sleep(0.25)
    raise ExperimentError(f"{label} did not converge: {samples[-3:]}")


def set_subscription_enabled(enabled: bool) -> dict[str, Any]:
    verb = "ENABLE" if enabled else "DISABLE"
    psql(
        target_admin(application=f"subscription-{verb.lower()}"),
        sql=f"ALTER SUBSCRIPTION {SUBSCRIPTION} {verb};\n",
        timeout=30,
    )
    for _ in range(120):
        state = subscription_state()
        workers = state.get("workers", {}).get("active_count", 0)
        slot = slot_state()
        if enabled:
            if state.get("enabled") is True:
                return {"subscription": state, "slot": slot}
        else:
            if (
                state.get("enabled") is False
                and workers == 0
                and slot.get("active") is False
            ):
                return {"subscription": state, "slot": slot}
        time.sleep(0.25)
    raise ExperimentError(f"subscription did not become {verb.lower()}")


def runtime_json(
    *,
    side: str,
    password_env: dict[str, str],
    sql: str,
    label: str,
    timeout: int = 120,
) -> Any:
    if side == "source":
        connection = runtime_connection(
            address=SOURCE_ADDRESS,
            database=SOURCE_DATABASE,
            user=SOURCE_RUNTIME,
            application=f"pg36-ch29-{label}",
        )
    else:
        connection = runtime_connection(
            address=TARGET_ADDRESS,
            database=TARGET_DATABASE,
            user=TARGET_RUNTIME,
            application=f"pg36-ch29-{label}",
        )
    return json_psql(
        connection,
        sql,
        label,
        env=password_env,
        timeout=timeout,
    )


def cleanup_fixture(run_id: str) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    target_observed = json_psql(
        target_admin("postgres", "cleanup-target-observe"),
        f"""
SELECT jsonb_build_object(
  'database_exists', EXISTS (
    SELECT FROM pg_database WHERE datname = '{TARGET_DATABASE}'
  ),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database WHERE datname = '{TARGET_DATABASE}'
  ),
  'owner_exists', EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{TARGET_OWNER}'
  ),
  'owner_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{TARGET_OWNER}'
  ),
  'runtime_exists', EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{TARGET_RUNTIME}'
  ),
  'runtime_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{TARGET_RUNTIME}'
  ),
  'subscription_exists', EXISTS (
    SELECT FROM pg_subscription WHERE subname = '{SUBSCRIPTION}'
  )
);
""",
        "target cleanup observation",
    )
    source_observed = json_psql(
        source_admin("postgres", "cleanup-source-observe"),
        f"""
SELECT jsonb_build_object(
  'database_exists', EXISTS (
    SELECT FROM pg_database WHERE datname = '{SOURCE_DATABASE}'
  ),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database WHERE datname = '{SOURCE_DATABASE}'
  ),
  'owner_exists', EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{SOURCE_OWNER}'
  ),
  'owner_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{SOURCE_OWNER}'
  ),
  'runtime_exists', EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{SOURCE_RUNTIME}'
  ),
  'runtime_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{SOURCE_RUNTIME}'
  ),
  'replication_exists', EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{REPLICATION_ROLE}'
  ),
  'replication_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{REPLICATION_ROLE}'
  ),
  'slot_exists', EXISTS (
    SELECT FROM pg_replication_slots WHERE slot_name = '{SLOT}'
  ),
  'slot_matches', coalesce((
    SELECT database = '{SOURCE_DATABASE}'
       AND plugin = 'pgoutput'
       AND slot_type = 'logical'
    FROM pg_replication_slots WHERE slot_name = '{SLOT}'
  ), true)
);
""",
        "source cleanup observation",
    )
    for observed, fields in (
        (target_observed, ("database", "owner", "runtime")),
        (source_observed, ("database", "owner", "runtime", "replication")),
    ):
        for field in fields:
            if observed.get(f"{field}_exists") and observed.get(f"{field}_marker") != marker:
                raise ExperimentError(f"refusing cleanup: {field} marker mismatch")
    if source_observed.get("slot_exists") and not source_observed.get("slot_matches"):
        raise ExperimentError("refusing cleanup: slot identity mismatch")

    subscription_drop_mode = "absent"
    if target_observed.get("subscription_exists"):
        sub_marker = json_psql(
            target_admin(application="cleanup-sub-marker"),
            f"""
SELECT to_jsonb(obj_description(oid, 'pg_subscription'))
FROM pg_subscription WHERE subname = '{SUBSCRIPTION}';
""",
            "subscription marker",
        )
        if sub_marker != marker:
            raise ExperimentError("refusing cleanup: subscription marker mismatch")
        psql(
            target_admin(application="cleanup-disable-sub"),
            sql=f"ALTER SUBSCRIPTION {SUBSCRIPTION} DISABLE;\n",
            timeout=30,
        )
        dropped = psql(
            target_admin(application="cleanup-drop-sub"),
            sql=f"DROP SUBSCRIPTION {SUBSCRIPTION};\n",
            timeout=60,
            check=False,
        )
        if dropped.returncode == 0:
            subscription_drop_mode = "normal-remote-slot-drop"
        else:
            psql(
                target_admin(application="cleanup-disassociate-sub"),
                sql=(
                    f"ALTER SUBSCRIPTION {SUBSCRIPTION} "
                    "SET (slot_name = NONE);\n"
                    f"DROP SUBSCRIPTION {SUBSCRIPTION};\n"
                ),
                timeout=60,
            )
            subscription_drop_mode = "disassociate-then-exact-source-drop"

    slot = slot_state()
    if slot:
        if (
            slot.get("database") != SOURCE_DATABASE
            or slot.get("plugin") != "pgoutput"
            or slot.get("slot_type") != "logical"
        ):
            raise ExperimentError("refusing cleanup: live slot identity mismatch")
        for _ in range(60):
            slot = slot_state()
            if not slot or slot.get("active") is False:
                break
            time.sleep(0.25)
        else:
            raise ExperimentError("exact chapter slot remained active")
        if slot:
            json_psql(
                source_admin("postgres", "cleanup-drop-slot"),
                f"""
SELECT to_jsonb(pg_drop_replication_slot('{SLOT}') IS NULL)
FROM pg_replication_slots
WHERE slot_name = '{SLOT}'
  AND database = '{SOURCE_DATABASE}'
  AND plugin = 'pgoutput'
  AND NOT active;
""",
                "slot drop",
            )

    terminated = {"source": 0, "target": 0}
    for side, connection, database, roles in (
        (
            "target",
            target_admin("postgres", "cleanup-target-sessions"),
            TARGET_DATABASE,
            [TARGET_RUNTIME],
        ),
        (
            "source",
            source_admin("postgres", "cleanup-source-sessions"),
            SOURCE_DATABASE,
            [SOURCE_RUNTIME, REPLICATION_ROLE],
        ),
    ):
        role_list = ", ".join(sql_literal(role) for role in roles)
        result = json_psql(
            connection,
            f"""
WITH victims AS (
  SELECT pid
  FROM pg_stat_activity
  WHERE datname = '{database}'
    AND usename IN ({role_list})
    AND application_name LIKE 'pg36-ch29-%'
), killed AS (
  SELECT pg_terminate_backend(pid) AS ok FROM victims
)
SELECT jsonb_build_object(
  'matched', (SELECT count(*) FROM victims),
  'terminated', (SELECT count(*) FROM killed WHERE ok)
);
""",
            f"{side} session cleanup",
        )
        terminated[side] = int(result["terminated"])

    if target_observed.get("database_exists"):
        psql(
            target_admin("postgres", "cleanup-drop-target-db"),
            sql=f"""
ALTER DATABASE {TARGET_DATABASE} ALLOW_CONNECTIONS false;
DROP DATABASE {TARGET_DATABASE};
""",
            timeout=60,
        )
    target_roles = [
        role
        for role, key in (
            (TARGET_RUNTIME, "runtime_exists"),
            (TARGET_OWNER, "owner_exists"),
        )
        if target_observed.get(key)
    ]
    if target_roles:
        psql(
            target_admin("postgres", "cleanup-drop-target-roles"),
            sql="DROP ROLE " + ", ".join(target_roles) + ";\n",
            timeout=30,
        )

    if source_observed.get("database_exists"):
        psql(
            source_admin("postgres", "cleanup-drop-source-db"),
            sql=f"""
ALTER DATABASE {SOURCE_DATABASE} ALLOW_CONNECTIONS false;
DROP DATABASE {SOURCE_DATABASE};
""",
            timeout=60,
        )
    source_roles = [
        role
        for role, key in (
            (REPLICATION_ROLE, "replication_exists"),
            (SOURCE_RUNTIME, "runtime_exists"),
            (SOURCE_OWNER, "owner_exists"),
        )
        if source_observed.get(key)
    ]
    if source_roles:
        psql(
            source_admin("postgres", "cleanup-drop-source-roles"),
            sql="DROP ROLE " + ", ".join(source_roles) + ";\n",
            timeout=30,
        )

    target_final = json_psql(
        target_admin("postgres", "cleanup-target-verify"),
        f"""
SELECT jsonb_build_object(
  'database_absent', NOT EXISTS (
    SELECT FROM pg_database WHERE datname = '{TARGET_DATABASE}'
  ),
  'owner_role_absent', NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{TARGET_OWNER}'
  ),
  'runtime_role_absent', NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{TARGET_RUNTIME}'
  ),
  'subscription_absent', NOT EXISTS (
    SELECT FROM pg_subscription WHERE subname = '{SUBSCRIPTION}'
  ),
  'sessions_remaining', (
    SELECT count(*) FROM pg_stat_activity WHERE datname = '{TARGET_DATABASE}'
  )
);
""",
        "target cleanup verification",
    )
    source_final = json_psql(
        source_admin("postgres", "cleanup-source-verify"),
        f"""
SELECT jsonb_build_object(
  'database_absent', NOT EXISTS (
    SELECT FROM pg_database WHERE datname = '{SOURCE_DATABASE}'
  ),
  'owner_role_absent', NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{SOURCE_OWNER}'
  ),
  'runtime_role_absent', NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{SOURCE_RUNTIME}'
  ),
  'replication_role_absent', NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = '{REPLICATION_ROLE}'
  ),
  'slot_absent', NOT EXISTS (
    SELECT FROM pg_replication_slots WHERE slot_name = '{SLOT}'
  ),
  'sessions_remaining', (
    SELECT count(*) FROM pg_stat_activity WHERE datname = '{SOURCE_DATABASE}'
  )
);
""",
        "source cleanup verification",
    )
    return {
        "marker_matched": True,
        "ordinary_drop": True,
        "force_drop_used": False,
        "unrelated_sessions_terminated": 0,
        "chapter_sessions_terminated": terminated,
        "subscription_drop_mode": subscription_drop_mode,
        "source": source_final,
        "target": target_final,
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, mode=0o700)
    output_dir.chmod(0o700)
    requirements = json.loads(
        (source_dir / "requirements.json").read_text(encoding="utf-8")
    )
    run_id = str(uuid.uuid4())
    source_password = secrets.token_urlsafe(32)
    target_password = secrets.token_urlsafe(32)
    replication_password = secrets.token_urlsafe(32)
    source_env = os.environ.copy()
    target_env = os.environ.copy()
    source_env["PGPASSWORD"] = source_password
    target_env["PGPASSWORD"] = target_password
    route_history: list[dict[str, Any]] = [
        {
            "at": utc_now(),
            "route": "source",
            "kind": "private-simulation-only",
            "platform_route_changed": False,
        }
    ]
    evidence: dict[str, Any] = {
        "schema": "pg36-ch29-migration-evidence-v1",
        "release": "1.0-sandbox",
        "captured_at": utc_now(),
        "run_id": run_id,
        "target": requirements["target"],
        "status": "running",
        "production_ch29_gate": "pending",
    }
    failure: BaseException | None = None
    try:
        fixture = create_fixture(
            run_id,
            source_password,
            target_password,
            replication_password,
            source_env,
            target_env,
        )
        if (
            fixture["source_system_identifier"]
            == fixture["target_system_identifier"]
            or fixture["source_credentials_equal_target_credentials"] is not False
        ):
            raise ExperimentError("fixture isolation postcondition failed")

        initial = wait_ready("initial-copy", timeout_seconds=180)
        if initial["source_manifest"]["customers"]["rows"] != 5000:
            raise ExperimentError("initial customer count changed")
        if initial["source_manifest"]["orders"]["rows"] != 20000:
            raise ExperimentError("initial order count changed")

        incremental_changes = runtime_json(
            side="source",
            password_env=source_env,
            label="incremental-dml",
            sql=r"""
WITH inserted AS (
  INSERT INTO shop.orders (
    customer_id, status, amount, created_at, updated_at, note
  )
  SELECT
    ((i - 1) % 5000) + 1,
    'paid',
    (50000 + i)::numeric / 100,
    timestamptz '2025-03-01 00:00:00+00'
      + (i * interval '1 second'),
    timestamptz '2025-03-01 00:00:00+00'
      + (i * interval '1 second'),
    'incremental-' || md5(i::text)
  FROM generate_series(1, 500) AS g(i)
  RETURNING 1
), updated AS (
  UPDATE shop.orders
  SET status = 'shipped',
      amount = amount + 1,
      updated_at = timestamptz '2025-03-02 00:00:00+00',
      note = note || '-updated'
  WHERE order_id BETWEEN 1 AND 200
  RETURNING 1
), deleted AS (
  DELETE FROM shop.orders
  WHERE order_id BETWEEN 19901 AND 20000
  RETURNING 1
)
SELECT jsonb_build_object(
  'inserted', (SELECT count(*) FROM inserted),
  'updated', (SELECT count(*) FROM updated),
  'deleted', (SELECT count(*) FROM deleted)
);
""",
            timeout=180,
        )
        incremental_marker = source_lsn()
        incremental = wait_ready(
            "incremental-catch-up",
            marker=incremental_marker,
            timeout_seconds=180,
        )

        disabled = set_subscription_enabled(False)
        stall_before = slot_state()
        stalled_changes = runtime_json(
            side="source",
            password_env=source_env,
            label="stalled-writes",
            sql=r"""
WITH inserted AS (
  INSERT INTO shop.orders (
    customer_id, status, amount, created_at, updated_at, note
  )
  SELECT
    ((i - 1) % 5000) + 1,
    'new',
    (70000 + i)::numeric / 100,
    timestamptz '2025-04-01 00:00:00+00'
      + (i * interval '1 second'),
    timestamptz '2025-04-01 00:00:00+00'
      + (i * interval '1 second'),
    repeat(md5(i::text), 20)
  FROM generate_series(1, 3000) AS g(i)
  RETURNING 1
)
SELECT jsonb_build_object('inserted', count(*)) FROM inserted;
""",
            timeout=180,
        )
        stall_marker = source_lsn()
        stall_after = slot_state()
        if (
            disabled["slot"].get("active") is not False
            or stall_before.get("confirmed_flush_lsn")
            != stall_after.get("confirmed_flush_lsn")
            or int(stall_after.get("retained_bytes", 0))
            <= int(stall_before.get("retained_bytes", 0))
            or stalled_changes != {"inserted": 3000}
        ):
            raise ExperimentError("bounded consumer stall was not observed")
        set_subscription_enabled(True)
        recovered = wait_ready(
            "consumer-recovered",
            marker=stall_marker,
            timeout_seconds=240,
        )

        set_subscription_enabled(False)
        conflict_before = subscription_state()["conflicts"]
        runtime_json(
            side="target",
            password_env=target_env,
            label="target-conflict-row",
            sql=f"""
INSERT INTO shop.orders (
  order_id, customer_id, status, amount, created_at, updated_at, note
) VALUES (
  {CONFLICT_ID}, 1, 'new', 1.00,
  timestamptz '2025-05-01 00:00:00+00',
  timestamptz '2025-05-01 00:00:00+00',
  'target-conflict'
)
RETURNING jsonb_build_object('order_id', order_id, 'note', note);
""",
        )
        runtime_json(
            side="source",
            password_env=source_env,
            label="source-conflict-row",
            sql=f"""
INSERT INTO shop.orders (
  order_id, customer_id, status, amount, created_at, updated_at, note
) VALUES (
  {CONFLICT_ID}, 1, 'paid', 2.00,
  timestamptz '2025-05-01 00:00:00+00',
  timestamptz '2025-05-01 00:00:01+00',
  'source-authority'
)
RETURNING jsonb_build_object('order_id', order_id, 'note', note);
""",
        )
        conflict_marker = source_lsn()
        set_subscription_enabled(True)
        conflict_observed: dict[str, Any] | None = None
        for _ in range(160):
            psql(
                target_admin(application="flush-conflict-stats"),
                sql="SELECT pg_stat_force_next_flush();\n",
                timeout=20,
            )
            current = subscription_state()
            current_conflicts = current.get("conflicts", {})
            if (
                int(current_conflicts.get("confl_insert_exists", 0))
                > int(conflict_before.get("confl_insert_exists", 0))
                and int(current_conflicts.get("apply_error_count", 0))
                > int(conflict_before.get("apply_error_count", 0))
            ):
                conflict_observed = current
                break
            time.sleep(0.25)
        if conflict_observed is None:
            raise ExperimentError("insert_exists conflict was not observed")
        set_subscription_enabled(False)
        conflict_rows = {
            "source": json_psql(
                source_admin(application="source-conflict-proof"),
                f"""
SELECT to_jsonb(o)
FROM (
  SELECT order_id, status, amount::text, note
  FROM shop.orders WHERE order_id = {CONFLICT_ID}
) AS o;
""",
                "source conflict proof",
            ),
            "target": json_psql(
                target_admin(application="target-conflict-proof"),
                f"""
SELECT to_jsonb(o)
FROM (
  SELECT order_id, status, amount::text, note
  FROM shop.orders WHERE order_id = {CONFLICT_ID}
) AS o;
""",
                "target conflict proof",
            ),
        }
        runtime_json(
            side="target",
            password_env=target_env,
            label="repair-conflict",
            sql=f"""
WITH deleted AS (
  DELETE FROM shop.orders
  WHERE order_id = {CONFLICT_ID}
    AND note = 'target-conflict'
  RETURNING 1
)
SELECT jsonb_build_object('deleted', count(*)) FROM deleted;
""",
        )
        set_subscription_enabled(True)
        conflict_repaired = wait_ready(
            "conflict-repaired",
            marker=conflict_marker,
            timeout_seconds=240,
        )

        set_subscription_enabled(False)
        drift_source_before = bucket_manifest(
            source_admin(application="drift-source-before"),
            "drift source before",
        )
        runtime_json(
            side="target",
            password_env=target_env,
            label="inject-silent-drift",
            sql=f"""
UPDATE shop.orders
SET note = note || '-target-only-drift',
    amount = amount + 0.01
WHERE order_id = {DRIFT_ID};
SELECT jsonb_build_object(
  'changed', count(*)
) FROM shop.orders
WHERE order_id = {DRIFT_ID}
  AND note LIKE '%-target-only-drift';
""",
        )
        drift_target_before = bucket_manifest(
            target_admin(application="drift-target-before"),
            "drift target before",
        )
        mismatch_before = differing_buckets(
            drift_source_before, drift_target_before
        )
        if mismatch_before != [DRIFT_ID % 16]:
            raise ExperimentError(
                f"silent drift was not isolated to one bucket: {mismatch_before}"
            )
        authoritative_row = json_psql(
            source_admin(application="drift-authority"),
            f"""
SELECT to_jsonb(o)
FROM (
  SELECT order_id, customer_id, status, amount::text,
         created_at::text, updated_at::text, note
  FROM shop.orders
  WHERE order_id = {DRIFT_ID}
) AS o;
""",
            "authoritative drift row",
        )
        repair_sql = f"""
UPDATE shop.orders
SET customer_id = {sql_literal(authoritative_row['customer_id'])},
    status = {sql_literal(authoritative_row['status'])},
    amount = {sql_literal(authoritative_row['amount'])}::numeric,
    created_at = {sql_literal(authoritative_row['created_at'])}::timestamptz,
    updated_at = {sql_literal(authoritative_row['updated_at'])}::timestamptz,
    note = {sql_literal(authoritative_row['note'])}
WHERE order_id = {DRIFT_ID};
"""
        psql(
            target_admin(application="repair-drift"),
            sql=repair_sql,
            timeout=30,
        )
        drift_source_after = bucket_manifest(
            source_admin(application="drift-source-after"),
            "drift source after",
        )
        drift_target_after = bucket_manifest(
            target_admin(application="drift-target-after"),
            "drift target after",
        )
        mismatch_after = differing_buckets(
            drift_source_after, drift_target_after
        )
        if mismatch_after:
            raise ExperimentError(f"silent drift repair failed: {mismatch_after}")
        set_subscription_enabled(True)
        post_drift = wait_ready(
            "post-drift",
            marker=conflict_marker,
            timeout_seconds=120,
        )

        fence_marker = source_lsn()
        wait_ready(
            "pre-fence",
            marker=fence_marker,
            timeout_seconds=120,
        )
        psql(
            source_admin(application="source-write-fence"),
            sql=f"""
REVOKE INSERT, UPDATE, DELETE
  ON shop.customers, shop.orders FROM {SOURCE_RUNTIME};
REVOKE USAGE, SELECT, UPDATE
  ON ALL SEQUENCES IN SCHEMA shop FROM {SOURCE_RUNTIME};
""",
            timeout=30,
        )
        denied = psql(
            runtime_connection(
                address=SOURCE_ADDRESS,
                database=SOURCE_DATABASE,
                user=SOURCE_RUNTIME,
                application="pg36-ch29-write-fence-proof",
            ),
            sql=r"""
\set VERBOSITY verbose
INSERT INTO shop.orders (
  customer_id, status, amount, created_at, updated_at, note
) VALUES (
  1, 'new', 1.00, clock_timestamp(), clock_timestamp(), 'must-fail'
);
""",
            env=source_env,
            timeout=30,
            check=False,
        )
        denied_sqlstate = None
        match = re.search(r"\b(42501)\b", denied.stderr)
        if match:
            denied_sqlstate = match.group(1)
        privilege_state = json_psql(
            source_admin(application="source-fence-catalog"),
            f"""
SELECT jsonb_build_object(
  'insert', has_table_privilege(
    '{SOURCE_RUNTIME}', 'shop.orders', 'INSERT'
  ),
  'update', has_table_privilege(
    '{SOURCE_RUNTIME}', 'shop.orders', 'UPDATE'
  ),
  'delete', has_table_privilege(
    '{SOURCE_RUNTIME}', 'shop.orders', 'DELETE'
  ),
  'select', has_table_privilege(
    '{SOURCE_RUNTIME}', 'shop.orders', 'SELECT'
  )
);
""",
            "source fence catalog",
        )
        if (
            denied.returncode == 0
            or denied_sqlstate != "42501"
            or privilege_state
            != {"insert": False, "update": False, "delete": False, "select": True}
        ):
            raise ExperimentError("source write fence was not proven")

        set_subscription_enabled(False)
        source_before_cutover = manifest(
            source_admin(application="source-before-cutover"),
            "source before cutover",
        )
        target_before_cutover = manifest(
            target_admin(application="target-before-cutover"),
            "target before cutover",
        )
        if logical_manifest(source_before_cutover) != logical_manifest(
            target_before_cutover
        ):
            raise ExperimentError("cutover manifests differ")
        source_max = int(source_before_cutover["orders"]["max_id"])
        target_sequence_before = int(
            target_before_cutover["order_sequence"]["last_value"]
        )
        sequence_after = json_psql(
            target_admin(application="target-sequence-sync"),
            f"""
SELECT jsonb_build_object(
  'set_to', setval(
    'shop.orders_order_id_seq',
    greatest(
      {source_max},
      (SELECT max(order_id) FROM shop.orders)
    ),
    true
  ),
  'max_order_id', (SELECT max(order_id) FROM shop.orders)
);
""",
            "target sequence synchronization",
        )
        route_history.append(
            {
                "at": utc_now(),
                "route": "target",
                "kind": "private-simulation-only",
                "platform_route_changed": False,
                "source_write_fenced": True,
                "manifests_equal": True,
            }
        )
        target_probe = runtime_json(
            side="target",
            password_env=target_env,
            label="target-route-probe",
            sql=r"""
SELECT jsonb_build_object(
  'customers', (SELECT count(*) FROM shop.customers),
  'orders', (SELECT count(*) FROM shop.orders),
  'orphan_orders', (
    SELECT count(*)
    FROM shop.orders AS o
    LEFT JOIN shop.customers AS c USING (customer_id)
    WHERE c.customer_id IS NULL
  )
);
""",
        )
        cutover_canary = runtime_json(
            side="target",
            password_env=target_env,
            label="target-cutover-canary",
            sql=r"""
INSERT INTO shop.orders (
  customer_id, status, amount, created_at, updated_at, note
) VALUES (
  1, 'new', 9.99, clock_timestamp(), clock_timestamp(),
  'target-cutover-canary'
)
RETURNING jsonb_build_object(
  'order_id', order_id,
  'note', note
);
""",
        )
        if int(cutover_canary["order_id"]) <= source_max:
            raise ExperimentError("target sequence was not safely synchronized")

        rollback_reconcile = runtime_json(
            side="target",
            password_env=target_env,
            label="rollback-reconcile",
            sql=f"""
WITH deleted AS (
  DELETE FROM shop.orders
  WHERE order_id = {int(cutover_canary['order_id'])}
    AND note = 'target-cutover-canary'
  RETURNING 1
)
SELECT jsonb_build_object('deleted', count(*)) FROM deleted;
""",
        )
        if rollback_reconcile != {"deleted": 1}:
            raise ExperimentError("target-only canary was not reconciled")
        route_history.append(
            {
                "at": utc_now(),
                "route": "source",
                "kind": "private-simulation-only",
                "platform_route_changed": False,
                "destination_only_rows_reconciled": 1,
                "source_retained": True,
            }
        )
        psql(
            source_admin(application="restore-source-writes"),
            sql=f"""
GRANT INSERT, UPDATE, DELETE
  ON shop.customers, shop.orders TO {SOURCE_RUNTIME};
GRANT USAGE, SELECT, UPDATE
  ON ALL SEQUENCES IN SCHEMA shop TO {SOURCE_RUNTIME};
""",
            timeout=30,
        )
        set_subscription_enabled(True)
        rollback_canary = runtime_json(
            side="source",
            password_env=source_env,
            label="source-rollback-canary",
            sql=r"""
INSERT INTO shop.orders (
  customer_id, status, amount, created_at, updated_at, note
) VALUES (
  1, 'paid', 8.88, clock_timestamp(), clock_timestamp(),
  'source-rollback-canary'
)
RETURNING jsonb_build_object(
  'order_id', order_id,
  'note', note
);
""",
        )
        rollback_marker = source_lsn()
        final_convergence = wait_ready(
            "rollback-converged",
            marker=rollback_marker,
            timeout_seconds=180,
        )
        write_json(output_dir / "route-history.json", route_history)

        evidence.update(
            {
                "status": "passed",
                "environment": {
                    "source_cluster": "pg-test",
                    "target_cluster": "pg-meta",
                    "source_system_identifier":
                        fixture["source_system_identifier"],
                    "target_system_identifier":
                        fixture["target_system_identifier"],
                    "distinct_system_identifiers": True,
                    "postgresql_major": 18,
                },
                "fixture": {
                    "initial": fixture["initial"],
                    "source_database": SOURCE_DATABASE,
                    "target_database": TARGET_DATABASE,
                    "publication": PUBLICATION,
                    "subscription": SUBSCRIPTION,
                    "slot": SLOT,
                    "source_target_credentials_isolated": True,
                    "replication_secret_published": False,
                },
                "initial_copy": initial,
                "incremental": {
                    "changes": incremental_changes,
                    "marker_lsn": incremental_marker,
                    "convergence": incremental,
                },
                "consumer_stall": {
                    "disabled_state": disabled,
                    "before": stall_before,
                    "changes": stalled_changes,
                    "marker_lsn": stall_marker,
                    "after": stall_after,
                    "confirmed_lsn_unchanged":
                        stall_before["confirmed_flush_lsn"]
                        == stall_after["confirmed_flush_lsn"],
                    "retained_bytes_grew":
                        int(stall_after["retained_bytes"])
                        > int(stall_before["retained_bytes"]),
                    "recovery": recovered,
                },
                "conflict": {
                    "id": CONFLICT_ID,
                    "before": conflict_before,
                    "observed": conflict_observed,
                    "source_and_target_rows_before_repair": conflict_rows,
                    "marker_lsn": conflict_marker,
                    "repair": conflict_repaired,
                },
                "silent_drift": {
                    "id": DRIFT_ID,
                    "mismatched_buckets_before": mismatch_before,
                    "mismatched_buckets_after": mismatch_after,
                    "authoritative_row_digest":
                        drift_source_after[DRIFT_ID % 16]["digest"],
                    "post_repair": post_drift,
                },
                "cutover_and_rollback": {
                    "source_fence_lsn": fence_marker,
                    "write_fence": {
                        "attempt_return_code": denied.returncode,
                        "sqlstate": denied_sqlstate,
                        "privileges": privilege_state,
                    },
                    "target_sequence_before": target_sequence_before,
                    "target_sequence_after": sequence_after,
                    "source_max_order_id": source_max,
                    "target_route_probe": target_probe,
                    "target_cutover_canary": cutover_canary,
                    "target_only_rows_reconciled": 1,
                    "source_rollback_canary": rollback_canary,
                    "final_convergence": final_convergence,
                    "route_history": route_history,
                    "actual_platform_route_changed": False,
                    "source_retained_through_rollback": True,
                },
                "safety": {
                    "production_data_touched": False,
                    "production_traffic_touched": False,
                    "persistent_cluster_configuration_change": False,
                    "pigsty_inventory_changed": False,
                    "patroni_configuration_changed": False,
                    "actual_platform_route_changed": False,
                    "unrelated_subscription_changed": False,
                    "unrelated_slot_changed": False,
                    "force_drop_used": False,
                },
            }
        )
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["failure_type"] = type(exc).__name__
        failure = exc
    finally:
        cleanup = cleanup_fixture(run_id)
        evidence["cleanup"] = cleanup
        if evidence.get("status") == "passed":
            source_clean = cleanup.get("source", {})
            target_clean = cleanup.get("target", {})
            if (
                any(value is not True for key, value in source_clean.items()
                    if key.endswith("_absent"))
                or any(value is not True for key, value in target_clean.items()
                    if key.endswith("_absent"))
                or source_clean.get("sessions_remaining") != 0
                or target_clean.get("sessions_remaining") != 0
                or cleanup.get("unrelated_sessions_terminated") != 0
                or cleanup.get("force_drop_used") is not False
            ):
                evidence["status"] = "failed-cleanup"
        write_json(output_dir / "migration-evidence.json", evidence)
    if failure is not None:
        raise failure
    if evidence["status"] != "passed":
        raise ExperimentError(f"migration experiment ended with {evidence['status']}")
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run_id,
                "initial_orders": evidence["initial_copy"]["source_manifest"][
                    "orders"
                ]["rows"],
                "stall_retained_bytes":
                    evidence["consumer_stall"]["after"]["retained_bytes"],
                "insert_conflict_observed": True,
                "silent_drift_repaired": True,
                "simulated_cutover_and_rollback": True,
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
        print(f"chapter 29 remote experiment failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
