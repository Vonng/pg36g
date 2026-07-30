#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ValidationError(RuntimeError):
    pass


SOURCE_FILES = [
    "requirements.json",
    "upgrade-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "remote_experiment.py",
    "validate.py",
    "review.py",
    "task.sh",
]

EXPECTED_STATES = [
    "PREFLIGHT",
    "SOURCE_BASELINE",
    "COMPATIBILITY_BLOCKED",
    "COMPATIBILITY_REPAIRED",
    "SOURCE_STOPPED",
    "CHECK_REJECTED",
    "CHECK_PASSED",
    "UPGRADED",
    "VALIDATED",
    "ROLLBACK_PROVEN",
    "FORWARD_COMMITTED",
    "CLEANED",
]

EXPECTED_REPAIR_ORDER = [
    "REINDEX INDEX app.orders_order_code_key",
    "ALTER COLLATION app.en_numeric REFRESH VERSION",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON document is not an object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_hashes(source_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = source_dir / name
        require(path.is_file(), f"source file missing: {path}")
        result[name] = sha256_file(path)
    return result


def validate_static(
    requirements: dict[str, Any],
    contract: dict[str, Any],
    negative: dict[str, Any],
) -> None:
    require(
        requirements.get("schema") == "pg36-ch30-requirements-v1",
        "requirements schema mismatch",
    )
    require(requirements.get("chapter") == 30, "chapter must be 30")
    require(
        requirements.get("target")
        == "pg36-l2-vagrant/isolated-pg17-to-pg18",
        "target mismatch",
    )
    require(
        requirements["versions"] == {"old_major": 17, "new_major": 18},
        "required major versions changed",
    )
    require(
        requirements["execution"]["upgrade_method"] == "copy",
        "only copy upgrade method is permitted",
    )
    require(
        requirements["fixture"]["initial_rows"] == 10000
        and requirements["fixture"]["forward_canary_id"] == 10001,
        "fixture cardinality changed",
    )
    for field in [
        "production_data_permitted",
        "production_traffic_permitted",
        "pigsty_inventory_change_permitted",
        "patroni_change_permitted",
        "persistent_cluster_configuration_change_permitted",
        "system_package_install_permitted",
        "external_listener_permitted",
        "pg_upgrade_link_clone_swap_permitted",
    ]:
        require(
            requirements["risk"].get(field) is False,
            f"risk boundary changed: {field}",
        )
    require(
        requirements["acceptance"]["production_ch30_gate"] == "pending",
        "production gate must remain pending",
    )

    require(
        contract.get("schema") == "pg36-ch30-upgrade-contract-v1",
        "contract schema mismatch",
    )
    require(contract.get("states") == EXPECTED_STATES, "state list changed")
    expected_transitions = [
        [left, right]
        for left, right in zip(EXPECTED_STATES, EXPECTED_STATES[1:])
    ]
    require(
        contract.get("transitions") == expected_transitions,
        "state transitions are not linear and complete",
    )
    forbidden_text = "\n".join(contract.get("forbidden_mutations", []))
    for token in [
        "system packages",
        "Pigsty inventory",
        "Patroni",
        "listen on TCP",
        "link, clone",
        "delete_old_cluster.sh",
        "system catalog",
        "unrelated",
        "unmarked",
    ]:
        require(token in forbidden_text, f"forbidden boundary missing: {token}")
    require(
        contract["release_gates"]["production_ch30_gate"] == "pending",
        "contract production gate changed",
    )

    require(
        negative.get("schema") == "pg36-ch30-negative-cases-v1",
        "negative case schema mismatch",
    )
    cases = negative.get("cases")
    require(isinstance(cases, list) and len(cases) == 30, "need 30 cases")
    ids = [case.get("id") for case in cases]
    require(len(set(ids)) == 30, "negative case IDs are not unique")
    for case in cases:
        require(
            case.get("document")
            in {
                "requirements",
                "contract",
                "preflight",
                "upgrade",
                "fixture_cleanup",
                "remote_cleanup",
            },
            f"unknown case document: {case}",
        )
        require(
            isinstance(case.get("path"), list) and case["path"],
            f"negative case path missing: {case}",
        )
        require(
            case.get("operation") in {"set", "delete"},
            f"negative case operation invalid: {case}",
        )


def validate_manifest(
    value: dict[str, Any],
    *,
    expected_rows: int,
    expected_max_id: int,
) -> None:
    require(value.get("rows") == expected_rows, "manifest row count mismatch")
    require(value.get("min_id") == 1, "manifest minimum ID mismatch")
    require(value.get("max_id") == expected_max_id, "manifest maximum ID mismatch")
    require(value.get("negative_amounts") == 0, "negative amount found")
    require(value.get("invalid_statuses") == 0, "invalid status found")
    require(
        isinstance(value.get("ordered_digest_md5"), str)
        and len(value["ordered_digest_md5"]) == 32,
        "ordered digest invalid",
    )
    counts = value.get("status_counts")
    require(isinstance(counts, dict), "status counts missing")
    require(sum(int(item) for item in counts.values()) == expected_rows,
            "status counts do not sum to row count")


def validate_complete(
    documents: dict[str, dict[str, Any]],
    *,
    source_dir: Path,
    upstream_root: Path,
    check_logs: bool,
) -> None:
    requirements = documents["requirements"]
    contract = documents["contract"]
    negative = documents["negative"]
    preflight = documents["preflight"]
    upgrade = documents["upgrade"]
    fixture_cleanup = documents["fixture_cleanup"]
    remote_cleanup = documents["remote_cleanup"]
    validate_static(requirements, contract, negative)

    require(
        preflight.get("schema") == "pg36-ch30-preflight-evidence-v1",
        "preflight schema mismatch",
    )
    require(preflight.get("target") == requirements["target"], "preflight target")
    env = preflight["environment"]
    require(env.get("old_major") == 17, "preflight old major mismatch")
    require(env.get("new_major") == 18, "preflight new major mismatch")
    require(
        env["managed_host"].get("cluster_name")
        == requirements["host"]["cluster"],
        "managed host cluster mismatch",
    )
    require(
        env["managed_host"].get("in_recovery") is False,
        "managed host is not primary",
    )
    require(env.get("locale_c_available") is True, "C locale unavailable")
    require(
        int(env.get("tmp_free_bytes", 0))
        >= requirements["execution"]["minimum_free_bytes"],
        "insufficient temporary space",
    )
    require(env.get("stale_fixture_roots") == [], "stale fixture root exists")
    require(env.get("live_temp_postmasters") == [], "temp postmaster exists")
    require(
        preflight.get("source_hashes") == current_hashes(source_dir),
        "preflight source hashes do not match current source",
    )
    require(
        len(preflight["source_hashes"]) == len(SOURCE_FILES),
        "source hash count mismatch",
    )
    for name, item in preflight["upstream"].items():
        path = upstream_root / item["relative_path"]
        require(path.is_file(), f"upstream evidence missing: {name}")
        require(
            sha256_file(path) == item["sha256"],
            f"upstream evidence hash changed: {name}",
        )
    for field, value in preflight["risk"].items():
        if field != "mutation":
            require(value is False, f"preflight risk claim true: {field}")
    require(preflight["risk"]["mutation"] == "none", "capture mutated state")
    require(
        preflight["decision"]["production_ch30_gate"] == "pending",
        "preflight production gate changed",
    )

    require(
        upgrade.get("schema") == "pg36-ch30-upgrade-evidence-v1",
        "upgrade schema mismatch",
    )
    require(upgrade.get("target") == requirements["target"], "upgrade target")
    require(
        upgrade.get("preflight_run_id") == preflight.get("preflight_run_id"),
        "preflight run is not bound",
    )
    require(upgrade.get("states") == EXPECTED_STATES, "state history mismatch")
    upgrade_env = upgrade["environment"]
    require(
        upgrade_env.get("old_major") == 17
        and upgrade_env.get("new_major") == 18,
        "upgrade major versions mismatch",
    )
    require(
        upgrade_env.get("old_postgres_sha256")
        == env.get("old_postgres_sha256"),
        "old postgres binary changed after preflight",
    )
    require(
        upgrade_env.get("new_pg_upgrade_sha256")
        == env.get("new_pg_upgrade_sha256"),
        "new pg_upgrade binary changed after preflight",
    )
    require(
        upgrade_env.get("host_before") == upgrade_env.get("host_after"),
        "managed host identity changed",
    )
    require(
        upgrade_env["host_before"].get("cluster_name")
        == requirements["host"]["cluster"],
        "wrong managed host in upgrade",
    )
    require(
        upgrade_env.get("unix_socket_only") is True
        and upgrade_env.get("listen_addresses") == "",
        "temporary cluster exposed a listener",
    )

    source = upgrade["source"]
    baseline = source["baseline"]
    baseline_manifest = baseline["manifest"]
    validate_manifest(baseline_manifest, expected_rows=10000, expected_max_id=10000)
    require(
        baseline["collation"].get("mismatch") is False,
        "baseline collation already mismatched",
    )
    require(
        requirements["fixture"]["collation_index"]
        in baseline["collation"]["affected_indexes"],
        "baseline collation index missing",
    )
    require(
        baseline["health"]["invalid_indexes"] == 0
        and baseline["health"]["prepared_transactions"] == 0,
        "source baseline health failed",
    )
    require(
        source.get("manifest_after_repair") == baseline_manifest,
        "collation repair changed logical data",
    )
    require(source.get("checksum_check_passed") is True,
            "source checksum check failed")

    gate = upgrade["collation_gate"]
    require(
        gate.get("injection") == "exact-disposable-collversion-row",
        "collation injection scope drifted",
    )
    require(
        gate.get("injected_value") == "pg36-injected-stale",
        "collation injection value drifted",
    )
    require(gate["state_before"].get("mismatch") is True,
            "collation mismatch was not observed")
    require(
        gate["state_before"].get("recorded_version")
        == "pg36-injected-stale",
        "injected collation version missing",
    )
    require(
        gate["state_before"].get("recorded_version")
        != gate["state_before"].get("actual_version"),
        "injected and actual collation versions are equal",
    )
    require(
        requirements["fixture"]["collation_index"]
        in gate["state_before"]["affected_indexes"],
        "affected collation index not found",
    )
    require(gate.get("release_before") == "blocked",
            "collation gate did not block")
    require(gate.get("repair_order") == EXPECTED_REPAIR_ORDER,
            "collation repair order changed")
    require(gate.get("reindex_completed") is True,
            "collation index was not rebuilt")
    require(gate.get("refresh_completed") is True,
            "collation version was not refreshed")
    require(gate["state_after"].get("mismatch") is False,
            "collation mismatch remains")
    require(
        gate["state_after"].get("recorded_version")
        == gate["state_after"].get("actual_version"),
        "collation recorded version was not refreshed",
    )

    bad = upgrade["incompatible_target"]
    require(bad.get("old_checksums") is True, "old checksums claim changed")
    require(bad.get("new_checksums") is False, "bad target checksums claim")
    require(bad.get("check_returncode") != 0,
            "incompatible pg_upgrade check passed")
    require(
        bad.get("expected_failure")
        == "old cluster uses data checksums but the new one does not",
        "unexpected incompatible check reason",
    )
    require(bad.get("expected_failure_observed") is True,
            "checksum mismatch reason not observed")
    require(bad.get("target_removed") is True,
            "rejected target was not removed")

    result = upgrade["upgrade"]
    require(result.get("method") == "copy", "upgrade method is not copy")
    require(
        result.get("check_returncode") == 0
        and result.get("check_passed") is True,
        "matching pg_upgrade check failed",
    )
    require(
        result.get("run_returncode") == 0
        and result.get("complete") is True,
        "pg_upgrade did not complete",
    )
    require(result.get("manifest_equal_before_writes") is True,
            "upgraded manifest differs")
    require(result.get("extension_manifest_equal_before_amcheck") is True,
            "extension manifest differs")
    require(result.get("query_result_equal") is True,
            "representative query result differs")
    upgraded = result["upgraded_before_writes"]
    require(upgraded["manifest"] == baseline_manifest,
            "upgraded manifest evidence differs")
    require(upgraded["extensions"] == baseline["extensions"],
            "upgraded extension evidence differs")
    require(upgraded["collation"]["mismatch"] is False,
            "upgraded collation mismatch")
    require(
        upgraded["health"]["invalid_indexes"] == 0
        and upgraded["health"]["prepared_transactions"] == 0,
        "upgraded health failed",
    )
    require(
        int(upgraded["identity"]["server_version_num"]) // 10000 == 18,
        "upgraded server is not major 18",
    )
    require(upgraded["identity"]["data_checksums"] == "on",
            "upgraded checksums are not on")
    require(result.get("amcheck_passed") is True, "amcheck did not pass")
    require(
        sorted(result.get("amcheck_indexes", []))
        == ["app.orders_order_code_key", "app.orders_pkey"],
        "amcheck index set mismatch",
    )
    require(result.get("post_upgrade_analyze_completed") is True,
            "post-upgrade analyze missing")
    require(isinstance(result.get("source_plan"), list), "source plan missing")
    require(isinstance(result.get("target_plan"), list), "target plan missing")

    rollback = upgrade["rollback"]
    require(rollback.get("new_cluster_stopped_before_old_start") is True,
            "new cluster was not stopped before rollback")
    require(rollback.get("target_only_writes_before_proof") == 0,
            "target wrote before rollback proof")
    require(rollback.get("old_cluster_restarted") is True,
            "old cluster did not restart")
    require(rollback.get("old_major") == 17, "rollback old major mismatch")
    require(rollback.get("manifest_equal") is True,
            "rollback manifest flag false")
    require(rollback.get("manifest") == baseline_manifest,
            "rollback manifest differs")
    require(rollback.get("collation_match") is True,
            "rollback collation mismatch")
    require(rollback.get("proven_before_target_writes") is True,
            "rollback timing is unsafe")

    forward = upgrade["forward"]
    require(forward.get("old_cluster_stopped") is True,
            "old cluster was not stopped before forward")
    require(forward.get("new_cluster_restarted") is True,
            "new cluster did not restart")
    require(forward.get("canary_order_id") == 10001,
            "forward canary ID mismatch")
    require(forward.get("canary_rows") == 1,
            "forward canary missing")
    validate_manifest(
        forward["manifest"], expected_rows=10001, expected_max_id=10001
    )
    require(forward.get("rollback_requires_reconciliation") is True,
            "forward boundary does not require reconciliation")

    for field, value in upgrade["risk"].items():
        require(value is False, f"upgrade risk claim true: {field}")
    require(
        upgrade["decision"]["production_approval"] is None
        and upgrade["decision"]["production_ch30_gate"] == "pending",
        "upgrade production decision drifted",
    )

    require(
        fixture_cleanup.get("schema")
        == "pg36-ch30-fixture-cleanup-v1",
        "fixture cleanup schema mismatch",
    )
    require(
        fixture_cleanup.get("run_id") == upgrade.get("run_id"),
        "fixture cleanup run ID mismatch",
    )
    require(fixture_cleanup.get("run_root_absent") is True,
            "fixture run root remains")
    require(fixture_cleanup.get("temporary_postmasters_stopped") is True,
            "temporary postmaster remains")
    require(fixture_cleanup.get("managed_host_identity_unchanged") is True,
            "managed host identity changed")
    require(fixture_cleanup.get("unrelated_processes_terminated") == 0,
            "unrelated process terminated")

    require(
        remote_cleanup.get("schema") == "pg36-ch30-remote-cleanup-v1",
        "remote cleanup schema mismatch",
    )
    require(remote_cleanup.get("run_id") == upgrade.get("run_id"),
            "remote cleanup run ID mismatch")
    require(remote_cleanup.get("remote_root_absent") is True,
            "remote root remains")
    require(remote_cleanup.get("active_postmasters") == [],
            "active temporary postmaster remains")
    require(remote_cleanup.get("remote_evidence_copied") is True,
            "remote evidence was not copied")
    require(remote_cleanup.get("unrelated_processes_terminated") == 0,
            "remote cleanup terminated unrelated process")

    if check_logs:
        remote_dir = documents["_remote_dir"]
        expected_logs = {
            "pg-upgrade-check-rejected.log":
                "old cluster uses data checksums but the new one does not",
            "pg-upgrade-check-passed.log": "*Clusters are compatible*",
            "pg-upgrade-copy.log": "Upgrade Complete",
            "source-checksums.log": "Checksum operation completed",
            "post-upgrade-analyze.log": "Generating",
        }
        for name, needle in expected_logs.items():
            path = remote_dir / name
            require(path.is_file(), f"log missing: {name}")
            text = path.read_text(errors="replace")
            require(needle in text, f"log evidence missing phrase: {name}")
        upgrade_log = (remote_dir / "pg-upgrade-copy.log").read_text(
            errors="replace"
        )
        for forbidden in ["--link", "--clone", "--swap", "--no-sync"]:
            require(forbidden not in upgrade_log,
                    f"forbidden upgrade mode in log: {forbidden}")


def apply_mutation(document: dict[str, Any], case: dict[str, Any]) -> None:
    path = case["path"]
    parent: Any = document
    for key in path[:-1]:
        parent = parent[key]
    final = path[-1]
    if case["operation"] == "set":
        parent[final] = copy.deepcopy(case.get("value"))
    elif case["operation"] == "delete":
        if isinstance(parent, list):
            del parent[int(final)]
        else:
            del parent[final]
    else:
        raise ValidationError(f"unknown mutation operation: {case}")


def run_declared_counterexamples(
    baseline: dict[str, dict[str, Any]],
    *,
    source_dir: Path,
    upstream_root: Path,
) -> list[dict[str, Any]]:
    results = []
    for case in baseline["negative"]["cases"]:
        mutated = copy.deepcopy(baseline)
        apply_mutation(mutated[case["document"]], case)
        try:
            validate_complete(
                mutated,
                source_dir=source_dir,
                upstream_root=upstream_root,
                check_logs=False,
            )
        except ValidationError as exc:
            results.append(
                {"id": case["id"], "status": "rejected", "reason": str(exc)}
            )
        else:
            raise ValidationError(
                f"declared counterexample was accepted: {case['id']}"
            )
    return results


LIVE_MUTATIONS = [
    ("fixture_cleanup", ["run_id"], "wrong-run"),
    ("remote_cleanup", ["run_id"], "wrong-run"),
    ("upgrade", ["upgrade", "extension_manifest_equal_before_amcheck"], False),
    ("upgrade", ["upgrade", "query_result_equal"], False),
    ("upgrade", ["upgrade", "amcheck_passed"], False),
    ("upgrade", ["upgrade", "post_upgrade_analyze_completed"], False),
    ("upgrade", ["risk", "pigsty_inventory_changed"], True),
    ("upgrade", ["risk", "patroni_configuration_changed"], True),
    ("upgrade", ["risk", "system_package_changed"], True),
    ("upgrade", ["risk", "external_listener_created"], True),
    ("upgrade", ["risk", "link_clone_swap_used"], True),
    ("upgrade", ["risk", "delete_old_cluster_script_run"], True),
    ("upgrade", ["rollback", "old_cluster_restarted"], False),
    ("upgrade", ["rollback", "manifest_equal"], False),
    ("upgrade", ["forward", "canary_rows"], 0),
    ("upgrade", ["forward", "manifest", "rows"], 10000),
    ("fixture_cleanup", ["temporary_postmasters_stopped"], False),
    ("fixture_cleanup", ["managed_host_identity_unchanged"], False),
    ("remote_cleanup", ["remote_evidence_copied"], False),
    ("remote_cleanup", ["active_postmasters"], [{"pid": 42}]),
]


def run_live_mutants(
    baseline: dict[str, dict[str, Any]],
    *,
    source_dir: Path,
    upstream_root: Path,
) -> list[dict[str, Any]]:
    results = []
    for index, (document, path, value) in enumerate(LIVE_MUTATIONS, start=1):
        mutated = copy.deepcopy(baseline)
        parent: Any = mutated[document]
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = copy.deepcopy(value)
        mutant_id = f"M{index:02d}"
        try:
            validate_complete(
                mutated,
                source_dir=source_dir,
                upstream_root=upstream_root,
                check_logs=False,
            )
        except ValidationError as exc:
            results.append(
                {"id": mutant_id, "status": "rejected", "reason": str(exc)}
            )
        else:
            raise ValidationError(f"live mutant was accepted: {mutant_id}")
    return results


def public_summary(
    preflight: dict[str, Any],
    upgrade: dict[str, Any],
    fixture_cleanup: dict[str, Any],
    remote_cleanup: dict[str, Any],
    declared_count: int,
    live_count: int,
) -> dict[str, Any]:
    baseline = upgrade["source"]["baseline"]["manifest"]
    upgraded = upgrade["upgrade"]["upgraded_before_writes"]["manifest"]
    return {
        "schema": "pg36-ch30-reference-run-v1",
        "release": "1.0-sandbox",
        "captured_at": upgrade["captured_at"],
        "run_id": upgrade["run_id"],
        "preflight_run_id": preflight["preflight_run_id"],
        "target": upgrade["target"],
        "environment": {
            "host_cluster":
                upgrade["environment"]["host_before"]["cluster_name"],
            "old_postgresql": upgrade["environment"]["old_postgresql"],
            "new_postgresql": upgrade["environment"]["new_postgresql"],
            "unix_socket_only":
                upgrade["environment"]["unix_socket_only"],
        },
        "fixture": {
            "initial_rows": baseline["rows"],
            "baseline_digest": baseline["ordered_digest_md5"],
            "upgraded_rows": upgraded["rows"],
            "upgraded_digest": upgraded["ordered_digest_md5"],
            "logical_manifest_equal":
                upgrade["upgrade"]["manifest_equal_before_writes"],
        },
        "collation_gate": {
            "injected_mismatch_observed":
                upgrade["collation_gate"]["state_before"]["mismatch"],
            "affected_indexes":
                upgrade["collation_gate"]["state_before"][
                    "affected_indexes"
                ],
            "release_before":
                upgrade["collation_gate"]["release_before"],
            "repair_order":
                upgrade["collation_gate"]["repair_order"],
            "mismatch_after":
                upgrade["collation_gate"]["state_after"]["mismatch"],
        },
        "incompatible_target": {
            "reason":
                upgrade["incompatible_target"]["expected_failure"],
            "check_returncode":
                upgrade["incompatible_target"]["check_returncode"],
            "rejected":
                upgrade["incompatible_target"][
                    "expected_failure_observed"
                ],
            "removed": upgrade["incompatible_target"]["target_removed"],
        },
        "upgrade": {
            "method": upgrade["upgrade"]["method"],
            "check_passed": upgrade["upgrade"]["check_passed"],
            "complete": upgrade["upgrade"]["complete"],
            "query_result_equal":
                upgrade["upgrade"]["query_result_equal"],
            "extension_manifest_equal":
                upgrade["upgrade"][
                    "extension_manifest_equal_before_amcheck"
                ],
            "amcheck_passed": upgrade["upgrade"]["amcheck_passed"],
            "post_upgrade_analyze_completed":
                upgrade["upgrade"]["post_upgrade_analyze_completed"],
        },
        "rollback": {
            "proven_before_target_writes":
                upgrade["rollback"]["proven_before_target_writes"],
            "old_cluster_restarted":
                upgrade["rollback"]["old_cluster_restarted"],
            "manifest_equal":
                upgrade["rollback"]["manifest_equal"],
            "target_only_writes_before_proof":
                upgrade["rollback"]["target_only_writes_before_proof"],
        },
        "forward": {
            "canary_order_id":
                upgrade["forward"]["canary_order_id"],
            "canary_rows": upgrade["forward"]["canary_rows"],
            "final_rows": upgrade["forward"]["manifest"]["rows"],
            "rollback_requires_reconciliation":
                upgrade["forward"]["rollback_requires_reconciliation"],
        },
        "cleanup": {
            "fixture_run_root_absent":
                fixture_cleanup["run_root_absent"],
            "temporary_postmasters_stopped":
                fixture_cleanup["temporary_postmasters_stopped"],
            "remote_root_absent":
                remote_cleanup["remote_root_absent"],
            "unrelated_processes_terminated":
                fixture_cleanup["unrelated_processes_terminated"]
                + remote_cleanup["unrelated_processes_terminated"],
        },
        "risk": upgrade["risk"],
        "validation": {
            "declared_counterexamples_rejected": declared_count,
            "live_evidence_mutants_rejected": live_count,
            "source_hash_bound": True,
            "private_bundle_required": True,
        },
        "decision": upgrade["decision"],
        "claims_not_made": [
            "this run upgraded a Pigsty-managed PostgreSQL data directory",
            "the sandbox duration predicts a production downtime window",
            "all third-party extensions and application drivers are compatible",
            "the sandbox result authorizes a production upgrade",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--upstream-root", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--negative-cases", required=True, type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--upgrade", type=Path)
    parser.add_argument("--fixture-cleanup", type=Path)
    parser.add_argument("--remote-cleanup", type=Path)
    parser.add_argument("--negative-output", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--public-summary", type=Path)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    upstream_root = args.upstream_root.resolve()
    requirements = load_json(args.requirements)
    contract = load_json(args.contract)
    negative = load_json(args.negative_cases)
    validate_static(requirements, contract, negative)

    complete_paths = [
        args.preflight,
        args.upgrade,
        args.fixture_cleanup,
        args.remote_cleanup,
    ]
    is_complete = all(path is not None for path in complete_paths)
    require(
        is_complete or not any(path is not None for path in complete_paths),
        "complete evidence paths must be supplied together",
    )

    declared_results: list[dict[str, Any]] = []
    live_results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema": "pg36-ch30-validation-report-v1",
        "captured_at": utc_now(),
        "mode": "lint",
        "status": "validation-ok",
        "declared_counterexamples": len(negative["cases"]),
        "live_evidence_mutants_rejected": 0,
        "source_files_hash_bound": len(SOURCE_FILES),
        "production_ch30_gate": "pending",
    }

    if is_complete:
        preflight = load_json(args.preflight)
        upgrade = load_json(args.upgrade)
        fixture_cleanup = load_json(args.fixture_cleanup)
        remote_cleanup = load_json(args.remote_cleanup)
        baseline: dict[str, Any] = {
            "requirements": requirements,
            "contract": contract,
            "negative": negative,
            "preflight": preflight,
            "upgrade": upgrade,
            "fixture_cleanup": fixture_cleanup,
            "remote_cleanup": remote_cleanup,
            "_remote_dir": args.upgrade.resolve().parent,
        }
        validate_complete(
            baseline,
            source_dir=source_dir,
            upstream_root=upstream_root,
            check_logs=True,
        )
        declared_results = run_declared_counterexamples(
            baseline,
            source_dir=source_dir,
            upstream_root=upstream_root,
        )
        live_results = run_live_mutants(
            baseline,
            source_dir=source_dir,
            upstream_root=upstream_root,
        )
        report.update(
            {
                "mode": "complete",
                "run_id": upgrade["run_id"],
                "preflight_run_id": preflight["preflight_run_id"],
                "declared_counterexamples_rejected":
                    len(declared_results),
                "live_evidence_mutants_rejected": len(live_results),
                "upgrade_method": upgrade["upgrade"]["method"],
                "rollback_proven":
                    upgrade["rollback"]["proven_before_target_writes"],
                "temporary_cleanup": "verified",
            }
        )
        if args.public_summary is None:
            raise ValidationError("public summary path required in complete mode")
        summary = public_summary(
            preflight,
            upgrade,
            fixture_cleanup,
            remote_cleanup,
            len(declared_results),
            len(live_results),
        )
        args.public_summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        args.public_summary.chmod(0o600)

    negative_report = {
        "schema": "pg36-ch30-negative-report-v1",
        "captured_at": utc_now(),
        "mode": report["mode"],
        "declared": declared_results
        if is_complete
        else [
            {"id": case["id"], "status": "schema-valid"}
            for case in negative["cases"]
        ],
        "live": live_results,
    }
    args.negative_output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.negative_output.write_text(
        json.dumps(negative_report, indent=2, sort_keys=True) + "\n"
    )
    args.negative_output.chmod(0o600)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "validation-ok",
                "mode": report["mode"],
                "declared_counterexamples_rejected":
                    len(declared_results),
                "live_mutants_rejected": len(live_results),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
