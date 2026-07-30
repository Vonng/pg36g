#!/usr/bin/env python3
"""Validate chapter 28 contracts, live evidence, and the public summary."""

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
    parser.add_argument("--maintenance", type=Path)
    parser.add_argument("--cleanup", type=Path)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_source(
    source_dir: Path,
    upstream_root: Path,
    negative_cases_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    requirements = read_json(source_dir / "requirements.json")
    contract = read_json(source_dir / "maintenance-contract.json")
    negative = read_json(negative_cases_path)
    missing = [name for name in SOURCE_NAMES if not (source_dir / name).is_file()]
    require(not missing, f"missing source files: {missing}", errors)
    require(
        requirements.get("schema") == "pg36-ch28-requirements-v1",
        "invalid requirements schema",
        errors,
    )
    require(
        requirements.get("target") == "pg36-l2-vagrant/pg-test",
        "target is not the bounded Pigsty sandbox",
        errors,
    )
    risk = requirements.get("risk", {})
    require(
        risk.get("production_data_permitted") is False
        and risk.get("production_traffic_permitted") is False
        and risk.get("cluster_configuration_change_permitted") is False
        and risk.get("forced_drop_permitted") is False,
        "requirements do not fail closed",
        errors,
    )
    forbidden = set(contract.get("forbidden_mutations", []))
    for item in (
        "ALTER SYSTEM",
        "VACUUM FULL",
        "DROP DATABASE FORCE",
        "terminate an unrelated session",
        "touch production data or traffic",
    ):
        require(item in forbidden, f"missing forbidden mutation: {item}", errors)
    require(
        contract.get("hypothesis", "").startswith("A snapshot older"),
        "maintenance hypothesis is not predeclared",
        errors,
    )
    cases = negative.get("cases", [])
    require(len(cases) == 28, "negative case count must be 28", errors)
    require(
        len({row.get("id") for row in cases}) == 28,
        "negative case ids must be unique",
        errors,
    )
    for row in cases:
        require(row.get("rejected") is True, f"{row.get('id')} not rejected", errors)
        require(bool(row.get("reason")), f"{row.get('id')} has no reason", errors)
    remote_source = (source_dir / "remote_experiment.py").read_text(encoding="utf-8")
    dangerous_patterns = {
        "ALTER SYSTEM command": r"""["']\s*ALTER\s+SYSTEM""",
        "VACUUM FULL command": r"""["'][^"']*VACUUM\s+FULL""",
        "forced database drop": r"DROP\s+DATABASE[^;\n]*\bFORCE\b",
        "Patroni mutation": r"patronictl\s+(edit-config|restart|reload)",
    }
    for label, pattern in dangerous_patterns.items():
        require(
            re.search(pattern, remote_source, re.IGNORECASE) is None,
            f"source contains {label}",
            errors,
        )
    for upstream in ("ch19", "ch25", "ch27"):
        require(
            (upstream_root / upstream).is_dir(),
            f"missing upstream lab {upstream}",
            errors,
        )
    return requirements, contract, errors


def core_live_errors(
    preflight: dict[str, Any],
    maintenance: dict[str, Any],
    cleanup: dict[str, Any],
    source_dir: Path,
) -> list[str]:
    errors: list[str] = []
    require(
        preflight.get("schema") == "pg36-ch28-preflight-evidence-v1",
        "invalid preflight schema",
        errors,
    )
    require(preflight.get("mutation") == "none", "preflight mutated target", errors)
    require(
        preflight.get("clean_start")
        == {"database_absent": True, "role_absent": True},
        "preflight did not start clean",
        errors,
    )
    expected_hashes = {name: sha256(source_dir / name) for name in SOURCE_NAMES}
    require(
        preflight.get("source_hashes") == expected_hashes,
        "source hashes do not match preflight",
        errors,
    )
    require(
        maintenance.get("schema") == "pg36-ch28-maintenance-evidence-v1"
        and maintenance.get("status") == "passed",
        "maintenance evidence did not pass",
        errors,
    )
    require(
        maintenance.get("target") == preflight.get("target"),
        "target changed after preflight",
        errors,
    )
    safety = maintenance.get("safety", {})
    require(
        safety.get("production_data_touched") is False
        and safety.get("production_traffic_touched") is False
        and safety.get("persistent_configuration_change") is False
        and safety.get("cluster_autovacuum_changed") is False
        and safety.get("vacuum_full_used") is False
        and safety.get("force_drop_used") is False,
        "maintenance safety boundary failed",
        errors,
    )
    fixture = maintenance.get("fixture", {})
    require(
        fixture
        == {
            "churn_rows": 60000,
            "expired_rows": 10000,
            "current_rows": 5000,
            "parent_rows": 15000,
            "autovacuum_enabled": False,
        },
        "fixture shape changed",
        errors,
    )
    holder = maintenance.get("old_snapshot", {})
    observed = holder.get("observed", {})
    released = holder.get("released", {})
    require(
        bool(observed.get("backend_xmin"))
        and observed.get("application_name") == "pg36-ch28-old-snapshot"
        and observed.get("datname") == "pg36_maintenance"
        and observed.get("usename") == "dbuser_pg36maint",
        "old snapshot was not proven",
        errors,
    )
    require(
        released.get("matched_sessions") == 1
        and released.get("terminated_sessions") == 1
        and released.get("remaining_sessions") == 0,
        "old snapshot was not released exactly",
        errors,
    )
    require(
        maintenance.get("churn")
        == {
            "updated_rows": 40000,
            "deleted_rows": 10000,
            "remaining_rows": 50000,
        },
        "churn row contract failed",
        errors,
    )
    snapshots = maintenance.get("snapshots", {})
    baseline = snapshots.get("baseline", {})
    blocked = snapshots.get("after_vacuum_with_old_snapshot", {})
    final = snapshots.get("after_release_vacuum_freeze", {})
    require(
        baseline.get("current_rows") == 60000,
        "baseline row count is wrong",
        errors,
    )
    require(
        blocked.get("current_rows") == 50000
        and blocked.get("tuple_physical", {}).get("dead_tuple_count", 0) > 0,
        "VACUUM with old snapshot did not retain obsolete tuples",
        errors,
    )
    require(
        final.get("current_rows") == 50000
        and final.get("tuple_physical", {}).get("dead_tuple_count") == 0,
        "post-release VACUUM did not remove obsolete tuples",
        errors,
    )
    require(
        final.get("visibility_map", {}).get("all_visible", 0) > 0
        and final.get("visibility_map", {}).get("all_frozen", 0) > 0,
        "visibility map outcome was not observed",
        errors,
    )
    require(
        final.get("fsm_available_bytes", 0) > 0,
        "post-vacuum reusable space was not observed",
        errors,
    )
    vacuum_runs = maintenance.get("vacuum_runs", {})
    for key in ("with_old_snapshot", "after_release"):
        row = vacuum_runs.get(key, {})
        require(
            row.get("progress_sample_count", 0) > 0
            and row.get("persistent_setting_change") is False,
            f"{key} lacks progress or session-local proof",
            errors,
        )
    checks = maintenance.get("integrity_checks", {})
    for key in ("bt_index_check", "bt_index_parent_check"):
        require(
            checks.get(key, {}).get("return_code") == 0,
            f"{key} failed",
            errors,
        )
    reindex = maintenance.get("concurrent_reindex", {})
    before = reindex.get("before", {})
    after = reindex.get("after", {})
    require(
        reindex.get("operation", {}).get("return_code") == 0
        and before.get("relfilenode") != after.get("relfilenode")
        and after.get("matching_named_indexes") == 1
        and after.get("invalid_fixture_indexes") == 0
        and after.get("concurrent_artifacts") == []
        and after.get("indisvalid") is True
        and after.get("indisready") is True
        and after.get("indislive") is True,
        "concurrent reindex postconditions failed",
        errors,
    )
    partition = maintenance.get("partition_retirement", {})
    require(
        partition.get("round_trip_validated") is True
        and partition.get("drop_performed_only_after_validation") is True
        and partition.get("topology_after_detach")
        == {
            "still_attached": False,
            "parent_rows": 5000,
            "standalone_rows": 10000,
        }
        and partition.get("post_drop")
        == {
            "expired_partition_absent": True,
            "restore_check_absent": True,
            "parent_rows": 5000,
        },
        "partition retirement proof failed",
        errors,
    )
    require(
        partition.get("manifest_before_detach", {}).get("rows") == 10000
        and partition.get("restore_manifest", {}).get("rows") == 10000
        and partition.get("manifest_before_detach", {}).get("logical_digest")
        == partition.get("restore_manifest", {}).get("logical_digest"),
        "partition round-trip manifest mismatch",
        errors,
    )
    exact_cleanup = maintenance.get("cleanup", {})
    require(
        exact_cleanup.get("marker_matched") is True
        and exact_cleanup.get("ordinary_drop") is True
        and exact_cleanup.get("force_drop_used") is False
        and exact_cleanup.get("database_absent") is True
        and exact_cleanup.get("role_absent") is True
        and exact_cleanup.get("sessions_remaining") == 0
        and exact_cleanup.get("unrelated_sessions_terminated") == 0,
        "fixture cleanup failed",
        errors,
    )
    require(
        cleanup.get("schema") == "pg36-ch28-remote-cleanup-v1"
        and cleanup.get("experiment_return_code") == 0
        and cleanup.get("remote_temp_absent") is True,
        "remote temporary cleanup failed",
        errors,
    )
    require(
        maintenance.get("production_ch28_gate") == "pending"
        and preflight.get("production_ch28_gate") == "pending",
        "production gate was bypassed",
        errors,
    )
    return errors


def public_summary(
    preflight: dict[str, Any],
    maintenance: dict[str, Any],
    negative_count: int,
) -> dict[str, Any]:
    pg = preflight["remote"]["postgresql"]
    snapshots = maintenance["snapshots"]
    baseline = snapshots["baseline"]
    blocked = snapshots["after_vacuum_with_old_snapshot"]
    final = snapshots["after_release_vacuum_freeze"]
    partition = maintenance["partition_retirement"]
    return {
        "schema": "pg36-ch28-reference-run-v1",
        "release": "1.0-sandbox",
        "captured_at": maintenance["captured_at"],
        "run_id": maintenance["run_id"],
        "preflight_run_id": preflight["run_id"],
        "target": maintenance["target"],
        "environment": {
            "cluster": pg["cluster_name"],
            "postgresql": pg["server_version"],
            "data_checksums": pg["data_checksums"],
            "fixture_database": "pg36_maintenance",
            "baseline_relation_bytes": baseline["relation_bytes"],
        },
        "upstream": preflight["upstream"],
        "risk": {
            "capture": "L0-read-only",
            "exercise": "L2-bounded-disposable-fixture",
            "production_data_touched": False,
            "production_traffic_touched": False,
            "persistent_configuration_change": False,
            "fixture_table_autovacuum_enabled": False,
            "vacuum_full_used": False,
            "force_drop_used": False,
        },
        "mvcc_reclamation": {
            "initial_rows": baseline["current_rows"],
            "updated_rows": maintenance["churn"]["updated_rows"],
            "deleted_rows": maintenance["churn"]["deleted_rows"],
            "remaining_rows": final["current_rows"],
            "old_snapshot_backend_xmin_observed": True,
            "dead_tuples_after_vacuum_with_old_snapshot":
                blocked["tuple_physical"]["dead_tuple_count"],
            "dead_tuples_after_release_vacuum":
                final["tuple_physical"]["dead_tuple_count"],
            "baseline_relation_bytes": baseline["relation_bytes"],
            "post_release_relation_bytes": final["relation_bytes"],
            "post_release_fsm_available_bytes": final["fsm_available_bytes"],
            "post_release_all_visible_pages":
                final["visibility_map"]["all_visible"],
            "post_release_all_frozen_pages":
                final["visibility_map"]["all_frozen"],
            "baseline_relfrozenxid_age":
                baseline["catalog"]["relfrozenxid_age"],
            "post_release_relfrozenxid_age":
                final["catalog"]["relfrozenxid_age"],
            "progress_samples": {
                "with_old_snapshot": maintenance["vacuum_runs"][
                    "with_old_snapshot"
                ]["progress_sample_count"],
                "after_release": maintenance["vacuum_runs"][
                    "after_release"
                ]["progress_sample_count"],
            },
            "progress_phases": {
                "with_old_snapshot": maintenance["vacuum_runs"][
                    "with_old_snapshot"
                ]["progress_phases"],
                "after_release": maintenance["vacuum_runs"][
                    "after_release"
                ]["progress_phases"],
            },
        },
        "integrity_and_rebuild": {
            "bt_index_check_passed": True,
            "bt_index_parent_check_passed": True,
            "bt_index_check_seconds":
                maintenance["integrity_checks"]["bt_index_check"][
                    "elapsed_seconds"
                ],
            "bt_index_parent_check_seconds":
                maintenance["integrity_checks"]["bt_index_parent_check"][
                    "elapsed_seconds"
                ],
            "reindex_concurrently_passed": True,
            "relfilenode_changed":
                maintenance["concurrent_reindex"]["before"]["relfilenode"]
                != maintenance["concurrent_reindex"]["after"]["relfilenode"],
            "valid_indexes_after": 1,
            "invalid_fixture_indexes_after": 0,
            "concurrent_artifacts_after": 0,
        },
        "partition_retirement": {
            "detach_concurrently_passed": True,
            "expired_rows": partition["manifest_before_detach"]["rows"],
            "archive_bytes": partition["archive"]["bytes"],
            "archive_sha256": partition["archive"]["sha256"],
            "round_trip_validated": partition["round_trip_validated"],
            "parent_rows_after_detach":
                partition["topology_after_detach"]["parent_rows"],
            "partition_dropped_after_validation":
                partition["drop_performed_only_after_validation"],
        },
        "cleanup": {
            "marker_matched": maintenance["cleanup"]["marker_matched"],
            "ordinary_drop": maintenance["cleanup"]["ordinary_drop"],
            "database_absent": maintenance["cleanup"]["database_absent"],
            "role_absent": maintenance["cleanup"]["role_absent"],
            "unrelated_sessions_terminated":
                maintenance["cleanup"]["unrelated_sessions_terminated"],
            "remote_temp_absent": True,
        },
        "decision": {
            "result": "maintenance-loop-demonstrated-in-sandbox",
            "production_ch28_gate": "pending",
            "production_approval": None,
        },
        "validation": {
            "source_hash_bound": True,
            "counterexamples_rejected": negative_count,
            "private_archive_verified": True,
        },
        "claims_not_made": [
            "normal VACUUM never truncates relation files",
            "this run proves a production maintenance window is safe",
            "amcheck replaces checksums or restore tests",
            "one table-local autovacuum override is a production recommendation"
        ],
    }


def mutation_report(
    preflight: dict[str, Any] | None,
    maintenance: dict[str, Any] | None,
    cleanup: dict[str, Any] | None,
    source_dir: Path,
    negative: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for case in negative["cases"]:
        rows.append(
            {
                "id": case["id"],
                "claim": case["claim"],
                "rejected": case["rejected"],
                "reason": case["reason"],
            }
        )
    live_mutants = []
    if preflight is not None and maintenance is not None and cleanup is not None:
        mutators: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("M01-persistent-change", lambda x: x["safety"].__setitem__(
                "persistent_configuration_change", True
            )),
            ("M02-production-data", lambda x: x["safety"].__setitem__(
                "production_data_touched", True
            )),
            ("M03-vacuum-full", lambda x: x["safety"].__setitem__(
                "vacuum_full_used", True
            )),
            ("M04-dead-hidden", lambda x: x["snapshots"][
                "after_vacuum_with_old_snapshot"
            ]["tuple_physical"].__setitem__("dead_tuple_count", 0)),
            ("M05-dead-remains", lambda x: x["snapshots"][
                "after_release_vacuum_freeze"
            ]["tuple_physical"].__setitem__("dead_tuple_count", 1)),
            ("M06-no-xmin", lambda x: x["old_snapshot"]["observed"].__setitem__(
                "backend_xmin", None
            )),
            ("M07-broad-release", lambda x: x["old_snapshot"]["released"].__setitem__(
                "terminated_sessions", 2
            )),
            ("M08-amcheck-fail", lambda x: x["integrity_checks"][
                "bt_index_check"
            ].__setitem__("return_code", 1)),
            ("M09-invalid-index", lambda x: x["concurrent_reindex"]["after"].__setitem__(
                "invalid_fixture_indexes", 1
            )),
            ("M10-partition-unverified", lambda x: x[
                "partition_retirement"
            ].__setitem__("round_trip_validated", False)),
            ("M11-drop-before-verify", lambda x: x[
                "partition_retirement"
            ].__setitem__("drop_performed_only_after_validation", False)),
            ("M12-force-drop", lambda x: x["cleanup"].__setitem__(
                "force_drop_used", True
            )),
            ("M13-unrelated-terminate", lambda x: x["cleanup"].__setitem__(
                "unrelated_sessions_terminated", 1
            )),
            ("M14-production-approved", lambda x: x.__setitem__(
                "production_ch28_gate", "approved"
            )),
        ]
        for mutant_id, mutate in mutators:
            value = copy.deepcopy(maintenance)
            mutate(value)
            rejected = bool(core_live_errors(preflight, value, cleanup, source_dir))
            live_mutants.append({"id": mutant_id, "rejected": rejected})
    return {
        "schema": "pg36-ch28-negative-report-v1",
        "declared_counterexamples": rows,
        "declared_rejected": sum(row["rejected"] is True for row in rows),
        "live_evidence_mutants": live_mutants,
        "live_mutants_rejected": sum(
            row["rejected"] is True for row in live_mutants
        ),
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    requirements, contract, errors = validate_source(
        source_dir,
        upstream_root,
        args.negative_cases.resolve(),
    )
    negative = read_json(args.negative_cases.resolve())
    preflight = maintenance = cleanup = None
    live_requested = any((args.preflight, args.maintenance, args.cleanup))
    if live_requested:
        if not all((args.preflight, args.maintenance, args.cleanup)):
            errors.append("live validation requires preflight, maintenance, and cleanup")
        else:
            preflight = read_json(args.preflight.resolve())
            maintenance = read_json(args.maintenance.resolve())
            cleanup = read_json(args.cleanup.resolve())
            errors.extend(
                core_live_errors(preflight, maintenance, cleanup, source_dir)
            )
            archive = args.maintenance.resolve().parent / "events-2024.csv"
            require(archive.is_file(), "private partition archive is missing", errors)
            if archive.is_file():
                require(
                    sha256(archive)
                    == maintenance.get("partition_retirement", {})
                    .get("archive", {})
                    .get("sha256"),
                    "private partition archive hash mismatch",
                    errors,
                )
                require(
                    sum(1 for _ in archive.open(encoding="utf-8")) == 10000,
                    "private partition archive row count mismatch",
                    errors,
                )
    negative_report = mutation_report(
        preflight, maintenance, cleanup, source_dir, negative
    )
    require(
        negative_report["declared_rejected"] == 28,
        "not every declared counterexample was rejected",
        errors,
    )
    if live_requested:
        require(
            negative_report["live_mutants_rejected"]
            == len(negative_report["live_evidence_mutants"]),
            "one or more live evidence mutants escaped validation",
            errors,
        )
    args.negative_output.parent.mkdir(parents=True, exist_ok=True)
    args.negative_output.write_text(
        json.dumps(negative_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.negative_output.chmod(0o600)
    report = {
        "schema": "pg36-ch28-validation-report-v1",
        "status": "passed" if not errors else "failed",
        "mode": "complete" if live_requested else "lint",
        "checks": {
            "source_files": len(SOURCE_NAMES),
            "declared_counterexamples_rejected":
                negative_report["declared_rejected"],
            "live_mutants_rejected":
                negative_report["live_mutants_rejected"],
            "target": requirements["target"],
            "forbidden_mutations": len(contract["forbidden_mutations"]),
        },
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    if errors:
        raise ValidationError("; ".join(errors))
    if args.public_summary:
        assert preflight is not None and maintenance is not None
        summary = public_summary(
            preflight,
            maintenance,
            negative_report["declared_rejected"],
        )
        args.public_summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.public_summary.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "validation-ok",
                "mode": report["mode"],
                "declared_counterexamples_rejected": 28,
                "live_mutants_rejected":
                    negative_report["live_mutants_rejected"],
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(f"chapter 28 validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
