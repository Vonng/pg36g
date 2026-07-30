#!/usr/bin/env python3
"""Validate chapter 23 evidence and adversarial counterexamples."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

from common import (
    LabError,
    read_json,
    sha256,
    topology_stable,
    utc_now,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    return parser.parse_args()


def fail_if(
    failures: list[str],
    condition: bool,
    message: str,
) -> None:
    if condition:
        failures.append(message)


def index_by(
    rows: Any,
    key: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get(key), str):
            result[str(row[key])] = row
    return result


def scan_secret_material(bundle: dict[str, Any]) -> list[str]:
    serialized = json.dumps(
        bundle,
        ensure_ascii=False,
        sort_keys=True,
    )
    patterns = {
        "SCRAM verifier": r"SCRAM-SHA-256\$",
        "private key": r"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----",
        "clear password field": r'"password"\s*:',
        "raw PgBouncer userlist": r'"userlist_raw"\s*:',
        "credential value": r'"credential_value"\s*:',
    }
    return [
        label
        for label, pattern in patterns.items()
        if re.search(pattern, serialized, flags=re.IGNORECASE)
    ]


def hba_methods(snapshot: dict[str, Any]) -> list[str]:
    methods: list[str] = []
    for member in snapshot.get("members", {}).values():
        for row in member.get("postgres", {}).get("hba_rules", []):
            method = row.get("auth_method")
            if isinstance(method, str):
                methods.append(method)
    return methods


def business_non_tls_hba(snapshot: dict[str, Any]) -> bool:
    for member in snapshot.get("members", {}).values():
        for row in member.get("postgres", {}).get("hba_rules", []):
            users = row.get("user_name") or []
            if (
                row.get("type") == "host"
                and "+dbrole_readonly" in users
                and row.get("auth_method") == "scram-sha-256"
            ):
                return True
    return False


def pgaudit_absent(snapshot: dict[str, Any]) -> bool:
    for member in snapshot.get("members", {}).values():
        postgres = member.get("postgres", {})
        libraries = str(
            postgres.get("settings", {}).get(
                "shared_preload_libraries",
                "",
            )
        )
        extension = index_by(postgres.get("extensions"), "name").get(
            "pgaudit"
        )
        if "pgaudit" in {
            value.strip() for value in libraries.split(",")
        }:
            return False
        if extension and extension.get("installed_version") is not None:
            return False
    return True


def validate_snapshot(
    failures: list[str],
    requirements: dict[str, Any],
    snapshot: dict[str, Any],
    phase: str,
) -> None:
    target = requirements["target"]
    fail_if(
        failures,
        snapshot.get("schema")
        != "pg36-ch23-security-snapshot-v1",
        f"{phase}: snapshot schema drifted",
    )
    fail_if(
        failures,
        snapshot.get("target") != target["id"],
        f"{phase}: target drifted",
    )
    fail_if(
        failures,
        snapshot.get("phase") != phase,
        f"{phase}: phase drifted",
    )
    fail_if(
        failures,
        not topology_stable(
            snapshot.get("topology", {}),
            target["expected_leader"],
        ),
        f"{phase}: topology is not the retained baseline",
    )
    members = snapshot.get("members", {})
    fail_if(
        failures,
        set(members) != set(target["members"]),
        f"{phase}: member set drifted",
    )
    for name, value in members.items():
        postgres = value.get("postgres", {})
        identity = postgres.get("identity", {})
        settings = postgres.get("settings", {})
        host = value.get("host", {})
        runtime = host.get("pgbouncer", {}).get(
            "runtime_settings",
            {},
        )
        fail_if(
            failures,
            not str(identity.get("server_version", "")).startswith(
                target["postgresql_observed"]
            ),
            f"{phase}/{name}: PostgreSQL version drifted",
        )
        fail_if(
            failures,
            settings.get("ssl") != "on",
            f"{phase}/{name}: PostgreSQL TLS is off",
        )
        fail_if(
            failures,
            settings.get("password_encryption") != "scram-sha-256",
            f"{phase}/{name}: password encryption is not SCRAM",
        )
        fail_if(
            failures,
            settings.get("ssl_min_protocol_version") != "TLSv1.2",
            f"{phase}/{name}: minimum TLS protocol drifted",
        )
        fail_if(
            failures,
            postgres.get("hba_parse_errors") != 0,
            f"{phase}/{name}: HBA parse errors exist",
        )
        fail_if(
            failures,
            runtime.get("pool_mode") != "transaction",
            f"{phase}/{name}: pool mode drifted",
        )
        fail_if(
            failures,
            runtime.get("client_tls_sslmode") != "disable",
            f"{phase}/{name}: expected TLS-gap observation drifted",
        )
        fail_if(
            failures,
            runtime.get("server_reset_query_always") != 0,
            f"{phase}/{name}: reset semantics drifted",
        )
        private_key = host.get("files", {}).get(
            "server_private_key",
            {},
        )
        fail_if(
            failures,
            private_key.get("mode") != "0600",
            f"{phase}/{name}: server private-key mode is not 0600",
        )
        certificate = host.get("certificate", {})
        fail_if(
            failures,
            not certificate.get("sha256_fingerprint"),
            f"{phase}/{name}: certificate fingerprint absent",
        )
        subject_alt_name = {
            (row.get("type"), row.get("value"))
            for row in certificate.get("subject_alt_name", [])
            if isinstance(row, dict)
        }
        fail_if(
            failures,
            ("DNS", name) not in subject_alt_name
            or ("IP Address", value.get("address"))
            not in subject_alt_name,
            f"{phase}/{name}: certificate SAN does not cover node identity",
        )
        user_names = host.get("pgbouncer", {}).get(
            "declared_user_names",
            [],
        )
        fail_if(
            failures,
            "test" not in user_names,
            f"{phase}/{name}: declared pool login is absent",
        )
        fail_if(
            failures,
            "pg36_ch23_rotate" in user_names,
            f"{phase}/{name}: direct-only rotation role entered pool",
        )
    methods = set(hba_methods(snapshot))
    forbidden = set(
        requirements["postgresql_policy"]["forbid_host_auth_methods"]
    )
    fail_if(
        failures,
        bool(methods & forbidden),
        f"{phase}: forbidden HBA method found: {sorted(methods & forbidden)}",
    )
    fail_if(
        failures,
        not business_non_tls_hba(snapshot),
        f"{phase}: expected direct non-TLS HBA gap was hidden",
    )
    fail_if(
        failures,
        not pgaudit_absent(snapshot),
        f"{phase}: expected pgAudit-gap observation drifted",
    )


def validate_fixture(
    failures: list[str],
    requirements: dict[str, Any],
    fixture: dict[str, Any],
) -> None:
    fail_if(
        failures,
        fixture.get("schema")
        != "pg36-ch23-fixture-projection-v1",
        "fixture schema drifted",
    )
    roles = index_by(fixture.get("roles"), "name")
    expected_roles = set(requirements["fixture"]["roles"].values())
    fail_if(
        failures,
        set(roles) != expected_roles,
        "synthetic role set drifted",
    )
    for name, role in roles.items():
        unsafe = any(
            role.get(key) is True
            for key in (
                "login",
                "superuser",
                "create_db",
                "create_role",
                "replication",
                "bypass_rls",
            )
        )
        fail_if(
            failures,
            unsafe,
            f"unsafe synthetic role attributes: {name}",
        )
        fail_if(
            failures,
            not str(role.get("comment", "")).startswith(
                requirements["fixture"]["role_comment_prefix"]
            ),
            f"synthetic role comment drifted: {name}",
        )
    rotation = roles.get(requirements["fixture"]["roles"]["rotation"], {})
    fail_if(
        failures,
        rotation.get("password_present") is not False,
        "rotation role retained a password in fixture projection",
    )

    actual_memberships = {
        (
            row.get("role"),
            row.get("member"),
            row.get("admin"),
            row.get("inherit"),
            row.get("set"),
        )
        for row in fixture.get("memberships", [])
    }
    expected_memberships = {
        (
            "pg36_ch23_runtime",
            "test",
            False,
            False,
            True,
        ),
        (
            "pg36_ch23_readonly",
            "test",
            False,
            False,
            True,
        ),
        (
            "pg36_ch23_owner",
            "pg36_ch23_migrate",
            False,
            False,
            True,
        ),
        (
            "dbrole_readonly",
            "pg36_ch23_rotate",
            False,
            False,
            False,
        ),
    }
    fail_if(
        failures,
        actual_memberships != expected_memberships,
        "role membership graph or options drifted",
    )
    schema = fixture.get("schema_object", {})
    fail_if(
        failures,
        schema.get("owner") != "pg36_ch23_owner"
        or schema.get("public_create") is not False
        or schema.get("runtime_usage") is not True
        or schema.get("runtime_create") is not False
        or schema.get("readonly_usage") is not True,
        "schema ownership or ACL drifted",
    )
    table = fixture.get("table_object", {})
    fail_if(
        failures,
        table.get("owner") != "pg36_ch23_owner"
        or table.get("row_security") is not True
        or table.get("force_row_security") is not True,
        "table owner or RLS flags drifted",
    )
    expected_runtime = {
        "select": True,
        "insert": True,
        "update": True,
        "delete": False,
        "truncate": False,
    }
    fail_if(
        failures,
        table.get("runtime") != expected_runtime,
        "runtime table ACL drifted",
    )
    fail_if(
        failures,
        table.get("readonly")
        != {"select": True, "insert": False, "update": False},
        "read-only table ACL drifted",
    )
    fail_if(
        failures,
        table.get("raw_login_select") is not False,
        "sandbox login inherited direct fixture SELECT",
    )
    policies = index_by(fixture.get("policies"), "name")
    fail_if(
        failures,
        set(policies)
        != {
            "account_runtime_select",
            "account_readonly_select",
            "account_runtime_insert",
            "account_runtime_update",
            "account_owner_all",
        },
        "RLS policy set drifted",
    )
    fail_if(
        failures,
        fixture.get("row_count") != 4
        or fixture.get("tenant_counts")
        != {
            requirements["fixture"]["tenant_a"]: 2,
            requirements["fixture"]["tenant_b"]: 2,
        },
        "synthetic tenant row counts drifted",
    )
    fail_if(
        failures,
        fixture.get("secret_values_exported") is not False,
        "fixture evidence exported secret values",
    )


def validate_tls(
    failures: list[str],
    tls: dict[str, Any],
) -> None:
    cases = index_by(tls.get("cases"), "case")

    def connected(name: str) -> bool:
        return cases.get(name, {}).get("connected") is True

    fail_if(
        failures,
        not connected("direct-require")
        or cases["direct-require"].get("observation", {}).get("ssl")
        is not True,
        "direct sslmode=require did not use TLS",
    )
    fail_if(
        failures,
        not connected("direct-verify-full")
        or cases["direct-verify-full"].get("observation", {}).get("ssl")
        is not True,
        "direct verify-full did not succeed",
    )
    fail_if(
        failures,
        cases.get("direct-wrong-name", {}).get("connected") is not False
        or cases.get("direct-wrong-name", {}).get("category")
        != "certificate-name-mismatch",
        "wrong certificate name was not rejected",
    )
    fail_if(
        failures,
        not connected("direct-disable")
        or cases["direct-disable"].get("observation", {}).get("ssl")
        is not False,
        "direct non-TLS gap was not reproduced",
    )
    fail_if(
        failures,
        not connected("direct-verify-full-channel-binding")
        or cases["direct-verify-full-channel-binding"].get(
            "observation",
            {},
        ).get("ssl")
        is not True,
        "direct channel-binding connection failed",
    )
    fail_if(
        failures,
        not connected("pooled-disable")
        or cases["pooled-disable"].get("observation", {}).get("ssl")
        is not False,
        "pooled cleartext client connection was not observed",
    )
    fail_if(
        failures,
        cases.get("pooled-require", {}).get("connected") is not False
        or cases.get("pooled-require", {}).get("category")
        != "server-no-client-tls",
        "PgBouncer client TLS gap was not reproduced",
    )
    interpretation = tls.get("interpretation", {})
    fail_if(
        failures,
        interpretation.get("sslmode_require_authenticates_server")
        is not False,
        "sslmode=require was misrepresented as server authentication",
    )
    fail_if(
        failures,
        interpretation.get("production_transport_gate") != "pending",
        "transport production gate was not left pending",
    )


def validate_rls(
    failures: list[str],
    requirements: dict[str, Any],
    rls: dict[str, Any],
) -> None:
    cases = index_by(rls.get("cases"), "case")
    tenant_a = requirements["fixture"]["tenant_a"]
    tenant_b = requirements["fixture"]["tenant_b"]
    for name, tenant in (
        ("runtime-select-tenant-a", tenant_a),
        ("runtime-select-tenant-b", tenant_b),
    ):
        case = cases.get(name, {})
        rows = case.get("result", {}).get("rows", [])
        fail_if(
            failures,
            case.get("accepted") is not True
            or len(rows) != 2
            or {row.get("tenant_id") for row in rows} != {tenant},
            f"{name}: tenant visibility drifted",
        )
    missing = cases.get("runtime-missing-context", {})
    fail_if(
        failures,
        missing.get("accepted") is not True
        or missing.get("result") != {"rows": 0, "tenant": None},
        "missing tenant context did not fail closed",
    )
    expected_states = {
        "runtime-invalid-context": "22P02",
        "runtime-cross-tenant-insert": "42501",
        "runtime-cross-tenant-update": "42501",
        "runtime-disable-rls": "42501",
        "runtime-create-in-schema": "42501",
        "runtime-truncate": "42501",
        "readonly-insert": "42501",
        "row-security-off-is-not-bypass": "42501",
        "raw-login-without-effective-role": "42501",
    }
    for name, state in expected_states.items():
        case = cases.get(name, {})
        fail_if(
            failures,
            case.get("accepted") is not False
            or case.get("sqlstate") != state,
            f"{name}: expected SQLSTATE {state} was not observed",
        )
    owner = rls.get("owner_and_break_glass", {})
    fail_if(
        failures,
        owner.get("owner_without_context_rows") != 0,
        "forced owner RLS did not fail closed",
    )
    owner_a = owner.get("owner_tenant_a", {})
    fail_if(
        failures,
        owner_a.get("rows") != 2
        or owner_a.get("minimum_tenant") != tenant_a
        or owner_a.get("maximum_tenant") != tenant_a,
        "forced owner RLS tenant filter drifted",
    )
    fail_if(
        failures,
        owner.get("migration_role_chain")
        != {
            "session_user": "pg36_ch23_migrate",
            "current_user": "pg36_ch23_owner",
        },
        "migration SET ROLE chain drifted",
    )
    fail_if(
        failures,
        owner.get("superuser_break_glass_rows") != 4,
        "superuser bypass observation drifted",
    )
    fail_if(
        failures,
        rls.get("end_user_input_trusted_directly") is not False,
        "end-user tenant input was trusted directly",
    )


def validate_pool(
    failures: list[str],
    requirements: dict[str, Any],
    pool: dict[str, Any],
    restore: dict[str, Any],
) -> None:
    before = pool.get("before")
    override = pool.get("override", {})
    fail_if(
        failures,
        pool.get("applied") != override,
        "single-backend pool override was not applied exactly",
    )
    leak = pool.get("session_set_counterexample", {})
    leak_b = leak.get("client_b_without_context", {})
    fail_if(
        failures,
        leak.get("same_backend") is not True
        or leak.get("tenant_a_leaked_to_client_b") is not True
        or leak_b.get("effective_tenant")
        != requirements["fixture"]["tenant_a"]
        or leak_b.get("rows") != 2
        or leak.get("supported_pattern") is not False,
        "session-level SET leak counterexample drifted",
    )
    secure = pool.get("transaction_local_contract", {})
    tenant_a = secure.get("tenant_a", {})
    tenant_b = secure.get("tenant_b", {})
    missing_a = secure.get("missing_after_a", {})
    missing_b = secure.get("missing_after_b", {})
    fail_if(
        failures,
        tenant_a.get("effective_tenant")
        != requirements["fixture"]["tenant_a"]
        or tenant_a.get("rows") != 2
        or tenant_b.get("effective_tenant")
        != requirements["fixture"]["tenant_b"]
        or tenant_b.get("rows") != 2
        or missing_a.get("effective_tenant") is not None
        or missing_a.get("rows") != 0
        or missing_b.get("effective_tenant") is not None
        or missing_b.get("rows") != 0
        or secure.get("supported_pattern") is not True,
        "transaction-local pool contract drifted",
    )
    fail_if(
        failures,
        restore.get("restored") is not True
        or restore.get("before") != before
        or restore.get("after") != before
        or len(restore.get("pool_reconnected_on", [])) != 3,
        "PgBouncer settings or sessions were not restored",
    )


def validate_rotation(
    failures: list[str],
    rotation: dict[str, Any],
) -> None:
    case_events = index_by(
        [
            row
            for row in rotation.get("events", [])
            if isinstance(row, dict) and "case" in row
        ],
        "case",
    )
    fail_if(
        failures,
        case_events.get("new-connection-secret-one", {}).get(
            "connected"
        )
        is not True,
        "first rotated credential did not authenticate",
    )
    fail_if(
        failures,
        case_events.get("pool-user-not-declared", {}).get("connected")
        is not False,
        "direct-only role unexpectedly authenticated through pool",
    )
    fail_if(
        failures,
        case_events.get("old-secret-new-connection", {}).get(
            "connected"
        )
        is not False,
        "old credential still authenticated a new connection",
    )
    fail_if(
        failures,
        case_events.get("new-secret-new-connection", {}).get(
            "connected"
        )
        is not True,
        "new credential did not authenticate",
    )
    for name in (
        "existing-session-before-rotation",
        "existing-session-after-password-change",
        "existing-session-after-nologin",
    ):
        fail_if(
            failures,
            case_events.get(name, {}).get("still_usable") is not True,
            f"{name}: existing-session observation drifted",
        )
    fail_if(
        failures,
        case_events.get("new-connection-after-nologin", {}).get(
            "connected"
        )
        is not False,
        "NOLOGIN did not reject a new connection",
    )
    fail_if(
        failures,
        case_events.get("new-connection-after-password-null", {}).get(
            "connected"
        )
        is not False,
        "PASSWORD NULL final state admitted a new connection",
    )
    final = rotation.get("final_state", {})
    fail_if(
        failures,
        final.get("can_login") is not False
        or final.get("password_present") is not False
        or final.get("secret_exported") is not False,
        "rotation role final state is not revoked",
    )
    generation = rotation.get("credential_generation", {})
    fail_if(
        failures,
        generation.get("values_exported") is not False
        or generation.get("shell_arguments_used") is not False,
        "rotation credential handling drifted",
    )
    interpretation = rotation.get("interpretation", {})
    fail_if(
        failures,
        interpretation.get(
            "password_change_terminates_existing_sessions"
        )
        is not False
        or interpretation.get(
            "nologin_terminates_existing_sessions"
        )
        is not False,
        "credential rotation overstated session termination",
    )


def validate_manifest(
    failures: list[str],
    requirements: dict[str, Any],
    evidence_dir: Path,
    manifest: dict[str, Any],
) -> None:
    fail_if(
        failures,
        manifest.get("schema") != "pg36-ch23-drill-manifest-v1",
        "manifest schema drifted",
    )
    fail_if(
        failures,
        manifest.get("target") != requirements["target"]["id"],
        "manifest target drifted",
    )
    fail_if(
        failures,
        manifest.get("authority")
        != "nonproduction-synthetic-data-only",
        "manifest authority drifted",
    )
    fail_if(
        failures,
        manifest.get("production_gate") != "pending",
        "production gate was incorrectly passed",
    )
    fail_if(
        failures,
        manifest.get("ordinary_postgresql_logging_is_complete_audit")
        is not False,
        "ordinary PostgreSQL logs were called a complete audit trail",
    )
    expected_guard = {
        "exact_target_required": True,
        "nonproduction_required": True,
        "synthetic_data_required": True,
        "separate_destructive_confirmation_required": True,
    }
    fail_if(
        failures,
        manifest.get("reset_guard_contract") != expected_guard,
        "destructive reset guard contract drifted",
    )
    fail_if(
        failures,
        manifest.get("credential_values_exported") is not False
        or manifest.get("private_key_read") is not False,
        "manifest claims secret or private-key access",
    )
    restored = manifest.get("mutations_restored", {})
    fail_if(
        failures,
        restored.get("pool_settings") is not True
        or restored.get("rotation_login") is not False
        or restored.get("rotation_password") is not None,
        "manifest final-state contract drifted",
    )
    hashes = manifest.get("evidence_sha256", {})
    expected_names = {
        name
        for name in requirements["required_evidence"]
        if name != "drill-manifest.json"
    }
    fail_if(
        failures,
        set(hashes) != expected_names,
        "manifest evidence hash set drifted",
    )
    for name, expected in hashes.items():
        path = evidence_dir / name
        fail_if(
            failures,
            not path.is_file() or sha256(path) != expected,
            f"evidence hash mismatch: {name}",
        )


def validate_bundle(
    requirements: dict[str, Any],
    bundle: dict[str, Any],
    evidence_dir: Path,
    *,
    verify_hashes: bool,
) -> list[str]:
    failures: list[str] = []
    secret_hits = scan_secret_material(bundle)
    fail_if(
        failures,
        bool(secret_hits),
        f"secret material detected: {secret_hits}",
    )
    validate_snapshot(
        failures,
        requirements,
        bundle.get("before", {}),
        "before",
    )
    validate_snapshot(
        failures,
        requirements,
        bundle.get("after", {}),
        "after",
    )
    validate_fixture(
        failures,
        requirements,
        bundle.get("fixture", {}),
    )
    validate_tls(failures, bundle.get("tls-tests", {}))
    validate_rls(
        failures,
        requirements,
        bundle.get("rls-tests", {}),
    )
    validate_pool(
        failures,
        requirements,
        bundle.get("pool-context", {}),
        bundle.get("pool-restore", {}),
    )
    validate_rotation(
        failures,
        bundle.get("rotation-tests", {}),
    )
    if verify_hashes:
        validate_manifest(
            failures,
            requirements,
            evidence_dir,
            bundle.get("drill-manifest", {}),
        )
    else:
        manifest = bundle.get("drill-manifest", {})
        fail_if(
            failures,
            manifest.get("production_gate") != "pending",
            "production gate was incorrectly passed",
        )
        fail_if(
            failures,
            manifest.get("reset_guard_contract")
            != {
                "exact_target_required": True,
                "nonproduction_required": True,
                "synthetic_data_required": True,
                "separate_destructive_confirmation_required": True,
            },
            "destructive reset guard contract drifted",
        )
        fail_if(
            failures,
            manifest.get(
                "ordinary_postgresql_logging_is_complete_audit"
            )
            is not False,
            "ordinary PostgreSQL logs were called a complete audit trail",
        )
    return failures


def load_bundle(
    requirements: dict[str, Any],
    evidence_dir: Path,
) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for name in requirements["required_evidence"]:
        path = evidence_dir / name
        if not path.is_file():
            raise LabError(f"required evidence is missing: {name}")
        bundle[name.removesuffix(".json")] = read_json(path)
    return bundle


def apply_negative_mutation(
    case_id: str,
    bundle: dict[str, Any],
) -> None:
    if case_id == "N01":
        bundle["before"]["target"] = "production/unknown"
    elif case_id == "N02":
        bundle["after"]["topology"]["members"][0]["state"] = "stopped"
    elif case_id == "N03":
        bundle["drill-manifest"]["production_gate"] = "passed"
    elif case_id == "N04":
        bundle["fixture"]["roles"][0]["superuser"] = True
    elif case_id == "N05":
        bundle["fixture"]["roles"][0]["login"] = True
    elif case_id == "N06":
        bundle["fixture"]["memberships"][0]["admin"] = True
    elif case_id == "N07":
        bundle["fixture"]["table_object"]["force_row_security"] = False
    elif case_id == "N08":
        cases = index_by(bundle["rls-tests"]["cases"], "case")
        cases["runtime-missing-context"]["result"]["rows"] = 4
    elif case_id == "N09":
        cases = index_by(bundle["rls-tests"]["cases"], "case")
        cases["runtime-cross-tenant-insert"]["accepted"] = True
    elif case_id == "N10":
        bundle["pool-context"]["session_set_counterexample"][
            "tenant_a_leaked_to_client_b"
        ] = False
    elif case_id == "N11":
        bundle["pool-context"]["session_set_counterexample"][
            "supported_pattern"
        ] = True
    elif case_id == "N12":
        bundle["pool-restore"]["restored"] = False
    elif case_id == "N13":
        bundle["rotation-tests"]["interpretation"][
            "password_change_terminates_existing_sessions"
        ] = True
    elif case_id == "N14":
        bundle["rotation-tests"]["final_state"]["can_login"] = True
    elif case_id == "N15":
        bundle["inventory-projection"]["credential_value"] = (
            "SCRAM-SHA-256$synthetic-forbidden"
        )
    elif case_id == "N16":
        bundle["tls-tests"]["interpretation"][
            "sslmode_require_authenticates_server"
        ] = True
    elif case_id == "N17":
        cases = index_by(bundle["tls-tests"]["cases"], "case")
        cases["direct-disable"]["connected"] = False
    elif case_id == "N18":
        cases = index_by(bundle["tls-tests"]["cases"], "case")
        cases["pooled-require"]["connected"] = True
    elif case_id == "N19":
        bundle["drill-manifest"][
            "ordinary_postgresql_logging_is_complete_audit"
        ] = True
    elif case_id == "N20":
        bundle["drill-manifest"]["reset_guard_contract"][
            "separate_destructive_confirmation_required"
        ] = False
    else:
        raise LabError(f"negative mutation is not implemented: {case_id}")


def run_negative_validation(
    requirements: dict[str, Any],
    bundle: dict[str, Any],
    evidence_dir: Path,
    specification: dict[str, Any],
) -> dict[str, Any]:
    results = []
    for row in specification.get("cases", []):
        case_id = str(row.get("id"))
        mutated = copy.deepcopy(bundle)
        apply_negative_mutation(case_id, mutated)
        failures = validate_bundle(
            requirements,
            mutated,
            evidence_dir,
            verify_hashes=False,
        )
        results.append(
            {
                "id": case_id,
                "expected": "reject",
                "rejected": bool(failures),
                "failure_count": len(failures),
            }
        )
    passed = all(row["rejected"] for row in results)
    return {
        "schema": "pg36-ch23-negative-report-v1",
        "validated_at": utc_now(milliseconds=True),
        "passed": passed,
        "case_count": len(results),
        "results": results,
    }


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        bundle = load_bundle(requirements, args.evidence)
        if args.negative_cases is not None:
            specification = read_json(args.negative_cases)
            report = run_negative_validation(
                requirements,
                bundle,
                args.evidence,
                specification,
            )
            if not report["passed"]:
                raise LabError("one or more counterexamples were accepted")
        else:
            failures = validate_bundle(
                requirements,
                bundle,
                args.evidence,
                verify_hashes=True,
            )
            report = {
                "schema": "pg36-ch23-validation-report-v1",
                "validated_at": utc_now(milliseconds=True),
                "passed": not failures,
                "failure_count": len(failures),
                "failures": failures,
                "production_gate": "pending",
            }
            if failures:
                raise LabError("; ".join(failures))
        write_json(args.output, report)
    except LabError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"validated={args.evidence}")
    print(f"report={args.output}")
    print("status=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
