#!/usr/bin/env python3
"""Validate chapter 29 contracts, live evidence, and public output."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from capture import SOURCE_NAMES


class ValidationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--migration", type=Path)
    parser.add_argument("--cleanup", type=Path)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def logical_manifest(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "customers",
            "orders",
            "status_counts",
            "business_invariants",
        )
    }


def validate_source(
    source_dir: Path,
    upstream_root: Path,
    negative_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    requirements = read_json(source_dir / "requirements.json")
    contract = read_json(source_dir / "migration-contract.json")
    negative = read_json(negative_path)
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    require(not missing, f"missing source files: {missing}", errors)
    require(
        requirements.get("schema") == "pg36-ch29-requirements-v1",
        "invalid requirements schema",
        errors,
    )
    require(
        requirements.get("target")
        == "pg36-l2-vagrant/pg-test-to-pg-meta",
        "target is not the bounded two-cluster sandbox",
        errors,
    )
    risk = requirements.get("risk", {})
    require(
        risk.get("production_data_permitted") is False
        and risk.get("production_traffic_permitted") is False
        and risk.get(
            "persistent_cluster_configuration_change_permitted"
        )
        is False
        and risk.get("actual_platform_route_change_permitted") is False
        and risk.get("forced_drop_permitted") is False,
        "requirements do not fail closed",
        errors,
    )
    require(
        contract.get("schema") == "pg36-ch29-migration-contract-v1"
        and contract.get("hypothesis", "").startswith(
            "A logical migration is acceptable"
        ),
        "migration hypothesis is not predeclared",
        errors,
    )
    forbidden = set(contract.get("forbidden_mutations", []))
    for item in (
        "ALTER SYSTEM",
        "change HAProxy, PgBouncer, DNS, VIP, or application routes",
        "touch production data or traffic",
        "DROP DATABASE FORCE",
        "drop the source before the rollback observation closes",
    ):
        require(item in forbidden, f"missing forbidden mutation: {item}", errors)
    cases = negative.get("cases", [])
    require(len(cases) == 29, "negative case count must be 29", errors)
    require(
        len({row.get("id") for row in cases}) == 29,
        "negative case ids must be unique",
        errors,
    )
    for row in cases:
        require(row.get("rejected") is True, f"{row.get('id')} not rejected", errors)
        require(bool(row.get("reason")), f"{row.get('id')} has no reason", errors)
    remote_source = (source_dir / "remote_experiment.py").read_text(
        encoding="utf-8"
    )
    dangerous = {
        "ALTER SYSTEM command": r"""["']\s*ALTER\s+SYSTEM""",
        "forced database drop": r"DROP\s+DATABASE[^;\n]*\bFORCE\b",
        "Patroni mutation": r"patronictl\s+(edit-config|restart|reload)",
        "HAProxy mutation": r"systemctl\s+(restart|reload)\s+haproxy",
    }
    for label, pattern in dangerous.items():
        require(
            re.search(pattern, remote_source, re.IGNORECASE) is None,
            f"source contains {label}",
            errors,
        )
    for upstream in ("ch19", "ch23", "ch25", "ch28"):
        require(
            (upstream_root / upstream).is_dir(),
            f"missing upstream lab {upstream}",
            errors,
        )
    return requirements, contract, errors


def core_live_errors(
    preflight: dict[str, Any],
    migration: dict[str, Any],
    cleanup: dict[str, Any],
    source_dir: Path,
) -> list[str]:
    errors: list[str] = []
    require(
        preflight.get("schema") == "pg36-ch29-preflight-evidence-v1",
        "invalid preflight schema",
        errors,
    )
    require(preflight.get("mutation") == "none", "preflight mutated target", errors)
    expected_clean = {
        "source": {
            "database_absent": True,
            "owner_role_absent": True,
            "runtime_role_absent": True,
            "replication_role_absent": True,
            "slot_absent": True,
        },
        "target": {
            "database_absent": True,
            "owner_role_absent": True,
            "runtime_role_absent": True,
            "subscription_absent": True,
        },
    }
    require(
        preflight.get("clean_start") == expected_clean,
        "preflight did not start clean",
        errors,
    )
    expected_hashes = {name: sha256(source_dir / name) for name in SOURCE_NAMES}
    require(
        preflight.get("source_hashes") == expected_hashes,
        "source hashes do not match preflight",
        errors,
    )
    source_remote = preflight.get("remote", {}).get("source", {})
    target_remote = preflight.get("remote", {}).get("target", {})
    require(
        source_remote.get("cluster_name") == "pg-test"
        and target_remote.get("cluster_name") == "pg-meta"
        and source_remote.get("system_identifier")
        != target_remote.get("system_identifier")
        and source_remote.get("in_recovery") is False
        and target_remote.get("in_recovery") is False
        and source_remote.get("wal_level") == "logical",
        "source/target identity preflight failed",
        errors,
    )
    require(
        migration.get("schema") == "pg36-ch29-migration-evidence-v1"
        and migration.get("status") == "passed"
        and migration.get("target") == preflight.get("target"),
        "migration evidence did not pass",
        errors,
    )
    environment = migration.get("environment", {})
    require(
        environment.get("source_cluster") == "pg-test"
        and environment.get("target_cluster") == "pg-meta"
        and environment.get("distinct_system_identifiers") is True
        and environment.get("source_system_identifier")
        != environment.get("target_system_identifier"),
        "migration environment identity failed",
        errors,
    )
    safety = migration.get("safety", {})
    safety_false = (
        "production_data_touched",
        "production_traffic_touched",
        "persistent_cluster_configuration_change",
        "pigsty_inventory_changed",
        "patroni_configuration_changed",
        "actual_platform_route_changed",
        "unrelated_subscription_changed",
        "unrelated_slot_changed",
        "force_drop_used",
    )
    require(
        all(safety.get(key) is False for key in safety_false),
        "migration safety boundary failed",
        errors,
    )
    fixture = migration.get("fixture", {})
    require(
        fixture.get("initial") == {"customers": 5000, "orders": 20000}
        and fixture.get("source_target_credentials_isolated") is True
        and fixture.get("replication_secret_published") is False,
        "fixture shape or credential isolation failed",
        errors,
    )
    initial = migration.get("initial_copy", {})
    initial_states = {
        row.get("state")
        for row in initial.get("subscription", {}).get("relations", [])
    }
    require(
        initial.get("logical_manifest_equal") is True
        and initial_states == {"r"}
        and len(initial.get("subscription", {}).get("relations", [])) == 2
        and initial.get("source_manifest", {}).get("customers", {}).get("rows")
        == 5000
        and initial.get("source_manifest", {}).get("orders", {}).get("rows")
        == 20000
        and logical_manifest(initial.get("source_manifest", {}))
        == logical_manifest(initial.get("target_manifest", {})),
        "initial copy proof failed",
        errors,
    )
    incremental = migration.get("incremental", {})
    require(
        incremental.get("changes")
        == {"inserted": 500, "updated": 200, "deleted": 100}
        and incremental.get("convergence", {}).get("marker_acknowledged") is True
        and incremental.get("convergence", {}).get("logical_manifest_equal")
        is True,
        "incremental convergence failed",
        errors,
    )
    stall = migration.get("consumer_stall", {})
    require(
        stall.get("disabled_state", {}).get("subscription", {}).get("enabled")
        is False
        and stall.get("disabled_state", {}).get("slot", {}).get("active") is False
        and stall.get("changes") == {"inserted": 3000}
        and stall.get("confirmed_lsn_unchanged") is True
        and stall.get("retained_bytes_grew") is True
        and int(stall.get("after", {}).get("retained_bytes", 0))
        > int(stall.get("before", {}).get("retained_bytes", 0))
        and stall.get("recovery", {}).get("marker_acknowledged") is True
        and stall.get("recovery", {}).get("logical_manifest_equal") is True,
        "consumer stall or recovery proof failed",
        errors,
    )
    conflict = migration.get("conflict", {})
    before_conflict = conflict.get("before", {})
    observed_conflict = conflict.get("observed", {}).get("conflicts", {})
    conflict_rows = conflict.get("source_and_target_rows_before_repair", {})
    require(
        conflict.get("id") == 900000
        and int(observed_conflict.get("confl_insert_exists", 0))
        > int(before_conflict.get("confl_insert_exists", 0))
        and int(observed_conflict.get("apply_error_count", 0))
        > int(before_conflict.get("apply_error_count", 0))
        and conflict_rows.get("source", {}).get("note") == "source-authority"
        and conflict_rows.get("target", {}).get("note") == "target-conflict"
        and conflict.get("repair", {}).get("marker_acknowledged") is True
        and conflict.get("repair", {}).get("logical_manifest_equal") is True,
        "insert conflict proof or repair failed",
        errors,
    )
    drift = migration.get("silent_drift", {})
    require(
        drift.get("id") == 1
        and drift.get("mismatched_buckets_before") == [1]
        and drift.get("mismatched_buckets_after") == []
        and drift.get("post_repair", {}).get("logical_manifest_equal") is True,
        "silent drift proof or repair failed",
        errors,
    )
    cutover = migration.get("cutover_and_rollback", {})
    fence = cutover.get("write_fence", {})
    sequence = cutover.get("target_sequence_after", {})
    route = cutover.get("route_history", [])
    require(
        fence.get("attempt_return_code", 0) != 0
        and fence.get("sqlstate") == "42501"
        and fence.get("privileges")
        == {"insert": False, "update": False, "delete": False, "select": True},
        "source write fence proof failed",
        errors,
    )
    require(
        int(sequence.get("set_to", 0)) >= int(cutover.get("source_max_order_id", 0))
        and int(cutover.get("target_cutover_canary", {}).get("order_id", 0))
        > int(cutover.get("source_max_order_id", 0))
        and cutover.get("target_only_rows_reconciled") == 1,
        "sequence synchronization or rollback reconciliation failed",
        errors,
    )
    require(
        [row.get("route") for row in route] == ["source", "target", "source"]
        and all(row.get("platform_route_changed") is False for row in route)
        and cutover.get("actual_platform_route_changed") is False
        and cutover.get("source_retained_through_rollback") is True
        and cutover.get("final_convergence", {}).get("marker_acknowledged") is True
        and cutover.get("final_convergence", {}).get("logical_manifest_equal")
        is True,
        "simulated cutover or rollback proof failed",
        errors,
    )
    final_manifest = cutover.get("final_convergence", {}).get(
        "source_manifest", {}
    )
    require(
        final_manifest.get("business_invariants")
        == {"orphan_orders": 0, "negative_amounts": 0, "invalid_statuses": 0},
        "final business invariants failed",
        errors,
    )
    exact = migration.get("cleanup", {})
    source_clean = exact.get("source", {})
    target_clean = exact.get("target", {})
    require(
        exact.get("marker_matched") is True
        and exact.get("ordinary_drop") is True
        and exact.get("force_drop_used") is False
        and exact.get("unrelated_sessions_terminated") == 0
        and all(
            source_clean.get(key) is True
            for key in (
                "database_absent",
                "owner_role_absent",
                "runtime_role_absent",
                "replication_role_absent",
                "slot_absent",
            )
        )
        and all(
            target_clean.get(key) is True
            for key in (
                "database_absent",
                "owner_role_absent",
                "runtime_role_absent",
                "subscription_absent",
            )
        )
        and source_clean.get("sessions_remaining") == 0
        and target_clean.get("sessions_remaining") == 0,
        "exact two-cluster cleanup failed",
        errors,
    )
    require(
        cleanup.get("schema") == "pg36-ch29-remote-cleanup-v1"
        and cleanup.get("experiment_return_code") == 0
        and cleanup.get("remote_temp_absent") is True,
        "remote temporary cleanup failed",
        errors,
    )
    require(
        preflight.get("production_ch29_gate") == "pending"
        and migration.get("production_ch29_gate") == "pending",
        "production gate was bypassed",
        errors,
    )
    return errors


def mutate(
    preflight: dict[str, Any],
    migration: dict[str, Any],
    cleanup: dict[str, Any],
) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    cases: list[
        tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]
    ] = []

    def add(
        name: str,
        changer: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], None],
    ) -> None:
        p = copy.deepcopy(preflight)
        m = copy.deepcopy(migration)
        c = copy.deepcopy(cleanup)
        changer(p, m, c)
        cases.append((name, p, m, c))

    add(
        "same-system-id",
        lambda p, m, c: p["remote"]["target"].__setitem__(
            "system_identifier", p["remote"]["source"]["system_identifier"]
        ),
    )
    add(
        "capture-mutated",
        lambda p, m, c: p.__setitem__("mutation", "writes"),
    )
    add(
        "source-hash-drift",
        lambda p, m, c: p["source_hashes"].__setitem__(
            "task.sh", "0" * 64
        ),
    )
    add(
        "migration-failed",
        lambda p, m, c: m.__setitem__("status", "failed"),
    )
    add(
        "real-route-change",
        lambda p, m, c: m["safety"].__setitem__(
            "actual_platform_route_changed", True
        ),
    )
    add(
        "initial-not-equal",
        lambda p, m, c: m["initial_copy"].__setitem__(
            "logical_manifest_equal", False
        ),
    )
    add(
        "initial-state-copying",
        lambda p, m, c: m["initial_copy"]["subscription"]["relations"][0].__setitem__(
            "state", "d"
        ),
    )
    add(
        "incremental-count",
        lambda p, m, c: m["incremental"]["changes"].__setitem__(
            "inserted", 499
        ),
    )
    add(
        "stall-active",
        lambda p, m, c: m["consumer_stall"]["disabled_state"]["slot"].__setitem__(
            "active", True
        ),
    )
    add(
        "stall-ack-advanced",
        lambda p, m, c: m["consumer_stall"].__setitem__(
            "confirmed_lsn_unchanged", False
        ),
    )
    add(
        "stall-no-retention",
        lambda p, m, c: m["consumer_stall"].__setitem__(
            "retained_bytes_grew", False
        ),
    )
    add(
        "conflict-not-counted",
        lambda p, m, c: m["conflict"]["observed"]["conflicts"].__setitem__(
            "confl_insert_exists",
            m["conflict"]["before"]["confl_insert_exists"],
        ),
    )
    add(
        "drift-not-repaired",
        lambda p, m, c: m["silent_drift"].__setitem__(
            "mismatched_buckets_after", [1]
        ),
    )
    add(
        "fence-not-enforced",
        lambda p, m, c: m["cutover_and_rollback"]["write_fence"].__setitem__(
            "sqlstate", None
        ),
    )
    add(
        "sequence-behind",
        lambda p, m, c: m["cutover_and_rollback"][
            "target_sequence_after"
        ].__setitem__("set_to", 1),
    )
    add(
        "source-not-retained",
        lambda p, m, c: m["cutover_and_rollback"].__setitem__(
            "source_retained_through_rollback", False
        ),
    )
    add(
        "source-cleanup-failed",
        lambda p, m, c: m["cleanup"]["source"].__setitem__(
            "database_absent", False
        ),
    )
    add(
        "target-cleanup-failed",
        lambda p, m, c: m["cleanup"]["target"].__setitem__(
            "subscription_absent", False
        ),
    )
    add(
        "production-gate-bypassed",
        lambda p, m, c: m.__setitem__("production_ch29_gate", "approved"),
    )
    return cases


def public_summary(
    preflight: dict[str, Any],
    migration: dict[str, Any],
    declared_rejected: int,
) -> dict[str, Any]:
    initial = migration["initial_copy"]
    incremental = migration["incremental"]
    stall = migration["consumer_stall"]
    conflict = migration["conflict"]
    drift = migration["silent_drift"]
    cutover = migration["cutover_and_rollback"]
    final_manifest = cutover["final_convergence"]["source_manifest"]
    return {
        "schema": "pg36-ch29-reference-run-v1",
        "release": "1.0-sandbox",
        "captured_at": migration["captured_at"],
        "run_id": migration["run_id"],
        "preflight_run_id": preflight["run_id"],
        "target": migration["target"],
        "environment": {
            "source_cluster": migration["environment"]["source_cluster"],
            "target_cluster": migration["environment"]["target_cluster"],
            "distinct_system_identifiers": True,
            "source_postgresql": preflight["remote"]["source"]["server_version"],
            "target_postgresql": preflight["remote"]["target"]["server_version"],
            "source_wal_level": preflight["remote"]["source"]["wal_level"],
        },
        "initial_copy": {
            "customers": initial["source_manifest"]["customers"]["rows"],
            "orders": initial["source_manifest"]["orders"]["rows"],
            "tables_ready": len(initial["subscription"]["relations"]),
            "logical_manifest_equal": initial["logical_manifest_equal"],
        },
        "incremental": {
            "inserted": incremental["changes"]["inserted"],
            "updated": incremental["changes"]["updated"],
            "deleted": incremental["changes"]["deleted"],
            "marker_acknowledged":
                incremental["convergence"]["marker_acknowledged"],
            "logical_manifest_equal":
                incremental["convergence"]["logical_manifest_equal"],
        },
        "consumer_stall": {
            "generated_rows": stall["changes"]["inserted"],
            "slot_inactive": stall["disabled_state"]["slot"]["active"] is False,
            "confirmed_lsn_unchanged": stall["confirmed_lsn_unchanged"],
            "retained_bytes_before": stall["before"]["retained_bytes"],
            "retained_bytes_after": stall["after"]["retained_bytes"],
            "retained_bytes_grew": stall["retained_bytes_grew"],
            "caught_up_after_enable":
                stall["recovery"]["marker_acknowledged"]
                and stall["recovery"]["logical_manifest_equal"],
        },
        "conflict_and_reconciliation": {
            "conflict_order_id": conflict["id"],
            "insert_exists_before":
                conflict["before"]["confl_insert_exists"],
            "insert_exists_after":
                conflict["observed"]["conflicts"]["confl_insert_exists"],
            "apply_errors_after":
                conflict["observed"]["conflicts"]["apply_error_count"],
            "conflict_repaired": conflict["repair"]["logical_manifest_equal"],
            "drift_order_id": drift["id"],
            "mismatched_buckets_before":
                drift["mismatched_buckets_before"],
            "mismatched_buckets_after":
                drift["mismatched_buckets_after"],
        },
        "cutover_and_rollback": {
            "source_write_fence_sqlstate":
                cutover["write_fence"]["sqlstate"],
            "source_max_order_id": cutover["source_max_order_id"],
            "target_sequence_before": cutover["target_sequence_before"],
            "target_sequence_after":
                cutover["target_sequence_after"]["set_to"],
            "target_canary_order_id":
                cutover["target_cutover_canary"]["order_id"],
            "route_history": [
                row["route"] for row in cutover["route_history"]
            ],
            "actual_platform_route_changed": False,
            "target_only_rows_reconciled":
                cutover["target_only_rows_reconciled"],
            "source_retained_through_rollback":
                cutover["source_retained_through_rollback"],
            "final_customers": final_manifest["customers"]["rows"],
            "final_orders": final_manifest["orders"]["rows"],
            "final_business_invariants":
                final_manifest["business_invariants"],
            "final_logical_manifest_equal":
                cutover["final_convergence"]["logical_manifest_equal"],
        },
        "cleanup": {
            "source_database_absent":
                migration["cleanup"]["source"]["database_absent"],
            "source_slot_absent":
                migration["cleanup"]["source"]["slot_absent"],
            "target_database_absent":
                migration["cleanup"]["target"]["database_absent"],
            "target_subscription_absent":
                migration["cleanup"]["target"]["subscription_absent"],
            "all_roles_absent": all(
                migration["cleanup"][side][key]
                for side, key in (
                    ("source", "owner_role_absent"),
                    ("source", "runtime_role_absent"),
                    ("source", "replication_role_absent"),
                    ("target", "owner_role_absent"),
                    ("target", "runtime_role_absent"),
                )
            ),
            "ordinary_drop": migration["cleanup"]["ordinary_drop"],
            "force_drop_used": migration["cleanup"]["force_drop_used"],
            "unrelated_sessions_terminated":
                migration["cleanup"]["unrelated_sessions_terminated"],
        },
        "risk": migration["safety"],
        "validation": {
            "declared_counterexamples_rejected": declared_rejected,
            "live_evidence_mutants_rejected": 19,
            "source_hash_bound": True,
            "private_bundle_required": True,
        },
        "claims_not_made": [
            "this run changed a real application or Pigsty route",
            "logical replication copied DDL, sequences, or large objects",
            "row counts alone proved semantic equivalence",
            "the sandbox result authorizes a production migration"
        ],
        "decision": {
            "result": "two-cluster-migration-state-machine-demonstrated",
            "production_approval": None,
            "production_ch29_gate": "pending",
        },
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    requirements, contract, source_errors = validate_source(
        source_dir,
        upstream_root,
        args.negative_cases.resolve(),
    )
    negative = read_json(args.negative_cases.resolve())
    declared_rejected = sum(
        1 for row in negative["cases"] if row.get("rejected") is True
    )
    if source_errors:
        raise ValidationError("; ".join(source_errors))
    complete_paths = (args.preflight, args.migration, args.cleanup)
    if not any(complete_paths):
        report = {
            "schema": "pg36-ch29-validation-report-v1",
            "status": "passed",
            "mode": "source-only",
            "declared_counterexamples_rejected": declared_rejected,
            "live_mutants_rejected": 0,
            "production_ch29_gate": "pending",
            "requirements_schema": requirements["schema"],
            "contract_schema": contract["schema"],
        }
        write_json(args.negative_output.resolve(), {
            "schema": "pg36-ch29-negative-report-v1",
            "declared_rejected": declared_rejected,
            "live_mutants_rejected": 0,
            "status": "passed",
        })
        write_json(args.output.resolve(), report)
        print(json.dumps({
            "status": "validation-ok",
            "mode": "source-only",
            "declared_counterexamples_rejected": declared_rejected,
        }, separators=(",", ":")))
        return 0
    if not all(complete_paths):
        raise ValidationError("complete validation requires all evidence paths")
    preflight = read_json(args.preflight.resolve())
    migration = read_json(args.migration.resolve())
    cleanup = read_json(args.cleanup.resolve())
    live_errors = core_live_errors(preflight, migration, cleanup, source_dir)
    if live_errors:
        raise ValidationError("; ".join(live_errors))
    mutants = mutate(preflight, migration, cleanup)
    rejected: list[dict[str, Any]] = []
    accepted: list[str] = []
    for name, mutant_preflight, mutant_migration, mutant_cleanup in mutants:
        errors = core_live_errors(
            mutant_preflight,
            mutant_migration,
            mutant_cleanup,
            source_dir,
        )
        if errors:
            rejected.append({"id": name, "errors": errors})
        else:
            accepted.append(name)
    if accepted:
        raise ValidationError(f"live mutants unexpectedly passed: {accepted}")
    negative_report = {
        "schema": "pg36-ch29-negative-report-v1",
        "status": "passed",
        "declared_rejected": declared_rejected,
        "live_mutants_rejected": len(rejected),
        "live_mutants": rejected,
    }
    report = {
        "schema": "pg36-ch29-validation-report-v1",
        "status": "passed",
        "mode": "complete",
        "declared_counterexamples_rejected": declared_rejected,
        "live_mutants_rejected": len(rejected),
        "production_ch29_gate": "pending",
    }
    write_json(args.negative_output.resolve(), negative_report)
    write_json(args.output.resolve(), report)
    if args.public_summary:
        write_json(
            args.public_summary.resolve(),
            public_summary(preflight, migration, declared_rejected),
        )
    print(json.dumps({
        "status": "validation-ok",
        "mode": "complete",
        "declared_counterexamples_rejected": declared_rejected,
        "live_mutants_rejected": len(rejected),
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"chapter 29 validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
