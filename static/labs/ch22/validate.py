#!/usr/bin/env python3
"""Validate chapter 22 service evidence and adversarial counterexamples."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any


EXPECTED_NEGATIVE_CODES = {
    "claim-production-from-sandbox": "E_PRODUCTION_CLAIM",
    "route-primary-to-replica": "E_ENDPOINT",
    "route-replica-to-primary": "E_ENDPOINT",
    "route-offline-to-wrong-member": "E_ENDPOINT",
    "treat-session-state-as-sticky": "E_POOL_SEMANTICS",
    "accept-broken-protocol-prepare": "E_PREPARED",
    "accept-sql-prepare-across-backends": "E_PREPARED",
    "exceed-server-pool-cap": "E_BACKPRESSURE",
    "claim-no-queue-with-saturation": "E_BACKPRESSURE",
    "leave-pgbouncer-overridden": "E_CONFIG_RESTORE",
    "lose-acknowledged-write": "E_COMMIT_EVIDENCE",
    "leave-unknown-outcome-unreconciled": "E_COMMIT_EVIDENCE",
    "accept-excessive-write-gap": "E_RECOVERY_TIME",
    "leave-wrong-final-leader": "E_TOPOLOGY",
    "degrade-source-after-drill": "E_TOPOLOGY",
}


class PolicyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code: str, message: str) -> None:
    raise PolicyError(code, message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("E_EVIDENCE", f"cannot read {path}: {exc}")
    if not isinstance(value, dict):
        fail("E_EVIDENCE", f"{path} must contain an object")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_evidence(path: Path) -> dict[str, Any]:
    return {
        "manifest": read_json(path / "drill-manifest.json"),
        "before": read_json(path / "before.json"),
        "after": read_json(path / "after.json"),
        "fixture": read_json(path / "fixture.json"),
        "endpoints": read_json(path / "endpoint-observations.json"),
        "pool_settings": read_json(path / "pool-settings.json"),
        "saturation": read_json(path / "pool-saturation.json"),
        "session": read_json(path / "session-semantics.json"),
        "prepared": read_json(path / "prepared-statements.json"),
        "replica": read_json(path / "replica-visibility.json"),
        "forward_action": read_json(path / "switch-forward.json"),
        "restore_action": read_json(path / "switch-restore.json"),
        "pool_refreshes": read_json(
            path / "pool-refresh-actions.json"
        ),
        "pre_switch": read_json(path / "phases" / "pre-switch.json"),
        "after_forward": read_json(
            path / "phases" / "after-forward.json"
        ),
        "restored": read_json(path / "phases" / "restored.json"),
        "reconciliation": read_json(path / "reconciliation.json"),
    }


def validate_documents(requirements: dict[str, Any]) -> None:
    if (
        requirements.get("schema")
        != "pg36-ch22-service-requirements-v1"
        or requirements.get("release") != "1.0-sandbox"
        or "not-production-slo"
        not in str(requirements.get("status", ""))
    ):
        fail("E_SCHEMA", "requirements identity drifted")
    target = requirements.get("target", {})
    if (
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("pigsty_release") != "v4.4.0"
        or target.get("postgresql_observed") != "18.4"
        or target.get("pgbouncer_observed") != "1.25.2"
        or target.get("haproxy_observed") != "3.4.2"
        or target.get("cluster") != "pg-test"
        or target.get("entry_address") != "10.10.10.11"
    ):
        fail("E_SCHEMA", "target identity drifted")
    if (
        target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or requirements.get("decision_boundary", {}).get(
            "production_ch22_gate"
        )
        != "pending"
    ):
        fail("E_PRODUCTION_CLAIM", "sandbox crossed production boundary")
    expected_exceptions = [
        "EX19-SHARED-HYPERVISOR",
        "EX19-SINGLE-ETCD",
        "EX19-SINGLE-BACKUP-TARGET",
        "EX19-VIRTUAL-STORAGE",
        "EX19-INVENTORY-SECRETS",
        "EX19-LAB-RESOURCE-FLOOR",
        "EX20-ASYNC-BASELINE",
        "EX20-WATCHDOG-OFF",
        "EX20-CLIENT-PROXY-NO-TLS",
        "EX20-PLANNED-ONLY",
        "EX22-SINGLE-HAPROXY-ENTRY",
        "EX22-ASYNC-READ-OBSERVATION",
        "EX22-SYNTHETIC-LOAD",
        "EX22-RUNTIME-POOL-OVERRIDE",
    ]
    if requirements.get("required_exception_ids") != expected_exceptions:
        fail("E_EXCEPTION", "required exception set drifted")
    if [
        row.get("id") for row in requirements.get("exceptions", [])
    ] != expected_exceptions[-4:]:
        fail("E_EXCEPTION", "chapter-22 exception details drifted")


def member_index(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = topology.get("members")
    if not isinstance(rows, list):
        fail("E_TOPOLOGY", "Patroni member list is missing")
    result = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(result) != len(rows):
        fail("E_TOPOLOGY", "member identities are missing or duplicated")
    return result


def validate_topology(
    topology: dict[str, Any],
    expected_leader: str,
    expected_timeline: int | None = None,
) -> int:
    members = member_index(topology)
    expected_hosts = {
        "pg-test-1": "10.10.10.11",
        "pg-test-2": "10.10.10.12",
        "pg-test-3": "10.10.10.13",
    }
    if set(members) != set(expected_hosts):
        fail("E_TOPOLOGY", "Patroni member set drifted")
    timelines: set[int] = set()
    for name, row in members.items():
        expected_role = "primary" if name == expected_leader else "replica"
        expected_state = "running" if name == expected_leader else "streaming"
        if (
            row.get("host") != expected_hosts[name]
            or row.get("role") != expected_role
            or row.get("state") != expected_state
        ):
            fail("E_TOPOLOGY", f"topology drifted for {name}")
        if not isinstance(row.get("timeline"), int):
            fail("E_TOPOLOGY", "timeline is missing")
        timelines.add(int(row["timeline"]))
        if name != expected_leader:
            lag = row.get("replay_lag_bytes")
            if isinstance(lag, int) and lag != 0:
                fail("E_TOPOLOGY", f"replica lag is nonzero for {name}")
    if len(timelines) != 1:
        fail("E_TOPOLOGY", "members disagree on timeline")
    timeline = next(iter(timelines))
    if expected_timeline is not None and timeline != expected_timeline:
        fail("E_TOPOLOGY", "timeline progression drifted")
    return timeline


def expected_pool(requirements: dict[str, Any]) -> dict[str, int]:
    pool = requirements["pgbouncer"]
    return {
        "default_pool_size": pool["default_pool_size"],
        "reserve_pool_size": pool["reserve_pool_size"],
        "reserve_pool_timeout": pool["reserve_pool_timeout_seconds"],
        "query_wait_timeout": pool["query_wait_timeout_seconds"],
    }


def validate_snapshot(
    snapshot: dict[str, Any],
    requirements: dict[str, Any],
    phase: str,
) -> int:
    if (
        snapshot.get("schema") != "pg36-ch22-service-snapshot-v1"
        or snapshot.get("release") != requirements["release"]
        or snapshot.get("phase") != phase
        or snapshot.get("target") != requirements["target"]["id"]
    ):
        fail("E_SCHEMA", f"snapshot identity drifted for {phase}")
    timeline = validate_topology(snapshot["topology"], "pg-test-1")
    entry = snapshot.get("entry", {})
    versions = entry.get("package_versions", {})
    if (
        not str(versions.get("haproxy", "")).startswith("3.4.2")
        or not str(versions.get("pgbouncer", "")).startswith("1.25.2")
        or not str(versions.get("postgresql-18", "")).startswith("18.4")
        or not {5432, 5433, 5434, 5436, 5438, 6432, 8008}.issubset(
            set(entry.get("tcp_listener_ports", []))
        )
    ):
        fail("E_ENDPOINT", "entry versions or listeners drifted")
    services = entry.get("services", {})
    for name, contract in requirements["services"].items():
        service = services.get(name, {})
        destination = 6432 if name in {"primary", "replica"} else 5432
        if (
            service.get("port") != contract["port"]
            or service.get("health_path") != contract["health_path"]
            or service.get("expected_status") != 200
            or service.get("mode") != "tcp"
            or {
                row.get("destination_port")
                for row in service.get("servers", [])
            }
            != {destination}
            or {
                row.get("check_port")
                for row in service.get("servers", [])
            }
            != {8008}
        ):
            fail("E_ENDPOINT", f"service definition drifted for {name}")
        defaults = service.get("default_server", {})
        if (
            defaults.get("inter") != "2s"
            or defaults.get("fastinter") != "1s"
            or defaults.get("downinter") != "2s"
            or defaults.get("rise") != 3
            or defaults.get("fall") != 3
            or defaults.get("on_marked_down") != "shutdown-sessions"
            or defaults.get("slowstart") != "30s"
            or defaults.get("maxconn") != 3000
            or defaults.get("maxqueue") != 128
        ):
            fail("E_ENDPOINT", f"HAProxy guardrails drifted for {name}")
    offline = services["offline"]["servers"]
    replica = services["replica"]["servers"]
    if (
        offline
        != [
            {
                "member": "pg-test-3",
                "address": "10.10.10.13",
                "destination_port": 5432,
                "check_port": 8008,
                "backup": False,
            },
            {
                "member": "pg-test-2",
                "address": "10.10.10.12",
                "destination_port": 5432,
                "check_port": 8008,
                "backup": True,
            },
        ]
        or not any(
            row.get("member") == "pg-test-1"
            and row.get("backup") is True
            for row in replica
        )
    ):
        fail("E_ENDPOINT", "replica/offline preference drifted")

    baseline = expected_pool(requirements)
    pgbouncer = snapshot.get("pgbouncer", {})
    if set(pgbouncer) != {
        "10.10.10.11", "10.10.10.12", "10.10.10.13"
    }:
        fail("E_CONFIG_RESTORE", "PgBouncer host set drifted")
    for host, actual in pgbouncer.items():
        if (
            actual.get("pool_mode") != "transaction"
            or actual.get("listen_port") != 6432
            or actual.get("max_client_conn") != 20000
            or actual.get("max_db_connections") != 100
            or actual.get("max_user_connections") != 100
            or actual.get("max_prepared_statements") != 256
            or actual.get("server_reset_query") != "DISCARD ALL"
            or actual.get("server_reset_query_always") != 0
            or actual.get("client_tls_sslmode") != "disable"
            or {
                key: actual.get(key) for key in baseline
            }
            != baseline
        ):
            fail("E_CONFIG_RESTORE", f"PgBouncer drifted on {host}")
    postgres = snapshot.get("postgres", {})
    if set(postgres) != set(pgbouncer):
        fail("E_TOPOLOGY", "PostgreSQL host set drifted")
    for name, host in requirements["target"]["members"].items():
        row = postgres[host]
        settings = row.get("settings", {})
        if (
            row.get("schema") != "pg36-ch22-postgresql-state-v1"
            or row.get("cluster_name") != "pg-test"
            or row.get("server_version_num") != 180004
            or row.get("in_recovery") is (name == "pg-test-1")
            or settings.get("max_connections") != 500
            or settings.get("superuser_reserved_connections") != 10
            or settings.get("reserved_connections") != 0
            or settings.get("idle_in_transaction_session_timeout")
            != 600000
            or settings.get("statement_timeout") != 0
            or settings.get("max_locks_per_transaction") != 500
        ):
            fail("E_TOPOLOGY", f"PostgreSQL state drifted on {host}")
    return timeline


def validate_manifest(
    manifest: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    try:
        parsed = uuid.UUID(str(manifest.get("run_id", "")))
    except ValueError:
        fail("E_MANIFEST", "run_id is not a UUID")
    if (
        manifest.get("schema") != "pg36-ch22-drill-manifest-v1"
        or manifest.get("release") != requirements["release"]
        or manifest.get("target") != requirements["target"]["id"]
        or manifest.get("mode")
        != "service-pooling-and-two-planned-switchovers"
        or manifest.get("status") != "completed"
        or manifest.get("production_approval") is not False
        or manifest.get("production_data") is not False
        or manifest.get("production_traffic") is not False
        or manifest.get("unplanned_failure_injected") is not False
        or manifest.get("destructive_cleanup") is not False
        or manifest.get("secret_values_exported") != 0
        or manifest.get("private_service_file_removed") is not True
        or manifest.get("declared_login_role_mutated") is not False
        or str(parsed) != manifest.get("run_id")
    ):
        if (
            manifest.get("production_approval") is not False
            or manifest.get("production_data") is not False
            or manifest.get("production_traffic") is not False
        ):
            fail(
                "E_PRODUCTION_CLAIM",
                "sandbox evidence carries a production claim",
            )
        fail("E_MANIFEST", "drill manifest identity drifted")


def validate_fixture(bundle: dict[str, Any]) -> None:
    fixture = bundle["fixture"]
    role = fixture.get("role", {})
    namespace = fixture.get("namespace", {})
    table = fixture.get("table", {})
    if (
        fixture.get("schema") != "pg36-ch22-fixture-v1"
        or fixture.get("database") != "test"
        or fixture.get("credential_exported") is not False
        or role.get("name") != "test"
        or role.get("comment") != "business user test"
        or role.get("can_login") is not True
        or role.get("superuser") is not False
        or role.get("create_db") is not False
        or role.get("create_role") is not False
        or role.get("replication") is not False
        or role.get("bypass_rls") is not False
        or role.get("inherit") is not True
        or role.get("connection_limit") != -1
        or fixture.get("declared_role_preserved") is not True
        or namespace
        != {
            "name": "pg36_ch22",
            "owner": "postgres",
            "comment":
                "pg36 chapter 22 service-routing lab; synthetic data only",
        }
        or table.get("name") != "pg36_ch22.route_probe"
        or table.get("owner") != "postgres"
    ):
        fail("E_FIXTURE", "fixture identity or privilege boundary drifted")


def validate_endpoints(bundle: dict[str, Any]) -> None:
    evidence = bundle["endpoints"]
    observations = evidence.get("observations", {})
    if (
        evidence.get("schema")
        != "pg36-ch22-endpoint-observations-v1"
        or evidence.get("entry_address") != "10.10.10.11"
        or set(observations)
        != {"primary", "replica", "default", "offline"}
    ):
        fail("E_ENDPOINT", "endpoint evidence identity drifted")
    expected = {
        "primary": (5433, False, False, "10.10.10.11"),
        "replica": (5434, True, True, None),
        "default": (5436, False, False, "10.10.10.11"),
        "offline": (5438, True, True, "10.10.10.13"),
    }
    for name, contract in expected.items():
        port, recovery, readonly, member = contract
        row = observations[name]
        if (
            row.get("service_port") != port
            or row.get("postgres_port") != 5432
            or row.get("cluster_name") != "pg-test"
            or row.get("in_recovery") is not recovery
            or row.get("transaction_read_only") is not readonly
            or (
                member is not None
                and row.get("selected_member_address") != member
            )
            or (
                name == "replica"
                and row.get("selected_member_address")
                not in {"10.10.10.12", "10.10.10.13"}
            )
        ):
            fail("E_ENDPOINT", f"endpoint semantics drifted for {name}")
    locations = evidence.get("dedicated_pool_locations", {})
    if (
        locations.get("pg-test-1", {}).get("present") is not True
        or locations.get("pg-test-1", {}).get("pool_mode")
        != "transaction"
        or not any(
            locations.get(name, {}).get("present") is True
            and locations.get(name, {}).get("pool_mode")
            == "transaction"
            for name in ("pg-test-2", "pg-test-3")
        )
    ):
        fail("E_ENDPOINT", "pooled endpoint path was not observed")


def validate_pool_semantics(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    settings = bundle["pool_settings"]
    baseline = expected_pool(requirements)
    override = requirements["pgbouncer"]["lab_override"]
    expected_override = {
        "default_pool_size": override["default_pool_size"],
        "reserve_pool_size": override["reserve_pool_size"],
        "reserve_pool_timeout": requirements["pgbouncer"][
            "reserve_pool_timeout_seconds"
        ],
        "query_wait_timeout": override["query_wait_timeout_seconds"],
    }
    if (
        settings.get("schema") != "pg36-ch22-pool-settings-v1"
        or settings.get("before") != baseline
        or settings.get("baseline_database_reconnect_members")
        != ["pg-test-1", "pg-test-2", "pg-test-3"]
        or settings.get("during") != expected_override
        or settings.get("restored") != baseline
        or settings.get("restored_before_switch") is not True
        or bundle["manifest"].get(
            "pool_settings_restored_before_switch"
        )
        is not True
    ):
        fail("E_CONFIG_RESTORE", "PgBouncer runtime policy was not restored")
    saturation = bundle["saturation"]
    contract = requirements["pool_experiment"]
    if (
        saturation.get("schema") != "pg36-ch22-saturation-v1"
        or saturation.get("clients") != contract["clients"]
        or saturation.get("completed_clients") != contract["clients"]
        or saturation.get("maximum_server_active")
        > contract["maximum_observed_server_active"]
    ):
        fail("E_BACKPRESSURE", "server pool cap was exceeded")
    if (
        saturation.get("maximum_client_waiting", 0)
        < contract["minimum_waiting_clients"]
    ):
        fail("E_BACKPRESSURE", "saturation produced no observable queue")
    if (
        len(saturation.get("unique_backend_pids", []))
        > contract["server_slots"]
        or any(
            row.get("transaction_read_only") is not False
            for row in saturation.get("results", [])
        )
    ):
        fail("E_BACKPRESSURE", "pool used unexpected backends or role")
    session = bundle["session"]
    if (
        session.get("schema") != "pg36-ch22-session-state-v1"
        or session.get("state_visible_to_other_client") is not True
        or session.get("state_not_sticky_for_original_client") is not True
        or session.get("client_a_first", {}).get("backend_pid")
        != session.get("client_b_borrowed", {}).get("backend_pid")
        or session.get("client_a_first", {}).get("backend_pid")
        == session.get("client_a_reassigned", {}).get("backend_pid")
    ):
        fail(
            "E_POOL_SEMANTICS",
            "transaction pooling was treated as sticky session state",
        )


def validate_prepared(bundle: dict[str, Any]) -> None:
    prepared = bundle["prepared"]
    protocol = prepared.get("protocol", {})
    if (
        prepared.get("schema")
        != "pg36-ch22-prepared-statements-v1"
        or prepared.get("pgbouncer_version") != "1.25.2"
        or prepared.get("max_prepared_statements") != 256
        or protocol.get("schema")
        != "pg36-ch22-protocol-prepare-v1"
        or protocol.get("prepare_threshold") != 1
        or protocol.get("iterations") != 12
        or protocol.get("correct_results") is not True
        or protocol.get("backend_reassignment_observed") is not True
        or len(protocol.get("unique_backend_pids", [])) < 2
    ):
        fail("E_PREPARED", "protocol prepared-statement proof failed")
    sql = prepared.get("sql", {})
    failure = sql.get("expected_failure") or {}
    if (
        sql.get("schema") != "pg36-ch22-sql-prepare-v1"
        or sql.get("backend_reassignment_forced") is not True
        or sql.get("unexpectedly_succeeded") is not False
        or failure.get("sqlstate") != "26000"
        or failure.get("class") != "InvalidSqlStatementName"
    ):
        fail(
            "E_PREPARED",
            "SQL PREPARE was accepted across backend reassignment",
        )


def validate_replica(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    replica = bundle["replica"]
    observation = replica.get("replica", {})
    if (
        replica.get("schema")
        != "pg36-ch22-replica-visibility-v1"
        or replica.get("run_id") != bundle["manifest"].get("run_id")
        or replica.get("token_recorded") is not True
        or replica.get("token_value_exported") is not False
        or not isinstance(
            replica.get("primary", {}).get("commit_lsn"), str
        )
        or observation.get("visible") is not True
        or observation.get("in_recovery") is not True
        or observation.get("transaction_read_only") is not True
        or observation.get("selected_member_address")
        not in {"10.10.10.12", "10.10.10.13"}
        or observation.get("visibility_delay_ms", float("inf"))
        > requirements["replica_read"]["visibility_timeout_seconds"]
        * 1000
        or replica.get("claim") != requirements["replica_read"]["claim"]
    ):
        fail("E_ENDPOINT", "replica visibility evidence drifted")


def validate_switch(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
    initial_timeline: int,
    final_timeline: int,
) -> None:
    validate_topology(
        bundle["pre_switch"],
        "pg-test-1",
        initial_timeline,
    )
    validate_topology(
        bundle["after_forward"],
        "pg-test-2",
        initial_timeline + 1,
    )
    validate_topology(
        bundle["restored"],
        "pg-test-1",
        initial_timeline + 2,
    )
    if final_timeline != initial_timeline + 2:
        fail("E_TOPOLOGY", "final snapshot lost timeline progression")
    for action, leader, candidate in (
        (bundle["forward_action"], "pg-test-1", "pg-test-2"),
        (bundle["restore_action"], "pg-test-2", "pg-test-1"),
    ):
        if (
            action.get("schema")
            != "pg36-ch22-switchover-action-v1"
            or action.get("kind") != "healthy-planned-switchover"
            or action.get("leader") != leader
            or action.get("candidate") != candidate
            or action.get("return_code") != 0
            or action.get("stderr_empty") is not True
            or action.get("duration_ms", -1) < 0
        ):
            fail("E_TOPOLOGY", "planned switchover action drifted")
    if bundle["manifest"].get("final_leader") != "pg-test-1":
        fail("E_TOPOLOGY", "baseline leader was not restored")
    refreshes = bundle["pool_refreshes"]
    phases = refreshes.get("phases", [])
    if (
        refreshes.get("schema")
        != "pg36-ch22-pool-refresh-actions-v1"
        or [row.get("phase") for row in phases]
        != ["after-forward", "after-restore"]
    ):
        fail("E_CONFIG_RESTORE", "role-aware pool refresh evidence drifted")
    for phase in phases:
        actions = phase.get("actions", [])
        if (
            [row.get("member") for row in actions]
            != ["pg-test-1", "pg-test-2", "pg-test-3"]
            or any(
                row.get("database") != "test"
                or row.get("status") != "issued"
                or row.get("duration_ms", -1) < 0
                for row in actions
            )
            or phase.get("first_acknowledgement_monotonic_ns", 0)
            < phase.get("finished_monotonic_ns", 1)
        ):
            fail(
                "E_CONFIG_RESTORE",
                "pool refresh did not cover every member or recover writes",
            )
    reconciliation = bundle["reconciliation"]
    counts = reconciliation.get("counts", {})
    if (
        reconciliation.get("schema")
        != "pg36-ch22-reconciliation-v1"
        or reconciliation.get("run_id")
        != bundle["manifest"].get("run_id")
        or reconciliation.get("status") != "reconciled"
        or counts.get("acknowledged", 0)
        < requirements["switch_probe"]["minimum_acknowledged_attempts"]
        or counts.get("acknowledged_rows_missing")
        != requirements["switch_probe"][
            "maximum_acknowledged_rows_missing"
        ]
        or counts.get("duplicate_tokens")
        != requirements["switch_probe"]["maximum_duplicate_tokens"]
        or counts.get("unreconciled_unknown_outcomes")
        != requirements["switch_probe"][
            "maximum_unreconciled_unknown_outcomes"
        ]
    ):
        fail(
            "E_COMMIT_EVIDENCE",
            "write outcomes are missing, duplicated, or unreconciled",
        )
    metrics = reconciliation.get("metrics", {})
    if (
        metrics.get(
            "maximum_conservative_write_gap_ms", float("inf")
        )
        > requirements["switch_probe"][
            "maximum_conservative_write_gap_ms"
        ]
    ):
        fail("E_RECOVERY_TIME", "write recovery gap exceeded objective")


def validate_ch19_gates(evidence_path: Path) -> None:
    for name in ("preflight-ch19", "postflight-ch19"):
        report = read_json(
            evidence_path.parent / name / "validation-report.json"
        )
        if (
            report.get("schema")
            != "pg36-ch19-validation-report-v1"
            or report.get("status") != "ok"
            or report.get("decision", {}).get("sandbox_l2")
            != "accepted-with-exceptions"
        ):
            fail("E_TOPOLOGY", f"{name} did not pass")


def validate_bundle(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
    evidence_path: Path,
) -> dict[str, Any]:
    validate_manifest(bundle["manifest"], requirements)
    validate_fixture(bundle)
    initial_timeline = validate_snapshot(
        bundle["before"], requirements, "before"
    )
    final_timeline = validate_snapshot(
        bundle["after"], requirements, "after"
    )
    validate_endpoints(bundle)
    validate_pool_semantics(bundle, requirements)
    validate_prepared(bundle)
    validate_replica(bundle, requirements)
    validate_switch(
        bundle,
        requirements,
        initial_timeline,
        final_timeline,
    )
    validate_ch19_gates(evidence_path)
    return {
        "schema": "pg36-ch22-validation-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "run_id": bundle["manifest"]["run_id"],
        "canonical_sha256": {
            "requirements": canonical_sha256(requirements),
        },
        "decision": {
            "sandbox_service_contract": "accepted-with-exceptions",
            "production_ch22_gate": "pending",
            "unplanned_failover": "not-run",
            "vip_or_multi_entry_failover": "not-run",
            "tls_acceptance": "not-run",
            "production_load_test": "not-run",
        },
        "accepted_exception_ids": requirements[
            "required_exception_ids"
        ],
        "service": {
            "entry_address": "10.10.10.11",
            "endpoint_count": 4,
            "pool_mode": "transaction",
            "pool_server_cap_observed": bundle["saturation"][
                "maximum_server_active"
            ],
            "pool_waiters_observed": bundle["saturation"][
                "maximum_client_waiting"
            ],
            "protocol_prepare_reassignment": bundle["prepared"][
                "protocol"
            ]["backend_reassignment_observed"],
            "sql_prepare_expected_sqlstate": bundle["prepared"]["sql"][
                "expected_failure"
            ]["sqlstate"],
            "replica_visibility_delay_ms": bundle["replica"]["replica"][
                "visibility_delay_ms"
            ],
        },
        "switch": {
            "initial_timeline": initial_timeline,
            "forward_timeline": initial_timeline + 1,
            "restored_timeline": final_timeline,
            "acknowledged": bundle["reconciliation"]["counts"][
                "acknowledged"
            ],
            "unknown": bundle["reconciliation"]["counts"]["unknown"],
            "maximum_conservative_write_gap_ms": bundle[
                "reconciliation"
            ]["metrics"]["maximum_conservative_write_gap_ms"],
            "final_leader": "pg-test-1",
        },
    }


def mutate(
    bundle: dict[str, Any],
    mutation: str,
    requirements: dict[str, Any],
) -> None:
    if mutation == "production_claim":
        bundle["manifest"]["production_approval"] = True
    elif mutation == "primary_read_only":
        bundle["endpoints"]["observations"]["primary"][
            "transaction_read_only"
        ] = True
    elif mutation == "replica_writable":
        bundle["endpoints"]["observations"]["replica"][
            "transaction_read_only"
        ] = False
    elif mutation == "offline_member":
        bundle["endpoints"]["observations"]["offline"][
            "selected_member_address"
        ] = "10.10.10.12"
    elif mutation == "session_state_sticky":
        bundle["session"]["state_not_sticky_for_original_client"] = False
    elif mutation == "protocol_prepare_failed":
        bundle["prepared"]["protocol"]["correct_results"] = False
    elif mutation == "sql_prepare_succeeded":
        bundle["prepared"]["sql"]["unexpectedly_succeeded"] = True
    elif mutation == "pool_cap_exceeded":
        bundle["saturation"]["maximum_server_active"] = 3
    elif mutation == "no_waiters":
        bundle["saturation"]["maximum_client_waiting"] = 0
    elif mutation == "pool_not_restored":
        bundle["pool_settings"]["restored_before_switch"] = False
    elif mutation == "ack_missing":
        bundle["reconciliation"]["counts"][
            "acknowledged_rows_missing"
        ] = 1
    elif mutation == "unknown_unreconciled":
        bundle["reconciliation"]["counts"][
            "unreconciled_unknown_outcomes"
        ] = 1
    elif mutation == "write_gap":
        bundle["reconciliation"]["metrics"][
            "maximum_conservative_write_gap_ms"
        ] = (
            requirements["switch_probe"][
                "maximum_conservative_write_gap_ms"
            ]
            + 1
        )
    elif mutation == "wrong_final_leader":
        bundle["manifest"]["final_leader"] = "pg-test-2"
    elif mutation == "source_degraded":
        bundle["after"]["topology"]["members"][2]["state"] = "stopped"
    else:
        fail("E_CASE", f"unknown mutation {mutation}")


def validate_negative_cases(
    bundle: dict[str, Any],
    requirements: dict[str, Any],
    evidence_path: Path,
    cases: dict[str, Any],
) -> dict[str, Any]:
    rows = cases.get("cases")
    if (
        cases.get("schema") != "pg36-ch22-negative-cases-v1"
        or not isinstance(rows, list)
        or len(rows) != len(EXPECTED_NEGATIVE_CODES)
    ):
        fail("E_CASE", "negative case document drifted")
    results: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row.get("id"))
        expected = str(row.get("expected_code"))
        if EXPECTED_NEGATIVE_CODES.get(case_id) != expected:
            fail("E_CASE", f"negative case contract drifted: {case_id}")
        candidate = copy.deepcopy(bundle)
        mutate(candidate, str(row.get("mutation")), requirements)
        try:
            validate_bundle(candidate, requirements, evidence_path)
        except PolicyError as exc:
            actual = exc.code
        else:
            actual = "ACCEPTED"
        if actual != expected:
            fail(
                "E_CASE",
                f"{case_id} produced {actual}, expected {expected}",
            )
        results.append(
            {
                "id": case_id,
                "expected_code": expected,
                "actual_code": actual,
                "status": "rejected-as-intended",
            }
        )
    return {
        "schema": "pg36-ch22-negative-report-v1",
        "status": "ok",
        "case_count": len(results),
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        validate_documents(requirements)
        bundle = load_evidence(args.evidence)
        if args.negative_cases:
            report = validate_negative_cases(
                bundle,
                requirements,
                args.evidence,
                read_json(args.negative_cases),
            )
        else:
            report = validate_bundle(
                bundle,
                requirements,
                args.evidence,
            )
        write_json(args.output, report)
    except PolicyError as exc:
        sys.stderr.write(f"{exc.code}: {exc.message}\n")
        return 1
    print(f"status={report['status']}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
