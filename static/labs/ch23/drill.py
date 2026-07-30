#!/usr/bin/env python3
"""Run the guarded chapter 23 identity, RLS, TLS, and pooling lab."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import psycopg

from capture import capture_snapshot
from common import (
    LabError,
    ensure_no_secret_material,
    load_private_inventory,
    pgbouncer_pools,
    read_json,
    reconnect_database,
    remote_json_psql,
    remote_psql,
    remote_python_json,
    run,
    selected_pool_settings,
    set_pgbouncer_config,
    sha256,
    ssh_base,
    topology_stable,
    utc_now,
    write_json,
)


FIXTURE_PROJECTION_SQL = r"""
SELECT json_build_object(
  'schema', 'pg36-ch23-fixture-projection-v1',
  'roles', (
    SELECT json_agg(
      json_build_object(
        'name', roles.rolname,
        'login', roles.rolcanlogin,
        'superuser', roles.rolsuper,
        'create_db', roles.rolcreatedb,
        'create_role', roles.rolcreaterole,
        'replication', roles.rolreplication,
        'bypass_rls', roles.rolbypassrls,
        'inherit_default', roles.rolinherit,
        'password_present',
          EXISTS (
            SELECT 1 FROM pg_authid AS auth
            WHERE auth.oid = roles.oid
              AND auth.rolpassword IS NOT NULL
          ),
        'comment', shobj_description(roles.oid, 'pg_authid')
      )
      ORDER BY roles.rolname
    )
    FROM pg_roles AS roles
    WHERE roles.rolname LIKE 'pg36_ch23_%'
  ),
  'memberships', (
    SELECT json_agg(
      json_build_object(
        'role', granted.rolname,
        'member', member.rolname,
        'grantor', grantor.rolname,
        'admin', membership.admin_option,
        'inherit', membership.inherit_option,
        'set', membership.set_option
      )
      ORDER BY granted.rolname, member.rolname
    )
    FROM pg_auth_members AS membership
    JOIN pg_roles AS granted ON granted.oid = membership.roleid
    JOIN pg_roles AS member ON member.oid = membership.member
    JOIN pg_roles AS grantor ON grantor.oid = membership.grantor
    WHERE granted.rolname LIKE 'pg36_ch23_%'
       OR member.rolname LIKE 'pg36_ch23_%'
  ),
  'schema_object', (
    SELECT json_build_object(
      'name', namespace.nspname,
      'owner', pg_get_userbyid(namespace.nspowner),
      'comment', obj_description(namespace.oid, 'pg_namespace'),
      'public_create',
        has_schema_privilege('public', namespace.oid, 'CREATE'),
      'runtime_usage',
        has_schema_privilege(
          'pg36_ch23_runtime', namespace.oid, 'USAGE'
        ),
      'runtime_create',
        has_schema_privilege(
          'pg36_ch23_runtime', namespace.oid, 'CREATE'
        ),
      'readonly_usage',
        has_schema_privilege(
          'pg36_ch23_readonly', namespace.oid, 'USAGE'
        )
    )
    FROM pg_namespace AS namespace
    WHERE namespace.nspname = 'pg36_ch23'
  ),
  'table_object', (
    SELECT json_build_object(
      'name', class.oid::regclass::text,
      'owner', pg_get_userbyid(class.relowner),
      'row_security', class.relrowsecurity,
      'force_row_security', class.relforcerowsecurity,
      'comment', obj_description(class.oid, 'pg_class'),
      'runtime', json_build_object(
        'select', has_table_privilege(
          'pg36_ch23_runtime', class.oid, 'SELECT'
        ),
        'insert', has_table_privilege(
          'pg36_ch23_runtime', class.oid, 'INSERT'
        ),
        'update', has_table_privilege(
          'pg36_ch23_runtime', class.oid, 'UPDATE'
        ),
        'delete', has_table_privilege(
          'pg36_ch23_runtime', class.oid, 'DELETE'
        ),
        'truncate', has_table_privilege(
          'pg36_ch23_runtime', class.oid, 'TRUNCATE'
        )
      ),
      'readonly', json_build_object(
        'select', has_table_privilege(
          'pg36_ch23_readonly', class.oid, 'SELECT'
        ),
        'insert', has_table_privilege(
          'pg36_ch23_readonly', class.oid, 'INSERT'
        ),
        'update', has_table_privilege(
          'pg36_ch23_readonly', class.oid, 'UPDATE'
        )
      ),
      'raw_login_select',
        has_table_privilege('test', class.oid, 'SELECT')
    )
    FROM pg_class AS class
    WHERE class.oid = 'pg36_ch23.account'::regclass
  ),
  'policies', (
    SELECT json_agg(
      json_build_object(
        'name', policyname,
        'permissive', permissive,
        'roles', roles,
        'command', cmd,
        'using', qual,
        'with_check', with_check
      )
      ORDER BY policyname
    )
    FROM pg_policies
    WHERE schemaname = 'pg36_ch23'
      AND tablename = 'account'
  ),
  'tenant_counts', (
    SELECT json_object_agg(tenant_id::text, row_count ORDER BY tenant_id)
    FROM (
      SELECT tenant_id, count(*) AS row_count
      FROM pg36_ch23.account
      GROUP BY tenant_id
    ) AS counts
  ),
  'row_count', (
    SELECT count(*) FROM pg36_ch23.account
  ),
  'secret_values_exported', false
);
"""


OWNER_TEST_PROGRAM = r"""
import json
import sys
import psycopg2

payload = json.load(sys.stdin)
connection = psycopg2.connect(
    dbname="test",
    application_name="pg36_ch23_owner_probe",
)
connection.autocommit = True
result = {"schema": "pg36-ch23-owner-tests-v1"}
try:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.tenant_id")
        cursor.execute(
            "SET SESSION AUTHORIZATION pg36_ch23_owner"
        )
        cursor.execute(
            "SELECT count(*) FROM pg36_ch23.account"
        )
        result["owner_without_context_rows"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, false)",
            (payload["tenant_a"],),
        )
        cursor.execute(
            "SELECT count(*), min(tenant_id::text), "
            "max(tenant_id::text) FROM pg36_ch23.account"
        )
        row = cursor.fetchone()
        result["owner_tenant_a"] = {
            "rows": row[0],
            "minimum_tenant": row[1],
            "maximum_tenant": row[2],
        }
        cursor.execute("RESET SESSION AUTHORIZATION")
        cursor.execute("RESET app.tenant_id")

        cursor.execute(
            "SET SESSION AUTHORIZATION pg36_ch23_migrate"
        )
        cursor.execute("SET ROLE pg36_ch23_owner")
        cursor.execute(
            "SELECT session_user, current_user"
        )
        row = cursor.fetchone()
        result["migration_role_chain"] = {
            "session_user": row[0],
            "current_user": row[1],
        }
        cursor.execute("RESET SESSION AUTHORIZATION")

        cursor.execute(
            "SELECT count(*) FROM pg36_ch23.account"
        )
        result["superuser_break_glass_rows"] = cursor.fetchone()[0]
finally:
    connection.close()
print(json.dumps(result, sort_keys=True))
"""


ROLE_MUTATION_PROGRAM = r"""
import json
import sys
import psycopg2

payload = json.load(sys.stdin)
if payload.get("role") != "pg36_ch23_rotate":
    raise SystemExit("role allowlist rejected")
action = payload.get("action")
if action not in {
    "login-with-password",
    "change-password",
    "disable-login",
    "revoke-password",
}:
    raise SystemExit("action allowlist rejected")

connection = psycopg2.connect(
    dbname="test",
    application_name="pg36_ch23_rotation_admin",
)
connection.autocommit = False
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT shobj_description(oid, 'pg_authid') "
            "FROM pg_roles WHERE rolname = %s",
            (payload["role"],),
        )
        row = cursor.fetchone()
        if row is None or row[0] != (
            "pg36 chapter 23 security lab: direct-only "
            "rotation probe; synthetic fixture only"
        ):
            raise RuntimeError("rotation role identity guard failed")

        cursor.execute("SET LOCAL log_statement = 'none'")
        if action == "login-with-password":
            cursor.execute(
                "ALTER ROLE pg36_ch23_rotate LOGIN PASSWORD %s",
                (payload["password"],),
            )
        elif action == "change-password":
            cursor.execute(
                "ALTER ROLE pg36_ch23_rotate PASSWORD %s",
                (payload["password"],),
            )
        elif action == "disable-login":
            cursor.execute(
                "ALTER ROLE pg36_ch23_rotate NOLOGIN"
            )
        else:
            cursor.execute(
                "ALTER ROLE pg36_ch23_rotate NOLOGIN PASSWORD NULL"
            )

        cursor.execute(
            "SELECT rolcanlogin, rolpassword IS NOT NULL "
            "FROM pg_authid WHERE rolname = %s",
            (payload["role"],),
        )
        state = cursor.fetchone()
    connection.commit()
finally:
    connection.close()
print(json.dumps({
    "role": "pg36_ch23_rotate",
    "action": action,
    "can_login": state[0],
    "password_present": state[1],
    "secret_exported": False,
}, sort_keys=True))
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--credential-inventory", type=Path, required=True)
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
        args.target_token != target["id"]
        or args.target_token != "pg36-l2-vagrant/pg-test"
        or args.confirmation != "SECURITY_RLS_ROTATION_CH23"
        or args.authority != "nonproduction-synthetic-data-only"
        or target["production_data_permitted"] is not False
        or target["production_traffic_permitted"] is not False
    ):
        raise LabError("direct security-drill authority guard failed")
    if args.output.exists() and any(args.output.iterdir()):
        raise LabError("refusing to overwrite a non-empty evidence directory")
    source = args.source_dir.resolve()
    inventory = args.credential_inventory.resolve()
    if inventory == source or source in inventory.parents:
        raise LabError("private credential inventory cannot be in source tree")


def connection_error(exc: BaseException) -> dict[str, Any]:
    message = str(exc).lower()
    if "does not match host name" in message or "hostname" in message:
        category = "certificate-name-mismatch"
    elif "server does not support ssl" in message:
        category = "server-no-client-tls"
    elif "password authentication failed" in message:
        category = "credential-rejected"
    elif "not permitted to log in" in message:
        category = "login-disabled"
    elif "no such user" in message or "unknown user" in message:
        category = "pool-user-absent"
    else:
        category = "connection-rejected"
    return {
        "connected": False,
        "sqlstate": getattr(exc, "sqlstate", None),
        "error_type": type(exc).__name__,
        "category": category,
        "message_redacted": True,
    }


def endpoint_kwargs(
    requirements: dict[str, Any],
    password: str,
    *,
    port: int,
    sslmode: str,
    role: str = "test",
    verify_name: str | None = None,
    root_certificate: Path | None = None,
    channel_binding: str | None = None,
) -> dict[str, Any]:
    entry = str(requirements["target"]["entry_address"])
    values: dict[str, Any] = {
        "host": verify_name or entry,
        "port": port,
        "dbname": requirements["target"]["database"],
        "user": role,
        "password": password,
        "sslmode": sslmode,
        "connect_timeout": 4,
        "application_name": "pg36_ch23_security_lab",
    }
    if verify_name is not None:
        values["hostaddr"] = entry
    if root_certificate is not None:
        values["sslrootcert"] = str(root_certificate)
    if channel_binding is not None:
        values["channel_binding"] = channel_binding
    return values


def copy_public_ca(
    requirements: dict[str, Any],
    ssh_user: str,
    destination: Path,
) -> None:
    host = str(requirements["target"]["entry_address"])
    result = run(
        ssh_base(ssh_user, host)
        + ["sudo -n cat /pg/cert/ca.crt"],
        timeout=10,
    )
    text = str(result.stdout)
    if (
        "-----BEGIN CERTIFICATE-----" not in text
        or "PRIVATE KEY" in text
    ):
        raise LabError("CA projection is not a public certificate")
    destination.write_text(text, encoding="ascii")
    destination.chmod(0o600)


def tls_case(
    name: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    started = utc_now(milliseconds=True)
    try:
        with psycopg.connect(**kwargs) as connection:
            row = connection.execute(
                """
                SELECT json_build_object(
                  'ssl', ssl.ssl,
                  'version', ssl.version,
                  'cipher', ssl.cipher,
                  'bits', ssl.bits,
                  'client_dn', ssl.client_dn,
                  'session_user', session_user,
                  'current_user', current_user,
                  'backend_pid', pg_backend_pid(),
                  'in_recovery', pg_is_in_recovery(),
                  'server_address', inet_server_addr()::text
                )
                FROM pg_stat_ssl AS ssl
                WHERE ssl.pid = pg_backend_pid()
                """
            ).fetchone()[0]
        return {
            "case": name,
            "started_at": started,
            "connected": True,
            "observation": row,
        }
    except Exception as exc:
        return {
            "case": name,
            "started_at": started,
            **connection_error(exc),
        }


def run_tls_tests(
    requirements: dict[str, Any],
    password: str,
    ca_path: Path,
) -> dict[str, Any]:
    direct_port = int(
        requirements["entrypoints"]["direct_primary"]["port"]
    )
    pooled_port = int(
        requirements["entrypoints"]["pooled_primary"]["port"]
    )
    cases = [
        tls_case(
            "direct-require",
            endpoint_kwargs(
                requirements,
                password,
                port=direct_port,
                sslmode="require",
            ),
        ),
        tls_case(
            "direct-verify-full",
            endpoint_kwargs(
                requirements,
                password,
                port=direct_port,
                sslmode="verify-full",
                verify_name="pg-test-1",
                root_certificate=ca_path,
            ),
        ),
        tls_case(
            "direct-wrong-name",
            endpoint_kwargs(
                requirements,
                password,
                port=direct_port,
                sslmode="verify-full",
                verify_name="wrong.invalid",
                root_certificate=ca_path,
            ),
        ),
        tls_case(
            "direct-disable",
            endpoint_kwargs(
                requirements,
                password,
                port=direct_port,
                sslmode="disable",
            ),
        ),
        tls_case(
            "direct-verify-full-channel-binding",
            endpoint_kwargs(
                requirements,
                password,
                port=direct_port,
                sslmode="verify-full",
                verify_name="pg-test-1",
                root_certificate=ca_path,
                channel_binding="require",
            ),
        ),
        tls_case(
            "pooled-disable",
            endpoint_kwargs(
                requirements,
                password,
                port=pooled_port,
                sslmode="disable",
            ),
        ),
        tls_case(
            "pooled-require",
            endpoint_kwargs(
                requirements,
                password,
                port=pooled_port,
                sslmode="require",
            ),
        ),
    ]
    return {
        "schema": "pg36-ch23-tls-tests-v1",
        "captured_at": utc_now(milliseconds=True),
        "cases": cases,
        "interpretation": {
            "direct_encryption_available": True,
            "direct_server_identity_verified_in_named_case": True,
            "sslmode_require_authenticates_server": False,
            "direct_tls_enforced_by_hba": False,
            "pool_client_tls_available": False,
            "production_transport_gate": "pending",
        },
        "private_key_read": False,
        "credential_exported": False,
    }


def application_connection(
    requirements: dict[str, Any],
    password: str,
) -> psycopg.Connection[Any]:
    values = endpoint_kwargs(
        requirements,
        password,
        port=int(
            requirements["entrypoints"]["pooled_primary"]["port"]
        ),
        sslmode="disable",
    )
    connection = psycopg.connect(**values)
    connection.autocommit = True
    return connection


def transaction_case(
    requirements: dict[str, Any],
    password: str,
    *,
    name: str,
    effective_role: str | None,
    tenant: str | None,
    operation: Callable[[psycopg.Connection[Any]], Any],
    commit: bool = False,
) -> dict[str, Any]:
    connection = application_connection(requirements, password)
    try:
        connection.execute("BEGIN")
        if effective_role is not None:
            if effective_role not in {
                "pg36_ch23_runtime",
                "pg36_ch23_readonly",
            }:
                raise LabError("effective role crossed the allowlist")
            connection.execute(f"SET LOCAL ROLE {effective_role}")
        if tenant is not None:
            connection.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (tenant,),
            )
        value = operation(connection)
        connection.execute("COMMIT" if commit else "ROLLBACK")
        return {
            "case": name,
            "accepted": True,
            "result": value,
        }
    except Exception as exc:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        return {
            "case": name,
            "accepted": False,
            "sqlstate": getattr(exc, "sqlstate", None),
            "error_type": type(exc).__name__,
            "message_redacted": True,
        }
    finally:
        connection.close()


def selected_rows(
    connection: psycopg.Connection[Any],
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT tenant_id::text, account_id::text, display_name
        FROM pg36_ch23.account
        ORDER BY tenant_id, account_id
        """
    ).fetchall()
    return {
        "backend_pid": connection.execute(
            "SELECT pg_backend_pid()"
        ).fetchone()[0],
        "rows": [
            {
                "tenant_id": row[0],
                "account_id": row[1],
                "display_name": row[2],
            }
            for row in rows
        ],
        "secret_note_exported": False,
    }


def run_rls_tests(
    requirements: dict[str, Any],
    password: str,
    ssh_user: str,
) -> dict[str, Any]:
    fixture = requirements["fixture"]
    tenant_a = str(fixture["tenant_a"])
    tenant_b = str(fixture["tenant_b"])
    cases: list[dict[str, Any]] = []
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-select-tenant-a",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=selected_rows,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-select-tenant-b",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_b,
            operation=selected_rows,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-missing-context",
            effective_role="pg36_ch23_runtime",
            tenant=None,
            operation=lambda connection: {
                "rows": connection.execute(
                    "SELECT count(*) FROM pg36_ch23.account"
                ).fetchone()[0],
                "tenant": connection.execute(
                    "SELECT pg36_ch23.current_tenant()::text"
                ).fetchone()[0],
            },
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-invalid-context",
            effective_role="pg36_ch23_runtime",
            tenant="not-a-uuid",
            operation=lambda connection: connection.execute(
                "SELECT count(*) FROM pg36_ch23.account"
            ).fetchone()[0],
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-cross-tenant-insert",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                """
                INSERT INTO pg36_ch23.account (
                  tenant_id, account_id, display_name,
                  balance_cents, secret_note
                )
                VALUES (
                  %s,
                  'cccccccc-cccc-4ccc-8ccc-ccccccccccc1',
                  'forbidden-cross-tenant-row',
                  1,
                  'synthetic rejected value'
                )
                """,
                (tenant_b,),
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-cross-tenant-update",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                """
                UPDATE pg36_ch23.account
                   SET tenant_id = %s
                 WHERE tenant_id = %s
                   AND account_id =
                       'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
                """,
                (tenant_b, tenant_a),
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-disable-rls",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                "ALTER TABLE pg36_ch23.account "
                "DISABLE ROW LEVEL SECURITY"
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-create-in-schema",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                "CREATE TABLE pg36_ch23.forbidden(id integer)"
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="runtime-truncate",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                "TRUNCATE pg36_ch23.account"
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="readonly-insert",
            effective_role="pg36_ch23_readonly",
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                """
                INSERT INTO pg36_ch23.account (
                  tenant_id, account_id, display_name,
                  balance_cents, secret_note
                )
                VALUES (
                  %s,
                  'dddddddd-dddd-4ddd-8ddd-ddddddddddd1',
                  'forbidden-readonly-row',
                  1,
                  'synthetic rejected value'
                )
                """,
                (tenant_a,),
            ).rowcount,
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="row-security-off-is-not-bypass",
            effective_role="pg36_ch23_runtime",
            tenant=tenant_a,
            operation=lambda connection: (
                connection.execute("SET LOCAL row_security = off"),
                connection.execute(
                    "SELECT count(*) FROM pg36_ch23.account"
                ).fetchone()[0],
            )[1],
        )
    )
    cases.append(
        transaction_case(
            requirements,
            password,
            name="raw-login-without-effective-role",
            effective_role=None,
            tenant=tenant_a,
            operation=lambda connection: connection.execute(
                "SELECT count(*) FROM pg36_ch23.account"
            ).fetchone()[0],
        )
    )

    host = str(
        requirements["target"]["members"][
            requirements["target"]["expected_leader"]
        ]
    )
    owner_tests = remote_python_json(
        ssh_user,
        host,
        OWNER_TEST_PROGRAM,
        {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
        },
        timeout=30,
    )
    return {
        "schema": "pg36-ch23-rls-tests-v1",
        "captured_at": utc_now(milliseconds=True),
        "cases": cases,
        "owner_and_break_glass": owner_tests,
        "tenant_context_source": "synthetic authorized application mapping",
        "end_user_input_trusted_directly": False,
    }


def active_pool_clients(
    ssh_user: str,
    host: str,
) -> int:
    total = 0
    for row in pgbouncer_pools(ssh_user, host):
        if row.get("database") != "test" or row.get("user") != "test":
            continue
        for key in ("cl_active", "cl_waiting", "cl_cancel_req"):
            raw = row.get(key)
            if raw not in {None, ""}:
                total += int(raw)
    return total


def pool_transaction(
    connection: psycopg.Connection[Any],
    *,
    role: str,
    tenant: str | None,
) -> dict[str, Any]:
    connection.execute("BEGIN")
    connection.execute(f"SET LOCAL ROLE {role}")
    if tenant is not None:
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (tenant,),
        )
    row = connection.execute(
        """
        SELECT pg_backend_pid(),
               pg36_ch23.current_tenant()::text,
               count(*),
               min(tenant_id::text),
               max(tenant_id::text)
        FROM pg36_ch23.account
        """
    ).fetchone()
    connection.execute("COMMIT")
    return {
        "backend_pid": row[0],
        "effective_tenant": row[1],
        "rows": row[2],
        "minimum_tenant": row[3],
        "maximum_tenant": row[4],
    }


def run_pool_context(
    requirements: dict[str, Any],
    password: str,
    ssh_user: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target = requirements["target"]
    hosts = [
        str(target["members"][name])
        for name in sorted(target["members"])
    ]
    entry = str(target["entry_address"])
    if active_pool_clients(ssh_user, entry) != 0:
        raise LabError("test pool has active clients before the context drill")
    before = selected_pool_settings(ssh_user, entry)
    override = {
        "default_pool_size": int(
            requirements["pool_policy"]["lab_override"][
                "default_pool_size"
            ]
        ),
        "reserve_pool_size": int(
            requirements["pool_policy"]["lab_override"][
                "reserve_pool_size"
            ]
        ),
        "reserve_pool_timeout": before["reserve_pool_timeout"],
        "query_wait_timeout": int(
            requirements["pool_policy"]["lab_override"][
                "query_wait_timeout"
            ]
        ),
    }
    tenant_a = str(requirements["fixture"]["tenant_a"])
    tenant_b = str(requirements["fixture"]["tenant_b"])
    observations: dict[str, Any] = {
        "schema": "pg36-ch23-pool-context-v1",
        "captured_at": utc_now(milliseconds=True),
        "before": before,
        "override": override,
    }
    restore: dict[str, Any] = {
        "schema": "pg36-ch23-pool-restore-v1",
        "before": before,
        "restored": False,
        "pool_reconnected_on": [],
    }
    try:
        set_pgbouncer_config(ssh_user, entry, override)
        for host in hosts:
            reconnect_database(ssh_user, host, "test")
        time.sleep(0.5)
        observations["applied"] = selected_pool_settings(
            ssh_user,
            entry,
        )

        client_a = application_connection(requirements, password)
        try:
            client_a.execute(
                "SELECT set_config('app.tenant_id', %s, false)",
                (tenant_a,),
            )
            leak_a = pool_transaction(
                client_a,
                role="pg36_ch23_runtime",
                tenant=None,
            )
        finally:
            client_a.close()

        client_b = application_connection(requirements, password)
        try:
            leak_b = pool_transaction(
                client_b,
                role="pg36_ch23_runtime",
                tenant=None,
            )
        finally:
            client_b.close()
        observations["session_set_counterexample"] = {
            "client_a": leak_a,
            "client_b_without_context": leak_b,
            "same_backend":
                leak_a["backend_pid"] == leak_b["backend_pid"],
            "tenant_a_leaked_to_client_b":
                leak_b["effective_tenant"] == tenant_a
                and leak_b["rows"]
                == requirements["fixture"]["rows_per_tenant"],
            "supported_pattern": False,
        }

        for host in hosts:
            reconnect_database(ssh_user, host, "test")
        time.sleep(0.5)

        secure_a_connection = application_connection(
            requirements,
            password,
        )
        try:
            secure_a = pool_transaction(
                secure_a_connection,
                role="pg36_ch23_runtime",
                tenant=tenant_a,
            )
        finally:
            secure_a_connection.close()

        missing_connection = application_connection(
            requirements,
            password,
        )
        try:
            missing = pool_transaction(
                missing_connection,
                role="pg36_ch23_runtime",
                tenant=None,
            )
        finally:
            missing_connection.close()

        secure_b_connection = application_connection(
            requirements,
            password,
        )
        try:
            secure_b = pool_transaction(
                secure_b_connection,
                role="pg36_ch23_runtime",
                tenant=tenant_b,
            )
        finally:
            secure_b_connection.close()

        missing_after_connection = application_connection(
            requirements,
            password,
        )
        try:
            missing_after = pool_transaction(
                missing_after_connection,
                role="pg36_ch23_runtime",
                tenant=None,
            )
        finally:
            missing_after_connection.close()

        observations["transaction_local_contract"] = {
            "tenant_a": secure_a,
            "missing_after_a": missing,
            "tenant_b": secure_b,
            "missing_after_b": missing_after,
            "supported_pattern": True,
        }
    finally:
        set_pgbouncer_config(ssh_user, entry, before)
        for host in hosts:
            reconnect_database(ssh_user, host, "test")
            restore["pool_reconnected_on"].append(host)
        time.sleep(0.5)
        restore["after"] = selected_pool_settings(ssh_user, entry)
        restore["restored"] = restore["after"] == before
        restore["captured_at"] = utc_now(milliseconds=True)
    return observations, restore


def mutate_rotation_role(
    requirements: dict[str, Any],
    ssh_user: str,
    *,
    action: str,
    password: str | None = None,
) -> dict[str, Any]:
    host = str(
        requirements["target"]["members"][
            requirements["target"]["expected_leader"]
        ]
    )
    payload: dict[str, Any] = {
        "role": "pg36_ch23_rotate",
        "action": action,
    }
    if password is not None:
        payload["password"] = password
    return remote_python_json(
        ssh_user,
        host,
        ROLE_MUTATION_PROGRAM,
        payload,
        timeout=30,
    )


def rotation_connection(
    requirements: dict[str, Any],
    password: str,
    *,
    pooled: bool = False,
) -> psycopg.Connection[Any]:
    port = int(
        requirements["entrypoints"][
            "pooled_primary" if pooled else "direct_primary"
        ]["port"]
    )
    values = endpoint_kwargs(
        requirements,
        password,
        port=port,
        sslmode="disable" if pooled else "require",
        role="pg36_ch23_rotate",
    )
    connection = psycopg.connect(**values)
    connection.autocommit = True
    return connection


def rotation_connect_case(
    requirements: dict[str, Any],
    password: str,
    *,
    name: str,
    pooled: bool = False,
) -> dict[str, Any]:
    try:
        with rotation_connection(
            requirements,
            password,
            pooled=pooled,
        ) as connection:
            row = connection.execute(
                "SELECT session_user, current_user, pg_backend_pid()"
            ).fetchone()
        return {
            "case": name,
            "connected": True,
            "session_user": row[0],
            "current_user": row[1],
            "backend_pid": row[2],
        }
    except Exception as exc:
        return {"case": name, **connection_error(exc)}


def existing_session_case(
    connection: psycopg.Connection[Any],
    name: str,
) -> dict[str, Any]:
    try:
        row = connection.execute(
            "SELECT session_user, current_user, pg_backend_pid(), 1"
        ).fetchone()
        return {
            "case": name,
            "still_usable": row[3] == 1,
            "session_user": row[0],
            "current_user": row[1],
            "backend_pid": row[2],
        }
    except Exception as exc:
        return {
            "case": name,
            "still_usable": False,
            **connection_error(exc),
        }


def run_rotation_tests(
    requirements: dict[str, Any],
    ssh_user: str,
) -> dict[str, Any]:
    secret_one = secrets.token_urlsafe(32)
    secret_two = secrets.token_urlsafe(32)
    if secret_one == secret_two:
        raise LabError("credential generator repeated a secret")
    events: list[dict[str, Any]] = []
    existing: psycopg.Connection[Any] | None = None
    try:
        events.append(
            mutate_rotation_role(
                requirements,
                ssh_user,
                action="login-with-password",
                password=secret_one,
            )
        )
        events.append(
            rotation_connect_case(
                requirements,
                secret_one,
                name="new-connection-secret-one",
            )
        )
        events.append(
            rotation_connect_case(
                requirements,
                secret_one,
                name="pool-user-not-declared",
                pooled=True,
            )
        )
        existing = rotation_connection(requirements, secret_one)
        events.append(
            existing_session_case(
                existing,
                "existing-session-before-rotation",
            )
        )

        events.append(
            mutate_rotation_role(
                requirements,
                ssh_user,
                action="change-password",
                password=secret_two,
            )
        )
        events.append(
            rotation_connect_case(
                requirements,
                secret_one,
                name="old-secret-new-connection",
            )
        )
        events.append(
            rotation_connect_case(
                requirements,
                secret_two,
                name="new-secret-new-connection",
            )
        )
        events.append(
            existing_session_case(
                existing,
                "existing-session-after-password-change",
            )
        )

        events.append(
            mutate_rotation_role(
                requirements,
                ssh_user,
                action="disable-login",
            )
        )
        events.append(
            rotation_connect_case(
                requirements,
                secret_two,
                name="new-connection-after-nologin",
            )
        )
        events.append(
            existing_session_case(
                existing,
                "existing-session-after-nologin",
            )
        )
    finally:
        if existing is not None:
            existing.close()
        final_state = mutate_rotation_role(
            requirements,
            ssh_user,
            action="revoke-password",
        )
    events.append(final_state)
    events.append(
        rotation_connect_case(
            requirements,
            secret_two,
            name="new-connection-after-password-null",
        )
    )
    secret_one = ""
    secret_two = ""
    return {
        "schema": "pg36-ch23-rotation-tests-v1",
        "captured_at": utc_now(milliseconds=True),
        "events": events,
        "final_state": final_state,
        "credential_generation": {
            "source": "Python secrets module",
            "values_exported": False,
            "shell_arguments_used": False,
            "server_log_statement_suppressed_for_password_ddl": True,
        },
        "interpretation": {
            "password_change_affects_new_authentication": True,
            "password_change_terminates_existing_sessions": False,
            "nologin_affects_new_authentication": True,
            "nologin_terminates_existing_sessions": False,
            "pool_auth_surface_is_separate": True,
        },
    }


def build_manifest(
    requirements: dict[str, Any],
    source_dir: Path,
    output: Path,
    *,
    run_id: str,
    started_at: str,
) -> dict[str, Any]:
    evidence_names = requirements["required_evidence"]
    evidence_hashes = {
        name: sha256(output / name)
        for name in evidence_names
        if name != "drill-manifest.json"
    }
    source_names = [
        "requirements.json",
        "role-contract.json",
        "threat-model.json",
        "tenant-contract.json",
        "negative-cases.json",
        "setup.sql",
        "common.py",
        "capture.py",
        "drill.py",
        "validate.py",
        "review.py",
        "task.sh",
    ]
    return {
        "schema": "pg36-ch23-drill-manifest-v1",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now(milliseconds=True),
        "target": requirements["target"]["id"],
        "authority": "nonproduction-synthetic-data-only",
        "mutations": [
            "converge and retain bounded synthetic roles, schema, function, table, policies, and grants",
            "temporarily set one PgBouncer pool to one server connection",
            "rotate and revoke one synthetic direct-only credential"
        ],
        "mutations_restored": {
            "pool_settings": True,
            "rotation_login": False,
            "rotation_password": None,
            "synthetic_fixture_retained": True
        },
        "topology_changed": False,
        "production_gate": "pending",
        "credential_values_exported": False,
        "private_key_read": False,
        "ordinary_postgresql_logging_is_complete_audit": False,
        "reset_guard_contract": {
            "exact_target_required": True,
            "nonproduction_required": True,
            "synthetic_data_required": True,
            "separate_destructive_confirmation_required": True
        },
        "source_sha256": {
            name: sha256(source_dir / name)
            for name in source_names
        },
        "evidence_sha256": evidence_hashes,
    }


def run_drill(args: argparse.Namespace) -> None:
    requirements = read_json(args.requirements)
    require_authority(args, requirements)
    password, inventory_projection = load_private_inventory(
        args.credential_inventory,
        expected_cluster="pg-test",
        expected_login=requirements["fixture"]["login_role"],
    )
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    started_at = utc_now(milliseconds=True)
    run_id = str(uuid.uuid4())
    write_json(output / "inventory-projection.json", inventory_projection)

    before = capture_snapshot(
        requirements,
        args.ssh_user,
        "before",
    )
    if not topology_stable(
        before["topology"],
        requirements["target"]["expected_leader"],
    ):
        raise LabError("initial topology is not the retained baseline")
    write_json(output / "before.json", before)

    leader_host = str(
        requirements["target"]["members"][
            requirements["target"]["expected_leader"]
        ]
    )
    remote_psql(
        args.ssh_user,
        leader_host,
        requirements["target"]["database"],
        (args.source_dir / "setup.sql").read_text(encoding="utf-8"),
        timeout=60,
    )
    fixture = remote_json_psql(
        args.ssh_user,
        leader_host,
        requirements["target"]["database"],
        FIXTURE_PROJECTION_SQL,
    )
    ensure_no_secret_material(fixture)
    write_json(output / "fixture.json", fixture)

    with tempfile.TemporaryDirectory(
        prefix="pg36-ch23-public-ca-"
    ) as temporary:
        ca_path = Path(temporary) / "root.crt"
        copy_public_ca(
            requirements,
            args.ssh_user,
            ca_path,
        )
        tls = run_tls_tests(requirements, password, ca_path)
    ensure_no_secret_material(tls)
    write_json(output / "tls-tests.json", tls)

    rls = run_rls_tests(requirements, password, args.ssh_user)
    ensure_no_secret_material(rls)
    write_json(output / "rls-tests.json", rls)

    pool, restore = run_pool_context(
        requirements,
        password,
        args.ssh_user,
    )
    ensure_no_secret_material(pool)
    ensure_no_secret_material(restore)
    write_json(output / "pool-context.json", pool)
    write_json(output / "pool-restore.json", restore)
    if restore.get("restored") is not True:
        raise LabError("PgBouncer settings were not restored")

    rotation = run_rotation_tests(requirements, args.ssh_user)
    ensure_no_secret_material(rotation)
    write_json(output / "rotation-tests.json", rotation)

    after = capture_snapshot(
        requirements,
        args.ssh_user,
        "after",
    )
    if not topology_stable(
        after["topology"],
        requirements["target"]["expected_leader"],
    ):
        raise LabError("final topology drifted")
    write_json(output / "after.json", after)

    manifest = build_manifest(
        requirements,
        args.source_dir,
        output,
        run_id=run_id,
        started_at=started_at,
    )
    ensure_no_secret_material(manifest)
    write_json(output / "drill-manifest.json", manifest)


def main() -> int:
    args = parse_args()
    try:
        run_drill(args)
    except (LabError, OSError, psycopg.Error) as exc:
        print(f"security drill failed: {exc}", file=sys.stderr)
        return 1
    print(f"evidence={args.output}")
    print("status=security-drill-captured")
    print("production_ch23_gate=pending")
    print("credential_values_exported=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
