#!/usr/bin/env python3
"""Validate chapter 35 forensic contracts and evidence mutants."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

from common import LabError, read_json, sha256_file, utc_now, write_json


SOURCE_FILES = (
    "requirements.json",
    "classification-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "l3-rebuild-plan.json",
    "common.py",
    "capture.py",
    "exercise.py",
    "classify.py",
    "validate.py",
    "review.py",
    "task.sh",
)


def fail_if(failures: list[str], condition: bool, message: str) -> None:
    if condition:
        failures.append(message)


def index_rows(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    result = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("case_id"), str):
            result[row["case_id"]] = row
    return result


def topology_signature(value: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "member": row.get("member"),
            "host": row.get("host"),
            "role": row.get("role"),
            "state": row.get("state"),
            "timeline": row.get("timeline"),
        }
        for row in value.get("patroni", {}).get("members", [])
        if isinstance(row, dict)
    ]


def validate_static(
    failures: list[str],
    requirements: dict[str, Any],
    contract: dict[str, Any],
    negative: dict[str, Any],
    rebuild_plan: dict[str, Any],
    source_dir: Path,
) -> None:
    fail_if(
        failures,
        requirements.get("schema")
        != "pg36-ch35-forensics-requirements-v1",
        "requirements schema drifted",
    )
    target = requirements.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("managed_primary") != "pg-test-1"
        or target.get("observer") != "pg-test-3"
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False,
        "target or production boundary drifted",
    )
    exercise = requirements.get("exercise", {})
    fail_if(
        failures,
        exercise.get("scenario_count") != 2
        or exercise.get("random_order") is not True
        or exercise.get("blind_classification") is not True
        or exercise.get("wrong_action_execution") is not False
        or set(exercise.get("routes", []))
        != {
            "RESTORE_FROM_KNOWN_GOOD_COPY",
            "REINDEX_AND_REFRESH_COLLATION",
        }
        or exercise.get("unknown_route") != "STOP_AND_ESCALATE",
        "exercise design drifted",
    )
    disposable = requirements.get("disposable_cluster", {})
    fail_if(
        failures,
        disposable.get("root_prefix")
        != "/tmp/pg36-ch35-forensics"
        or disposable.get("host") != "pg-test-3"
        or disposable.get("port") != 55445
        or disposable.get("listen_addresses") != ""
        or disposable.get("data_checksums") is not True
        or disposable.get("allow_system_table_mods") is not True
        or disposable.get("exact_cleanup_required") is not True,
        "disposable cluster contract drifted",
    )
    fixture = requirements.get("fixture", {})
    fail_if(
        failures,
        fixture.get("row_count") != 12000
        or fixture.get("minimum_heap_blocks") != 8
        or fixture.get("business_invariants")
        != [
            "row_count",
            "sum_id",
            "sum_balance",
            "ordered_content_digest",
        ],
        "fixture or business invariant contract drifted",
    )
    physical = requirements.get("physical_case", {})
    fail_if(
        failures,
        physical.get("relation_kind") != "heap"
        or physical.get("offline_mutation_only") is not True
        or physical.get("mutated_block") != 2
        or physical.get("byte_offset_within_block") != 512
        or physical.get("minimum_bad_checksums") != 1
        or physical.get("online_scan_must_fail") is not True
        or physical.get("ignore_checksum_failure_permitted") is not False
        or physical.get("zero_damaged_pages_permitted") is not False
        or physical.get("recovery")
        != "fresh-working-copy-from-known-good-stopped-snapshot",
        "physical corruption contract drifted",
    )
    collation = requirements.get("collation_case", {})
    fail_if(
        failures,
        collation.get("provider") != "icu"
        or collation.get("metadata_mutation_only") is not True
        or collation.get("checksum_failure_expected") is not False
        or collation.get("amcheck_before_repair_expected") != "pass"
        or collation.get("repair_order")
        != [
            "reindex exact dependent index on working copy",
            "refresh exact collation version metadata",
        ]
        or collation.get(
            "original_evidence_copy_preserved_until_cleanup"
        )
        is not True,
        "collation scenario contract drifted",
    )
    risk = requirements.get("risk", {})
    false_keys = (
        "managed_postgresql_mutation_permitted",
        "managed_pgdata_mutation_permitted",
        "managed_service_change_permitted",
        "managed_route_change_permitted",
        "managed_reset_host_permitted",
        "unique_source_mutation_permitted",
        "manual_pg_wal_deletion_permitted",
        "ignore_checksum_failure_permitted",
        "zero_damaged_pages_permitted",
        "pg_resetwal_permitted",
    )
    fail_if(
        failures,
        risk.get("managed_capture") != "L0-read-only"
        or risk.get("exercise") != "L3-disposable-clones-only"
        or any(risk.get(key) is not False for key in false_keys),
        "risk boundary drifted",
    )
    acceptance = requirements.get("acceptance", {})
    fail_if(
        failures,
        acceptance.get("production_ch35_gate") != "pending"
        or acceptance.get("physical_case_must_not_be_repaired_in_place")
        is not True
        or acceptance.get("collation_case_must_reindex_before_refresh")
        is not True
        or acceptance.get("managed_topology_unchanged") is not True
        or acceptance.get("exact_cleanup_required") is not True,
        "acceptance boundary drifted",
    )
    fail_if(
        failures,
        len(requirements.get("exceptions", [])) != 5,
        "declared exception set drifted",
    )

    fail_if(
        failures,
        contract.get("schema")
        != "pg36-ch35-classification-contract-v1"
        or contract.get("required_packet_fields")
        != [
            "case_id",
            "observed_at",
            "checksum",
            "relation",
            "collation",
            "amcheck",
            "business",
        ],
        "classification contract schema or fields drifted",
    )
    routes = contract.get("routes", [])
    route_index = {
        row.get("route"): row
        for row in routes
        if isinstance(row, dict)
    }
    fail_if(
        failures,
        len(routes) != 2
        or set(route_index)
        != {
            "RESTORE_FROM_KNOWN_GOOD_COPY",
            "REINDEX_AND_REFRESH_COLLATION",
        }
        or "checksum.offline_bad_checksums >= 1"
        not in route_index.get(
            "RESTORE_FROM_KNOWN_GOOD_COPY",
            {},
        ).get("requires", [])
        or "refreshing collation metadata"
        not in route_index.get(
            "REINDEX_AND_REFRESH_COLLATION",
            {},
        ).get("safe_action", ""),
        "classification route contract drifted",
    )
    fail_if(
        failures,
        contract.get("unknown_route", {}).get("route")
        != "STOP_AND_ESCALATE"
        or contract.get("production_ch35_gate") != "pending",
        "unknown route or production gate drifted",
    )

    cases = negative.get("cases", [])
    fail_if(
        failures,
        negative.get("schema") != "pg36-ch35-negative-cases-v1"
        or not isinstance(cases, list)
        or len(cases) != 35
        or len(
            {
                row.get("id")
                for row in cases
                if isinstance(row, dict)
            }
        )
        != 35,
        "negative-case registry drifted",
    )
    fail_if(
        failures,
        rebuild_plan.get("schema")
        != "pg36-ch35-l3-rebuild-plan-v1"
        or rebuild_plan.get("name") != "reset:host"
        or rebuild_plan.get("destructive") is not True
        or rebuild_plan.get("executed") is not False
        or rebuild_plan.get("managed_reset_host_executed") is not False
        or rebuild_plan.get("production_ch35_gate") != "pending"
        or len(rebuild_plan.get("required_gates", [])) < 7,
        "L3 host rebuild decision contract drifted",
    )
    for name in SOURCE_FILES:
        path = source_dir / name
        fail_if(
            failures,
            not path.is_file() or path.is_symlink(),
            f"source file is missing or unsafe: {name}",
        )
    try:
        lab_contract = (source_dir / "lab-contract.md").read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        failures.append(f"cannot read lab contract: {exc}")
        lab_contract = ""
    for token in (
        "原始证据与操作副本",
        "不会",
        "`ignore_checksum_failure`",
        "`zero_damaged_pages`",
        "`pg_resetwal`",
        "`managed_reset_host_executed=false`",
        "`production_ch35_gate=pending`",
    ):
        fail_if(
            failures,
            token not in lab_contract,
            f"lab contract safety token missing: {token}",
        )


def validate_capture(
    failures: list[str],
    value: dict[str, Any],
    phase: str,
) -> None:
    fail_if(
        failures,
        value.get("schema") != "pg36-ch35-managed-capture-v1"
        or value.get("phase") != phase
        or value.get("target") != "pg36-l2-vagrant/pg-test"
        or value.get("mutation") != "none",
        f"{phase} capture identity drifted",
    )
    by_name = {
        row.get("member"): row
        for row in value.get("patroni", {}).get("members", [])
        if isinstance(row, dict)
    }
    fail_if(
        failures,
        set(by_name) != {"pg-test-1", "pg-test-2", "pg-test-3"}
        or by_name.get("pg-test-1", {}).get("role") != "primary"
        or by_name.get("pg-test-1", {}).get("state") != "running"
        or any(
            by_name.get(name, {}).get("role") != "replica"
            or by_name.get(name, {}).get("state") != "streaming"
            for name in ("pg-test-2", "pg-test-3")
        ),
        f"{phase} managed topology drifted",
    )
    postgres = value.get("postgres", {})
    fail_if(
        failures,
        postgres.get("in_recovery") is not False
        or postgres.get("cluster_name") != "pg-test"
        or postgres.get("chapter_fixture_sessions") != 0,
        f"{phase} managed SQL projection drifted",
    )
    fail_if(
        failures,
        value.get("forensic_host", {}).get("matching_roots") != [],
        f"{phase} forensic root was left behind",
    )


def validate_evidence(
    failures: list[str],
    bundle: dict[str, Any],
    requirements: dict[str, Any],
    contract: dict[str, Any],
    source_dir: Path,
) -> None:
    before = bundle["before"]
    after = bundle["after"]
    exercise = bundle["exercise"]
    packets = bundle["blind_packets"]
    hidden = bundle["hidden_answers"]
    classification = bundle["classification"]
    cleanup = bundle["cleanup"]
    manifest = bundle["run_manifest"]
    source_manifest = bundle["source_manifest"]

    validate_capture(failures, before, "before")
    validate_capture(failures, after, "after")
    fail_if(
        failures,
        topology_signature(before) != topology_signature(after)
        or before.get("postgres", {}).get("system_identifier")
        != after.get("postgres", {}).get("system_identifier")
        or before.get("postgres", {}).get("timeline")
        != after.get("postgres", {}).get("timeline"),
        "managed topology changed across forensic exercise",
    )

    run_id = exercise.get("run_id")
    fail_if(
        failures,
        exercise.get("schema") != "pg36-ch35-exercise-v1"
        or manifest.get("run_id") != run_id
        or manifest.get("production_ch35_gate") != "pending"
        or manifest.get("managed_reset_host_executed") is not False
        or exercise.get("target") != "pg36-l2-vagrant/pg-test"
        or exercise.get("host") != "pg-test-3",
        "exercise identity or production gate drifted",
    )
    disposable = exercise.get("disposable", {})
    fail_if(
        failures,
        disposable.get("port") != 55445
        or disposable.get("listen_addresses") != ""
        or disposable.get("unix_socket_only") is not True
        or disposable.get("data_checksums") is not True
        or disposable.get("managed_patroni_member") is not False
        or disposable.get("managed_dcs_member") is not False
        or disposable.get("managed_service_route") is not False,
        "disposable forensic boundary drifted",
    )
    engine = exercise.get("engine", {})
    fail_if(
        failures,
        engine.get("data_checksums") != "on"
        or engine.get("allow_system_table_mods") != "on"
        or engine.get("ignore_checksum_failure") != "off"
        or engine.get("zero_damaged_pages") != "off",
        "disposable engine guard drifted",
    )
    fixture = exercise.get("fixture", {})
    baseline = fixture.get("business_invariants", {})
    fail_if(
        failures,
        baseline.get("row_count") != 12000
        or not baseline.get("ordered_content_digest")
        or fixture.get("relation", {}).get("heap_blocks", 0) < 8
        or fixture.get("collation", {}).get("version_mismatch")
        is not False
        or fixture.get("amcheck", {}).get("structural_check_passed")
        is not True
        or fixture.get("source_checksum", {}).get(
            "offline_bad_checksums"
        )
        != 0,
        "clean source fixture did not validate",
    )
    known = exercise.get("known_good_snapshot", {})
    fail_if(
        failures,
        known.get("stopped_copy") is not True
        or known.get("unchanged") is not True
        or known.get("digest_before_cases")
        != known.get("digest_after_cases"),
        "known-good stopped snapshot changed",
    )
    order = exercise.get("scenario_order")
    fail_if(
        failures,
        not isinstance(order, list)
        or len(order) != 2
        or set(order)
        != {"PHYSICAL_HEAP_PAGE", "COLLATION_METADATA"}
        or manifest.get("scenario_order") != order,
        "random scenario set drifted",
    )

    cases = exercise.get("cases")
    case_index = index_rows(cases)
    packet_index = index_rows(packets)
    hidden_index = index_rows(hidden)
    result_index = index_rows(classification.get("results"))
    fail_if(
        failures,
        len(case_index) != 2
        or set(case_index) != set(packet_index)
        or set(case_index) != set(hidden_index)
        or set(case_index) != set(result_index),
        "case identity set drifted or duplicated",
    )
    fail_if(
        failures,
        exercise.get("blind_packets") != packets
        or exercise.get("hidden_answers") != hidden
        or manifest.get("blind_case_ids")
        != [row.get("case_id") for row in packets],
        "exercise projection artifacts drifted",
    )
    fail_if(
        failures,
        classification.get("schema")
        != "pg36-ch35-classification-v1"
        or classification.get("input_case_count") != 2
        or classification.get("hidden_answers_read") is not False,
        "blind classifier provenance drifted",
    )
    required = contract.get("required_packet_fields", [])
    forbidden = {"truth", "scenario", "expected_route", "hidden"}
    for case_id, packet in packet_index.items():
        fail_if(
            failures,
            any(key not in packet for key in required)
            or bool(forbidden.intersection(packet)),
            f"blind packet {case_id} is incomplete or leaks truth",
        )

    scenarios = {
        row.get("scenario"): row
        for row in cases
        if isinstance(row, dict)
    } if isinstance(cases, list) else {}
    fail_if(
        failures,
        set(scenarios) != {"PHYSICAL_HEAP_PAGE", "COLLATION_METADATA"},
        "one forensic scenario is missing",
    )

    physical = scenarios.get("PHYSICAL_HEAP_PAGE", {})
    physical_id = physical.get("case_id")
    physical_packet = packet_index.get(physical_id, {})
    physical_recovery = physical.get("recovery", {})
    fail_if(
        failures,
        hidden_index.get(physical_id, {}).get("expected_route")
        != "RESTORE_FROM_KNOWN_GOOD_COPY"
        or physical.get("expected_route")
        != "RESTORE_FROM_KNOWN_GOOD_COPY",
        "physical hidden answer drifted",
    )
    fail_if(
        failures,
        physical_packet.get("checksum", {}).get("enabled") is not True
        or physical_packet.get("checksum", {}).get(
            "offline_bad_checksums",
            0,
        )
        < 1
        or physical_packet.get("relation", {}).get("kind") != "heap"
        or physical_packet.get("collation", {}).get(
            "version_mismatch"
        )
        is not False
        or physical.get("observed", {}).get("online_scan", {}).get(
            "scan_succeeded"
        )
        is not False
        or physical.get("injection", {}).get(
            "server_running_during_mutation"
        )
        is not False,
        "physical damage evidence drifted",
    )
    fail_if(
        failures,
        physical_recovery.get("strategy")
        != "new-copy-from-known-good-stopped-snapshot"
        or physical_recovery.get("in_place_repair") is not False
        or physical_recovery.get("dangerous_gucs_used") is not False
        or physical_recovery.get("manual_pg_wal_file_deletion")
        is not False
        or physical_recovery.get("business_invariants_match")
        is not True
        or physical_recovery.get("business_invariants") != baseline
        or physical_recovery.get("amcheck", {}).get(
            "structural_check_passed"
        )
        is not True
        or physical_recovery.get("checksum", {}).get(
            "offline_bad_checksums"
        )
        != 0
        or physical.get("evidence_copy", {}).get(
            "preserved_until_final_cleanup"
        )
        is not True,
        "physical recovery or original evidence preservation drifted",
    )

    collation = scenarios.get("COLLATION_METADATA", {})
    collation_id = collation.get("case_id")
    collation_packet = packet_index.get(collation_id, {})
    collation_recovery = collation.get("recovery", {})
    fail_if(
        failures,
        hidden_index.get(collation_id, {}).get("expected_route")
        != "REINDEX_AND_REFRESH_COLLATION"
        or collation.get("expected_route")
        != "REINDEX_AND_REFRESH_COLLATION",
        "collation hidden answer drifted",
    )
    fail_if(
        failures,
        collation_packet.get("checksum", {}).get(
            "offline_bad_checksums"
        )
        != 0
        or collation_packet.get("relation", {}).get("kind")
        != "index-derived"
        or collation_packet.get("collation", {}).get(
            "version_mismatch"
        )
        is not True
        or collation_packet.get("amcheck", {}).get(
            "structural_check_passed"
        )
        is not True
        or collation_packet.get("business", {}).get(
            "current_validation_passed"
        )
        is not True,
        "collation-derived evidence drifted",
    )
    fail_if(
        failures,
        collation.get("injection", {}).get("metadata_only") is not True
        or collation.get("injection", {}).get("allow_system_table_mods")
        is not True
        or collation_recovery.get("strategy")
        != "separate-working-copy"
        or collation_recovery.get("reindex_before_refresh") is not True
        or [
            row.get("sequence")
            for row in collation_recovery.get("steps", [])
        ]
        != [1, 2]
        or collation_recovery.get("collation", {}).get(
            "version_mismatch"
        )
        is not False
        or collation_recovery.get("amcheck", {}).get(
            "structural_check_passed"
        )
        is not True
        or collation_recovery.get("business_invariants_match")
        is not True
        or collation_recovery.get("business_invariants") != baseline
        or collation_recovery.get("checksum", {}).get(
            "offline_bad_checksums"
        )
        != 0
        or collation.get("evidence_copy", {}).get(
            "preserved_until_final_cleanup"
        )
        is not True,
        "collation working-copy repair drifted",
    )

    for case_id, answer in hidden_index.items():
        result = result_index.get(case_id, {})
        expected = answer.get("expected_route")
        fail_if(
            failures,
            result.get("route") != expected
            or len(result.get("evidence", [])) != 5,
            f"classification is wrong or unsupported for {case_id}",
        )
        if expected == "RESTORE_FROM_KNOWN_GOOD_COPY":
            fail_if(
                failures,
                result.get("physical_predicate") is not True
                or result.get("derived_predicate") is not False,
                "physical classification predicates are ambiguous",
            )
        if expected == "REINDEX_AND_REFRESH_COLLATION":
            fail_if(
                failures,
                result.get("physical_predicate") is not False
                or result.get("derived_predicate") is not True,
                "derived classification predicates are ambiguous",
            )

    safety = exercise.get("safety", {})
    false_keys = (
        "managed_postgresql_mutated",
        "managed_pgdata_mutated",
        "managed_service_changed",
        "managed_route_changed",
        "managed_reset_host_executed",
        "unique_source_mutated",
        "manual_pg_wal_file_deletion",
        "ignore_checksum_failure_used",
        "zero_damaged_pages_used",
        "pg_resetwal_used",
        "wrong_action_executed",
        "production_data_touched",
        "production_traffic_touched",
    )
    fail_if(
        failures,
        any(safety.get(key) is not False for key in false_keys)
        or safety.get("external_dispatch_count") != 0,
        "forensic safety boundary drifted",
    )
    fail_if(
        failures,
        cleanup != exercise.get("cleanup")
        or cleanup.get("root_exists_after") is not False
        or cleanup.get("marker_matched") is not True
        or cleanup.get("all_postmasters_stopped_before_cleanup")
        is not True,
        "exact forensic cleanup is unproved",
    )

    rows = source_manifest.get("files", [])
    source_index = {
        row.get("path"): row
        for row in rows
        if isinstance(row, dict)
    }
    fail_if(
        failures,
        source_manifest.get("schema")
        != "pg36-ch35-source-manifest-v1"
        or set(source_index) != set(SOURCE_FILES)
        or len(rows) != len(SOURCE_FILES),
        "source manifest file set drifted",
    )
    for name in SOURCE_FILES:
        path = source_dir / name
        row = source_index.get(name, {})
        fail_if(
            failures,
            not path.is_file()
            or row.get("sha256") != sha256_file(path)
            or row.get("bytes") != path.stat().st_size,
            f"source hash binding drifted: {name}",
        )


def load_bundle(root: Path) -> dict[str, Any]:
    exercise = root / "exercise"
    return {
        "before": read_json(root / "before.json"),
        "after": read_json(root / "after.json"),
        "classification": read_json(root / "classification.json"),
        "exercise": read_json(exercise / "exercise-evidence.json"),
        "blind_packets": read_json(exercise / "blind-packets.json"),
        "hidden_answers": read_json(exercise / "hidden-answers.json"),
        "cleanup": read_json(exercise / "cleanup.json"),
        "run_manifest": read_json(exercise / "run-manifest.json"),
        "source_manifest": read_json(exercise / "source-manifest.json"),
    }


def scenario(bundle: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        row
        for row in bundle["exercise"]["cases"]
        if row.get("scenario") == name
    )


def packet_copies(
    bundle: dict[str, Any],
    case_id: str,
) -> list[dict[str, Any]]:
    rows = []
    for collection in (
        bundle["blind_packets"],
        bundle["exercise"]["blind_packets"],
    ):
        rows.extend(
            row for row in collection if row.get("case_id") == case_id
        )
    rows.append(
        next(
            row["blind_packet"]
            for row in bundle["exercise"]["cases"]
            if row.get("case_id") == case_id
        )
    )
    return rows


def mutate(bundle: dict[str, Any], mutation: str) -> None:
    requirements = bundle["requirements"]
    contract = bundle["contract"]
    risk = requirements["risk"]
    if mutation == "requirements.production-data=true":
        requirements["target"]["production_data_permitted"] = True
    elif mutation == "requirements.production-traffic=true":
        requirements["target"]["production_traffic_permitted"] = True
    elif mutation == "requirements.managed-pgdata=true":
        risk["managed_pgdata_mutation_permitted"] = True
    elif mutation == "requirements.managed-reset-host=true":
        risk["managed_reset_host_permitted"] = True
    elif mutation == "requirements.unique-source=true":
        risk["unique_source_mutation_permitted"] = True
    elif mutation == "requirements.wal-delete=true":
        risk["manual_pg_wal_deletion_permitted"] = True
    elif mutation == "requirements.ignore-checksum=true":
        risk["ignore_checksum_failure_permitted"] = True
    elif mutation == "requirements.zero-page=true":
        risk["zero_damaged_pages_permitted"] = True
    elif mutation == "requirements.resetwal=true":
        risk["pg_resetwal_permitted"] = True
    elif mutation == "requirements.scenarios=1":
        requirements["exercise"]["scenario_count"] = 1
    elif mutation == "contract.remove-route":
        contract["routes"].pop()
    elif mutation == "contract.remove-unknown":
        contract.pop("unknown_route", None)
    elif mutation == "contract.bad-checksums=0":
        contract["routes"][0]["requires"][1] = (
            "checksum.offline_bad_checksums >= 0"
        )
    elif mutation == "contract.allow-refresh-only":
        contract["routes"][1]["safe_action"] = (
            "refresh collation metadata only"
        )
    elif mutation == "blind.add-truth":
        bundle["blind_packets"][0]["truth"] = "PHYSICAL_HEAP_PAGE"
    elif mutation == "blind.add-expected-route":
        bundle["blind_packets"][0]["expected_route"] = "anything"
    elif mutation == "blind.remove-checksum":
        bundle["blind_packets"][0].pop("checksum", None)
    elif mutation == "classification.duplicate-case":
        rows = bundle["classification"]["results"]
        rows[1]["case_id"] = rows[0]["case_id"]
    elif mutation.startswith("classification."):
        if mutation == "classification.remove-evidence":
            bundle["classification"]["results"][0]["evidence"] = []
        else:
            case = scenario(
                bundle,
                (
                    "PHYSICAL_HEAP_PAGE"
                    if mutation == "classification.physical=collation"
                    else "COLLATION_METADATA"
                ),
            )
            index_rows(bundle["classification"]["results"])[
                case["case_id"]
            ]["route"] = (
                "REINDEX_AND_REFRESH_COLLATION"
                if "physical=" in mutation
                else "RESTORE_FROM_KNOWN_GOOD_COPY"
            )
    elif mutation.startswith("evidence.physical."):
        case = scenario(bundle, "PHYSICAL_HEAP_PAGE")
        copies = packet_copies(bundle, case["case_id"])
        if mutation == "evidence.physical.enabled=false":
            for row in copies:
                row["checksum"]["enabled"] = False
        elif mutation == "evidence.physical.bad=0":
            for row in copies:
                row["checksum"]["offline_bad_checksums"] = 0
        elif mutation == "evidence.physical.kind=index":
            for row in copies:
                row["relation"]["kind"] = "index-derived"
        elif mutation == "evidence.physical.scan=true":
            case["observed"]["online_scan"]["scan_succeeded"] = True
        elif mutation == "evidence.physical.in-place=true":
            case["recovery"]["in_place_repair"] = True
        elif mutation == "evidence.physical.row-count=1":
            case["recovery"]["business_invariants"]["row_count"] = 1
        else:
            raise LabError(f"unknown physical mutation: {mutation}")
    elif mutation.startswith("evidence.collation."):
        case = scenario(bundle, "COLLATION_METADATA")
        copies = packet_copies(bundle, case["case_id"])
        if mutation == "evidence.collation.bad=1":
            for row in copies:
                row["checksum"]["offline_bad_checksums"] = 1
        elif mutation == "evidence.collation.mismatch=false":
            for row in copies:
                row["collation"]["version_mismatch"] = False
        elif mutation == "evidence.collation.amcheck=false":
            for row in copies:
                row["amcheck"]["structural_check_passed"] = False
        elif mutation == "evidence.collation.order=refresh-first":
            case["recovery"]["steps"].reverse()
            case["recovery"]["reindex_before_refresh"] = False
        elif mutation == "evidence.collation.digest=bad":
            case["recovery"]["business_invariants"][
                "ordered_content_digest"
            ] = "bad"
        else:
            raise LabError(f"unknown collation mutation: {mutation}")
    elif mutation == "evidence.original-preserved=false":
        scenario(bundle, "PHYSICAL_HEAP_PAGE")["evidence_copy"][
            "preserved_until_final_cleanup"
        ] = False
    elif mutation == "evidence.cleanup.root-left=true":
        bundle["cleanup"]["root_exists_after"] = True
        bundle["exercise"]["cleanup"]["root_exists_after"] = True
    elif mutation == "evidence.production-gate=approved":
        bundle["run_manifest"]["production_ch35_gate"] = "approved"
    else:
        raise LabError(f"unknown mutation: {mutation}")


def build_public(
    bundle: dict[str, Any],
    counterexamples: int,
) -> dict[str, Any]:
    exercise = bundle["exercise"]
    physical = scenario(bundle, "PHYSICAL_HEAP_PAGE")
    collation = scenario(bundle, "COLLATION_METADATA")
    routes = {
        row["case_id"]: row["route"]
        for row in bundle["classification"]["results"]
    }
    return {
        "schema": "pg36-ch35-public-summary-v1",
        "status": "completed",
        "run_id": exercise["run_id"],
        "observed_at": exercise["finished_at"],
        "target": exercise["target"],
        "experiment": {
            "postgresql_version": exercise["engine"]["server_version"],
            "host": exercise["host"],
            "randomized_order": exercise["scenario_order"],
            "blind_classification": True,
            "unix_socket_only": True,
            "fixture_rows": exercise["fixture"][
                "business_invariants"
            ]["row_count"],
            "fixture_digest": exercise["fixture"][
                "business_invariants"
            ]["ordered_content_digest"],
        },
        "physical_page": {
            "route": routes[physical["case_id"]],
            "relation_kind": physical["blind_packet"]["relation"]["kind"],
            "mutated_block": physical["injection"]["block"],
            "bytes_changed": physical["injection"]["bytes_changed"],
            "offline_bad_checksums": physical["observed"]["checksum"][
                "offline_bad_checksums"
            ],
            "online_scan_succeeded": physical["observed"][
                "online_scan"
            ]["scan_succeeded"],
            "online_scan_sqlstate": physical["observed"][
                "online_scan"
            ]["sqlstate"],
            "in_place_repair": physical["recovery"]["in_place_repair"],
            "recovered_invariants_match": physical["recovery"][
                "business_invariants_match"
            ],
            "recovered_bad_checksums": physical["recovery"][
                "checksum"
            ]["offline_bad_checksums"],
            "original_case_preserved": physical["evidence_copy"][
                "preserved_until_final_cleanup"
            ],
        },
        "collation_derived": {
            "route": routes[collation["case_id"]],
            "offline_bad_checksums": collation["observed"]["checksum"][
                "offline_bad_checksums"
            ],
            "structural_amcheck_before": collation["observed"][
                "amcheck"
            ]["structural_check_passed"],
            "stored_version_injected": collation["injection"]["after"][
                "stored_version"
            ],
            "actual_version": collation["injection"]["after"][
                "actual_version"
            ],
            "reindex_before_refresh": collation["recovery"][
                "reindex_before_refresh"
            ],
            "repair_elapsed_ms": collation["recovery"]["elapsed_ms"],
            "version_mismatch_after": collation["recovery"][
                "collation"
            ]["version_mismatch"],
            "recovered_invariants_match": collation["recovery"][
                "business_invariants_match"
            ],
            "original_case_preserved": collation["evidence_copy"][
                "preserved_until_final_cleanup"
            ],
        },
        "managed_cluster": {
            "topology_unchanged": (
                topology_signature(bundle["before"])
                == topology_signature(bundle["after"])
            ),
            "system_identifier_unchanged": (
                bundle["before"]["postgres"]["system_identifier"]
                == bundle["after"]["postgres"]["system_identifier"]
            ),
            "timeline_unchanged": (
                bundle["before"]["postgres"]["timeline"]
                == bundle["after"]["postgres"]["timeline"]
            ),
            "mutations": 0,
        },
        "safety": {
            **exercise["safety"],
            "known_good_snapshot_unchanged": exercise[
                "known_good_snapshot"
            ]["unchanged"],
            "exact_root_removed": (
                exercise["cleanup"]["root_exists_after"] is False
            ),
        },
        "evidence": {
            "declared_counterexamples": counterexamples,
            "live_mutants_rejected": counterexamples,
            "source_files_hash_bound": len(SOURCE_FILES),
        },
        "decision": {
            "production_approval": None,
            "production_ch35_gate": "pending",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--negative-output", type=Path)
    parser.add_argument("--public-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        contract = read_json(
            args.source_dir / "classification-contract.json"
        )
        negative = read_json(args.negative_cases)
        rebuild_plan = read_json(
            args.source_dir / "l3-rebuild-plan.json"
        )
        failures: list[str] = []
        validate_static(
            failures,
            requirements,
            contract,
            negative,
            rebuild_plan,
            args.source_dir,
        )
        if args.evidence_dir is None:
            write_json(
                args.output,
                {
                    "schema": "pg36-ch35-validation-report-v1",
                    "validated_at": utc_now(),
                    "mode": "contracts-only",
                    "passed": not failures,
                    "failure_count": len(failures),
                    "failures": failures,
                    "declared_counterexamples": len(
                        negative.get("cases", [])
                    ),
                    "source_files_hash_bound": len(SOURCE_FILES),
                    "production_ch35_gate": "pending",
                },
            )
            if failures:
                raise LabError("; ".join(failures))
            return 0

        bundle = load_bundle(args.evidence_dir)
        bundle["requirements"] = requirements
        bundle["contract"] = contract
        bundle["negative"] = negative
        bundle["rebuild_plan"] = rebuild_plan
        validate_evidence(
            failures,
            bundle,
            requirements,
            contract,
            args.source_dir,
        )
        mutant_results = []
        for row in negative["cases"]:
            candidate = copy.deepcopy(bundle)
            mutate(candidate, row["mutation"])
            mutant_failures: list[str] = []
            validate_static(
                mutant_failures,
                candidate["requirements"],
                candidate["contract"],
                candidate["negative"],
                candidate["rebuild_plan"],
                args.source_dir,
            )
            validate_evidence(
                mutant_failures,
                candidate,
                candidate["requirements"],
                candidate["contract"],
                args.source_dir,
            )
            mutant_results.append(
                {
                    "id": row["id"],
                    "mutation": row["mutation"],
                    "rejected": bool(mutant_failures),
                    "first_failure": (
                        mutant_failures[0] if mutant_failures else None
                    ),
                }
            )
        accepted = [
            row["id"]
            for row in mutant_results
            if row["rejected"] is not True
        ]
        if accepted:
            failures.append("live mutants accepted: " + ", ".join(accepted))
        run_id = bundle["exercise"].get("run_id")
        write_json(
            args.output,
            {
                "schema": "pg36-ch35-validation-report-v1",
                "validated_at": utc_now(),
                "mode": "complete-evidence",
                "run_id": run_id,
                "passed": not failures,
                "failure_count": len(failures),
                "failures": failures,
                "declared_counterexamples": len(negative["cases"]),
                "live_evidence_mutants": len(mutant_results),
                "live_evidence_mutants_rejected": sum(
                    1 for row in mutant_results if row["rejected"]
                ),
                "source_files_hash_bound": len(SOURCE_FILES),
                "production_ch35_gate": "pending",
            },
        )
        if args.negative_output is None or args.public_summary is None:
            raise LabError(
                "complete validation requires negative and public outputs"
            )
        write_json(
            args.negative_output,
            {
                "schema": "pg36-ch35-negative-report-v1",
                "validated_at": utc_now(),
                "run_id": run_id,
                "passed": not accepted,
                "case_count": len(mutant_results),
                "rejected_count": sum(
                    1 for row in mutant_results if row["rejected"]
                ),
                "live_mutant_count": len(mutant_results),
                "live_mutants_rejected": sum(
                    1 for row in mutant_results if row["rejected"]
                ),
                "results": mutant_results,
            },
        )
        if not failures:
            write_json(
                args.public_summary,
                build_public(bundle, len(mutant_results)),
            )
        if failures:
            raise LabError("; ".join(failures))
    except (
        KeyError,
        IndexError,
        StopIteration,
        TypeError,
        OSError,
        LabError,
    ) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
