#!/usr/bin/env python3
"""Validate chapter 34 contracts, evidence, and live adversarial mutants."""

from __future__ import annotations

import argparse
import copy
import json
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


def rows_by_case(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = row.get("case_id")
        if isinstance(case_id, str):
            result[case_id] = row
    return result


def managed_topology_signature(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows = value.get("patroni", {}).get("members", [])
    return [
        {
            "member": row.get("member"),
            "host": row.get("host"),
            "role": row.get("role"),
            "state": row.get("state"),
            "timeline": row.get("timeline"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def validate_static(
    failures: list[str],
    requirements: dict[str, Any],
    contract: dict[str, Any],
    negative: dict[str, Any],
    source_dir: Path,
) -> None:
    fail_if(
        failures,
        requirements.get("schema")
        != "pg36-ch34-overload-requirements-v1",
        "requirements schema drifted",
    )
    target = requirements.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("cluster") != "pg-test"
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
        or exercise.get("common_alert")
        != "postgresql-resource-headroom-at-risk"
        or set(exercise.get("routes", []))
        != {
            "RELIEVE_FLOW_PRESSURE",
            "PRESERVE_RETENTION_EVIDENCE",
        },
        "exercise design drifted",
    )
    disposable = requirements.get("disposable_cluster", {})
    fail_if(
        failures,
        disposable.get("host") != "pg-test-3"
        or disposable.get("root_prefix")
        != "/tmp/pg36-ch34-overload"
        or disposable.get("port") != 55444
        or disposable.get("listen_addresses") != ""
        or disposable.get("max_connections") != 24
        or disposable.get("superuser_reserved_connections") != 3
        or disposable.get("max_replication_slots") != 4
        or disposable.get("max_slot_wal_keep_size") != "-1"
        or disposable.get("data_checksums") is not True
        or disposable.get("exact_cleanup_required") is not True,
        "disposable cluster boundary drifted",
    )
    flow = requirements.get("flow_scenario", {})
    fail_if(
        failures,
        flow.get("attempted_clients") != 30
        or flow.get("statement_seconds") != 20
        or flow.get("minimum_observed_sessions") != 18
        or flow.get("minimum_connection_rejections") != 1
        or flow.get("minimum_lock_waiters") != 1
        or flow.get("mitigation")
        != "pg_cancel_backend-exact-application-name"
        or flow.get("post_mitigation_sessions") != 0,
        "flow scenario contract drifted",
    )
    retention = requirements.get("retention_scenario", {})
    fail_if(
        failures,
        retention.get("slot_kind") != "physical"
        or retention.get("slot_active") is not False
        or retention.get("minimum_retained_wal_bytes") != 33_554_432
        or retention.get("maximum_generated_wal_bytes") != 134_217_728
        or retention.get("mitigation")
        != "drop-exact-owned-disposable-slot-after-evidence"
        or retention.get("manual_pg_wal_file_deletion") is not False
        or retention.get("post_mitigation_slots") != 0,
        "retention scenario contract drifted",
    )
    risk = requirements.get("risk", {})
    forbidden_true = (
        "managed_postgresql_mutation_permitted",
        "managed_connection_storm_permitted",
        "managed_replication_slot_permitted",
        "managed_query_cancel_permitted",
        "managed_service_change_permitted",
        "managed_route_change_permitted",
        "host_cache_drop_permitted",
        "oom_injection_permitted",
        "manual_pg_wal_deletion_permitted",
    )
    fail_if(
        failures,
        risk.get("managed_capture") != "L0-read-only"
        or risk.get("exercise")
        != "L2-disposable-local-cluster-only"
        or any(risk.get(key) is not False for key in forbidden_true),
        "risk boundary drifted",
    )
    acceptance = requirements.get("acceptance", {})
    fail_if(
        failures,
        acceptance.get("production_ch34_gate") != "pending"
        or acceptance.get("wrong_route_must_be_rejected") is not True
        or acceptance.get("managed_topology_unchanged") is not True
        or acceptance.get("exact_cleanup_required") is not True,
        "acceptance gate drifted",
    )
    fail_if(
        failures,
        len(requirements.get("exceptions", [])) != 4,
        "declared exception set drifted",
    )

    fail_if(
        failures,
        contract.get("schema")
        != "pg36-ch34-classification-contract-v1"
        or contract.get("common_alert") != exercise.get("common_alert"),
        "classification contract schema or alert drifted",
    )
    required_fields = contract.get("required_packet_fields", [])
    fail_if(
        failures,
        required_fields
        != [
            "case_id",
            "observed_at",
            "connection",
            "retention",
            "engine",
            "filesystem",
        ],
        "blind packet field contract drifted",
    )
    routes = contract.get("routes", [])
    route_index = {
        row.get("route"): row for row in routes if isinstance(row, dict)
    }
    flow_route = route_index.get("RELIEVE_FLOW_PRESSURE", {})
    retention_route = route_index.get(
        "PRESERVE_RETENTION_EVIDENCE",
        {},
    )
    fail_if(
        failures,
        len(routes) != 2
        or set(route_index)
        != {
            "RELIEVE_FLOW_PRESSURE",
            "PRESERVE_RETENTION_EVIDENCE",
        }
        or "connection.observed_sessions >= 18"
        not in flow_route.get("requires", [])
        or "retention.retained_wal_bytes >= 33554432"
        not in retention_route.get("requires", [])
        or "delete files from pg_wal"
        not in retention_route.get("forbidden_shortcut", ""),
        "classification route predicates drifted",
    )
    unknown = contract.get("unknown_route", {})
    fail_if(
        failures,
        unknown.get("route") != "STOP_AND_INVESTIGATE"
        or "stop destructive cleanup" not in unknown.get("actions", []),
        "unknown classification route drifted",
    )
    fail_if(
        failures,
        contract.get("production_ch34_gate") != "pending",
        "classification production gate opened",
    )

    cases = negative.get("cases", [])
    fail_if(
        failures,
        negative.get("schema") != "pg36-ch34-negative-cases-v1"
        or not isinstance(cases, list)
        or len(cases) != 34
        or len(
            {
                row.get("id")
                for row in cases
                if isinstance(row, dict)
            }
        )
        != 34
        or any(
            not isinstance(row, dict)
            or not row.get("id")
            or not row.get("mutation")
            for row in cases
        ),
        "negative-case registry drifted",
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
        "同症状、双根因",
        "不会在受管集群上制造连接风暴",
        "实验不会手工删除",
        "`pg_wal` 文件",
        "STOP_AND_INVESTIGATE",
        "production_ch34_gate=pending",
    ):
        fail_if(
            failures,
            token not in lab_contract,
            f"lab contract safety token missing: {token}",
        )


def validate_managed_capture(
    failures: list[str],
    value: dict[str, Any],
    phase: str,
    label: str,
) -> None:
    fail_if(
        failures,
        value.get("schema") != "pg36-ch34-managed-capture-v1"
        or value.get("phase") != phase
        or value.get("target") != "pg36-l2-vagrant/pg-test"
        or value.get("mutation") != "none",
        f"{label} managed capture identity drifted",
    )
    members = value.get("patroni", {}).get("members", [])
    by_name = rows_by_case(
        [
            {**row, "case_id": row.get("member")}
            for row in members
            if isinstance(row, dict)
        ]
    )
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
        f"{label} managed topology drifted",
    )
    postgres = value.get("postgres", {})
    fail_if(
        failures,
        postgres.get("in_recovery") is not False
        or postgres.get("cluster_name") != "pg-test"
        or postgres.get("activity", {}).get("chapter_fixture_sessions")
        != 0,
        f"{label} managed SQL projection drifted",
    )
    fail_if(
        failures,
        value.get("disposable_host", {}).get("matching_roots") != [],
        f"{label} disposable root was left behind",
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

    validate_managed_capture(failures, before, "before", "before")
    validate_managed_capture(failures, after, "after", "after")
    fail_if(
        failures,
        before.get("postgres", {}).get("system_identifier")
        != after.get("postgres", {}).get("system_identifier")
        or before.get("postgres", {}).get("timeline")
        != after.get("postgres", {}).get("timeline")
        or managed_topology_signature(before)
        != managed_topology_signature(after),
        "managed topology changed across the exercise",
    )

    run_id = exercise.get("run_id")
    fail_if(
        failures,
        exercise.get("schema") != "pg36-ch34-exercise-v1"
        or not isinstance(run_id, str)
        or manifest.get("run_id") != run_id
        or manifest.get("production_ch34_gate") != "pending"
        or exercise.get("target") != "pg36-l2-vagrant/pg-test"
        or exercise.get("host") != "pg-test-3"
        or exercise.get("common_alert")
        != contract.get("common_alert"),
        "exercise identity binding drifted",
    )
    disposable = exercise.get("disposable", {})
    fail_if(
        failures,
        disposable.get("port") != 55444
        or disposable.get("listen_addresses") != ""
        or disposable.get("unix_socket_only") is not True
        or disposable.get("data_checksums") is not True
        or disposable.get("managed_patroni_member") is not False
        or disposable.get("managed_dcs_member") is not False
        or disposable.get("managed_service_route") is not False,
        "disposable engine boundary drifted",
    )
    order = exercise.get("scenario_order")
    fail_if(
        failures,
        not isinstance(order, list)
        or len(order) != 2
        or set(order) != {"FLOW", "RETENTION"}
        or manifest.get("scenario_order") != order,
        "randomized scenario set drifted",
    )
    cases = exercise.get("cases")
    case_index = rows_by_case(cases)
    packet_index = rows_by_case(packets)
    hidden_index = rows_by_case(hidden)
    result_index = rows_by_case(classification.get("results"))
    fail_if(
        failures,
        len(case_index) != 2
        or len(packet_index) != 2
        or len(hidden_index) != 2
        or len(result_index) != 2
        or set(case_index)
        != set(packet_index)
        or set(case_index)
        != set(hidden_index)
        or set(case_index)
        != set(result_index),
        "case identity set drifted or duplicated",
    )
    fail_if(
        failures,
        exercise.get("blind_packets") != packets
        or exercise.get("hidden_answers") != hidden
        or manifest.get("blind_case_ids")
        != [row.get("case_id") for row in packets],
        "exercise artifacts are not exact projections",
    )
    fail_if(
        failures,
        classification.get("schema")
        != "pg36-ch34-classification-v1"
        or classification.get("input_case_count") != 2
        or classification.get("hidden_answers_read") is not False
        or classification.get("common_alert")
        != contract.get("common_alert"),
        "blind classifier provenance drifted",
    )
    required_fields = contract.get("required_packet_fields", [])
    forbidden = {"truth", "scenario", "expected_route", "hidden"}
    for case_id, packet in packet_index.items():
        fail_if(
            failures,
            any(key not in packet for key in required_fields)
            or bool(forbidden.intersection(packet)),
            f"blind packet {case_id} is incomplete or leaks truth",
        )
        fail_if(
            failures,
            packet.get("alert") != contract.get("common_alert"),
            f"blind packet {case_id} alert drifted",
        )

    scenario_index = {
        row.get("scenario"): row
        for row in cases
        if isinstance(row, dict)
    } if isinstance(cases, list) else {}
    fail_if(
        failures,
        set(scenario_index) != {"FLOW", "RETENTION"},
        "exercise does not contain one case of each root cause",
    )

    flow = scenario_index.get("FLOW", {})
    flow_id = flow.get("case_id")
    flow_packet = packet_index.get(flow_id, {})
    flow_connection = flow_packet.get("connection", {})
    flow_retention = flow_packet.get("retention", {})
    flow_observed = flow.get("observed", {}).get("connection", {})
    flow_mitigation = flow.get("mitigation", {})
    flow_recovery = flow.get("recovery", {})
    flow_req = requirements.get("flow_scenario", {})
    fail_if(
        failures,
        hidden_index.get(flow_id, {}).get("scenario") != "FLOW"
        or hidden_index.get(flow_id, {}).get("expected_route")
        != "RELIEVE_FLOW_PRESSURE"
        or flow.get("expected_route") != "RELIEVE_FLOW_PRESSURE",
        "flow hidden answer drifted",
    )
    fail_if(
        failures,
        flow_connection.get("attempted_clients")
        != flow_req.get("attempted_clients")
        or flow_connection.get("observed_sessions", -1)
        < flow_req.get("minimum_observed_sessions", 18)
        or flow_connection.get("connection_rejections", -1)
        < flow_req.get("minimum_connection_rejections", 1)
        or flow_connection.get("lock_waiters", -1)
        < flow_req.get("minimum_lock_waiters", 1)
        or flow_retention.get("inactive_physical_slots") != 0
        or flow_observed.get("observed_sessions")
        != flow_connection.get("observed_sessions")
        or flow_observed.get("connection_rejections")
        != flow_connection.get("connection_rejections")
        or flow_observed.get("lock_waiters")
        != flow_connection.get("lock_waiters"),
        "flow pressure evidence does not meet its lower bounds",
    )
    fail_if(
        failures,
        flow_mitigation.get("action") != "pg_cancel_backend"
        or flow_mitigation.get("scope")
        != "exact-application-name-prefix"
        or not str(flow_mitigation.get("application_prefix", "")).startswith(
            "pg36-ch34-flow-"
        )
        or flow_mitigation.get("broad_cancel_used") is not False
        or flow_mitigation.get("max_connections_changed") is not False
        or flow_recovery.get("post_fixture_sessions") != 0
        or flow_recovery.get("post_probe") != 1
        or flow_recovery.get("post_inactive_physical_slots") != 0,
        "flow mitigation scope or recovery drifted",
    )

    retention = scenario_index.get("RETENTION", {})
    retention_id = retention.get("case_id")
    retention_packet = packet_index.get(retention_id, {})
    retention_connection = retention_packet.get("connection", {})
    retention_signal = retention_packet.get("retention", {})
    retention_observed = retention.get("observed", {})
    slot = retention_observed.get("slot", {})
    slot_rows = slot.get("rows", []) if isinstance(slot, dict) else []
    slot_row = slot_rows[0] if len(slot_rows) == 1 else {}
    retention_mitigation = retention.get("mitigation", {})
    retention_recovery = retention.get("recovery", {})
    retention_req = requirements.get("retention_scenario", {})
    retained_bytes = retention_signal.get("retained_wal_bytes", -1)
    fail_if(
        failures,
        hidden_index.get(retention_id, {}).get("scenario") != "RETENTION"
        or hidden_index.get(retention_id, {}).get("expected_route")
        != "PRESERVE_RETENTION_EVIDENCE"
        or retention.get("expected_route")
        != "PRESERVE_RETENTION_EVIDENCE",
        "retention hidden answer drifted",
    )
    fail_if(
        failures,
        retention_signal.get("inactive_physical_slots") != 1
        or not isinstance(retained_bytes, int)
        or retained_bytes
        < retention_req.get("minimum_retained_wal_bytes", 33_554_432)
        or retained_bytes
        > retention_req.get("maximum_generated_wal_bytes", 134_217_728)
        or retention_connection.get("connection_rejections") != 0
        or slot.get("inactive_physical_slots") != 1
        or len(slot_rows) != 1
        or slot_row.get("slot_type") != "physical"
        or slot_row.get("active") is not False
        or not slot_row.get("restart_lsn")
        or slot_row.get("retained_wal_bytes") != retained_bytes,
        "retention evidence does not prove one inactive physical slot",
    )
    fail_if(
        failures,
        retention_mitigation.get("action")
        != "pg_drop_replication_slot"
        or retention_mitigation.get("scope")
        != "exact-owned-disposable-slot"
        or retention_mitigation.get("slot_name")
        != slot_row.get("slot_name")
        or not retention_mitigation.get("evidence_preserved_at")
        or retention_mitigation.get("manual_pg_wal_file_deletion")
        is not False
        or retention_mitigation.get("broad_slot_cleanup_used")
        is not False
        or retention_mitigation.get("connection_cancel_used") is not False
        or retention_recovery.get("post_physical_slots") != 0
        or retention_recovery.get("post_inactive_physical_slots") != 0
        or retention_recovery.get("post_probe") != 1,
        "retention mitigation scope or recovery drifted",
    )

    for case_id, answer in hidden_index.items():
        result = result_index.get(case_id, {})
        expected = answer.get("expected_route")
        fail_if(
            failures,
            result.get("route") != expected
            or not isinstance(result.get("evidence"), list)
            or len(result.get("evidence", [])) != 5,
            f"blind classification is wrong or unsupported for {case_id}",
        )
        if expected == "RELIEVE_FLOW_PRESSURE":
            fail_if(
                failures,
                result.get("flow_predicate") is not True
                or result.get("retention_predicate") is not False,
                "flow predicates are ambiguous",
            )
        if expected == "PRESERVE_RETENTION_EVIDENCE":
            fail_if(
                failures,
                result.get("flow_predicate") is not False
                or result.get("retention_predicate") is not True,
                "retention predicates are ambiguous",
            )

    safety = exercise.get("safety", {})
    required_false = (
        "managed_postgresql_mutated",
        "managed_connection_storm",
        "managed_replication_slot_created",
        "managed_query_canceled",
        "managed_service_changed",
        "managed_route_changed",
        "host_cache_dropped",
        "oom_injected",
        "filesystem_fill_injected",
        "wrong_action_executed",
        "manual_pg_wal_file_deletion",
        "production_data_touched",
        "production_traffic_touched",
    )
    fail_if(
        failures,
        any(safety.get(key) is not False for key in required_false)
        or safety.get("external_dispatch_count") != 0,
        "exercise safety boundary drifted",
    )
    fail_if(
        failures,
        cleanup != exercise.get("cleanup")
        or cleanup.get("root_exists_after") is not False
        or cleanup.get("marker_matched") is not True
        or cleanup.get("server_stopped_before_cleanup") is not True,
        "exact disposable cleanup is unproved",
    )

    manifest_rows = source_manifest.get("files", [])
    manifest_index = {
        row.get("path"): row
        for row in manifest_rows
        if isinstance(row, dict)
    }
    fail_if(
        failures,
        source_manifest.get("schema")
        != "pg36-ch34-source-manifest-v1"
        or set(manifest_index) != set(SOURCE_FILES)
        or len(manifest_rows) != len(SOURCE_FILES),
        "source manifest file set drifted",
    )
    for name in SOURCE_FILES:
        row = manifest_index.get(name, {})
        path = source_dir / name
        fail_if(
            failures,
            not path.is_file()
            or row.get("sha256") != sha256_file(path)
            or row.get("bytes") != path.stat().st_size,
            f"source hash binding drifted: {name}",
        )


def load_bundle(evidence_dir: Path) -> dict[str, Any]:
    exercise_dir = evidence_dir / "exercise"
    return {
        "before": read_json(evidence_dir / "before.json"),
        "after": read_json(evidence_dir / "after.json"),
        "exercise": read_json(exercise_dir / "exercise-evidence.json"),
        "blind_packets": read_json(exercise_dir / "blind-packets.json"),
        "hidden_answers": read_json(exercise_dir / "hidden-answers.json"),
        "classification": read_json(evidence_dir / "classification.json"),
        "cleanup": read_json(exercise_dir / "cleanup.json"),
        "run_manifest": read_json(exercise_dir / "run-manifest.json"),
        "source_manifest": read_json(
            exercise_dir / "source-manifest.json"
        ),
    }


def locate_case(bundle: dict[str, Any], scenario: str) -> dict[str, Any]:
    for row in bundle["exercise"]["cases"]:
        if row.get("scenario") == scenario:
            return row
    raise LabError(f"cannot locate {scenario} case")


def packet_copies(
    bundle: dict[str, Any],
    case_id: str,
) -> list[dict[str, Any]]:
    result = []
    for rows in (
        bundle["blind_packets"],
        bundle["exercise"]["blind_packets"],
    ):
        for row in rows:
            if row.get("case_id") == case_id:
                result.append(row)
    case = next(
        row
        for row in bundle["exercise"]["cases"]
        if row.get("case_id") == case_id
    )
    result.append(case["blind_packet"])
    return result


def mutate(bundle: dict[str, Any], mutation: str) -> None:
    requirements = bundle["requirements"]
    contract = bundle["contract"]
    if mutation == "requirements.production_data=true":
        requirements["target"]["production_data_permitted"] = True
    elif mutation == "requirements.production_traffic=true":
        requirements["target"]["production_traffic_permitted"] = True
    elif mutation == "requirements.managed_storm=true":
        requirements["risk"]["managed_connection_storm_permitted"] = True
    elif mutation == "requirements.managed_slot=true":
        requirements["risk"]["managed_replication_slot_permitted"] = True
    elif mutation == "requirements.managed_cancel=true":
        requirements["risk"]["managed_query_cancel_permitted"] = True
    elif mutation == "requirements.manual_wal_delete=true":
        requirements["risk"]["manual_pg_wal_deletion_permitted"] = True
    elif mutation == "requirements.oom=true":
        requirements["risk"]["oom_injection_permitted"] = True
    elif mutation == "requirements.scenarios=1":
        requirements["exercise"]["scenario_count"] = 1
    elif mutation == "contract.remove-route":
        contract["routes"].pop()
    elif mutation == "contract.remove-unknown-route":
        contract.pop("unknown_route", None)
    elif mutation == "contract.flow-sessions=1":
        contract["routes"][0]["requires"][0] = (
            "connection.observed_sessions >= 1"
        )
    elif mutation == "contract.retained-bytes=0":
        contract["routes"][1]["requires"][1] = (
            "retention.retained_wal_bytes >= 0"
        )
    elif mutation == "contract.allow-delete-pg-wal":
        contract["routes"][1]["forbidden_shortcut"] = "none"
    elif mutation == "blind.add-hidden-truth":
        bundle["blind_packets"][0]["truth"] = "FLOW"
    elif mutation == "blind.add-expected-route":
        bundle["blind_packets"][0]["expected_route"] = (
            "RELIEVE_FLOW_PRESSURE"
        )
    elif mutation == "blind.remove-retention":
        bundle["blind_packets"][0].pop("retention", None)
    elif mutation == "classification.duplicate-case":
        rows = bundle["classification"]["results"]
        rows[1]["case_id"] = rows[0]["case_id"]
    elif mutation == "classification.flow=retention":
        flow = locate_case(bundle, "FLOW")
        rows_by_case(bundle["classification"]["results"])[
            flow["case_id"]
        ]["route"] = "PRESERVE_RETENTION_EVIDENCE"
    elif mutation == "classification.retention=flow":
        retention = locate_case(bundle, "RETENTION")
        rows_by_case(bundle["classification"]["results"])[
            retention["case_id"]
        ]["route"] = "RELIEVE_FLOW_PRESSURE"
    elif mutation == "classification.remove-evidence":
        bundle["classification"]["results"][0]["evidence"] = []
    elif mutation.startswith("evidence.flow."):
        flow = locate_case(bundle, "FLOW")
        case_id = flow["case_id"]
        copies = packet_copies(bundle, case_id)
        if mutation == "evidence.flow.sessions=1":
            for packet in copies:
                packet["connection"]["observed_sessions"] = 1
        elif mutation == "evidence.flow.rejections=0":
            for packet in copies:
                packet["connection"]["connection_rejections"] = 0
        elif mutation == "evidence.flow.lock-waiters=0":
            for packet in copies:
                packet["connection"]["lock_waiters"] = 0
        elif mutation == "evidence.flow.inactive-slot=1":
            for packet in copies:
                packet["retention"]["inactive_physical_slots"] = 1
        elif mutation == "evidence.flow.cancel-scope=all":
            flow["mitigation"]["scope"] = "all-sessions"
            flow["mitigation"]["broad_cancel_used"] = True
        elif mutation == "evidence.flow.post-sessions=1":
            flow["recovery"]["post_fixture_sessions"] = 1
        else:
            raise LabError(f"unknown flow mutation: {mutation}")
    elif mutation.startswith("evidence.retention."):
        retention = locate_case(bundle, "RETENTION")
        case_id = retention["case_id"]
        copies = packet_copies(bundle, case_id)
        slot = retention["observed"]["slot"]
        if mutation == "evidence.retention.slots=0":
            for packet in copies:
                packet["retention"]["inactive_physical_slots"] = 0
            slot["inactive_physical_slots"] = 0
        elif mutation == "evidence.retention.active=true":
            slot["rows"][0]["active"] = True
        elif mutation == "evidence.retention.bytes=1":
            for packet in copies:
                packet["retention"]["retained_wal_bytes"] = 1
            slot["rows"][0]["retained_wal_bytes"] = 1
        elif mutation == "evidence.retention.rejections=1":
            for packet in copies:
                packet["connection"]["connection_rejections"] = 1
        elif mutation == "evidence.retention.wal-deleted=true":
            retention["mitigation"][
                "manual_pg_wal_file_deletion"
            ] = True
        elif mutation == "evidence.retention.post-slots=1":
            retention["recovery"]["post_physical_slots"] = 1
        else:
            raise LabError(f"unknown retention mutation: {mutation}")
    elif mutation == "evidence.cleanup.root-left=true":
        bundle["cleanup"]["root_exists_after"] = True
        bundle["exercise"]["cleanup"]["root_exists_after"] = True
    elif mutation == "evidence.production-gate=approved":
        bundle["run_manifest"]["production_ch34_gate"] = "approved"
    else:
        raise LabError(f"unknown mutation: {mutation}")


def build_public(
    bundle: dict[str, Any],
    negative_count: int,
) -> dict[str, Any]:
    exercise = bundle["exercise"]
    flow = locate_case(bundle, "FLOW")
    retention = locate_case(bundle, "RETENTION")
    flow_packet = flow["blind_packet"]
    retention_packet = retention["blind_packet"]
    routes = {
        row["case_id"]: row["route"]
        for row in bundle["classification"]["results"]
    }
    return {
        "schema": "pg36-ch34-public-summary-v1",
        "status": "completed",
        "run_id": exercise["run_id"],
        "observed_at": exercise["finished_at"],
        "target": exercise["target"],
        "common_alert": exercise["common_alert"],
        "experiment": {
            "postgresql_version": flow_packet["engine"]["server_version"],
            "host": exercise["host"],
            "unix_socket_only": exercise["disposable"][
                "unix_socket_only"
            ],
            "randomized_order": exercise["scenario_order"],
            "blind_classification": True,
            "case_count": 2,
        },
        "flow_pressure": {
            "attempted_clients": flow_packet["connection"][
                "attempted_clients"
            ],
            "observed_sessions": flow_packet["connection"][
                "observed_sessions"
            ],
            "connection_rejections": flow_packet["connection"][
                "connection_rejections"
            ],
            "lock_waiters": flow_packet["connection"]["lock_waiters"],
            "classified_route": routes[flow["case_id"]],
            "mitigation_scope": flow["mitigation"]["scope"],
            "post_fixture_sessions": flow["recovery"][
                "post_fixture_sessions"
            ],
        },
        "wal_retention": {
            "inactive_physical_slots": retention_packet["retention"][
                "inactive_physical_slots"
            ],
            "retained_wal_bytes": retention_packet["retention"][
                "retained_wal_bytes"
            ],
            "generated_wal_bytes": retention["observed"][
                "generated_wal_bytes"
            ],
            "classified_route": routes[retention["case_id"]],
            "mitigation_scope": retention["mitigation"]["scope"],
            "post_physical_slots": retention["recovery"][
                "post_physical_slots"
            ],
            "manual_pg_wal_file_deletion": retention["mitigation"][
                "manual_pg_wal_file_deletion"
            ],
        },
        "managed_cluster": {
            "topology_unchanged": (
                managed_topology_signature(bundle["before"])
                == managed_topology_signature(bundle["after"])
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
            "exact_root_removed": (
                exercise["cleanup"]["root_exists_after"] is False
            ),
        },
        "evidence": {
            "declared_counterexamples": negative_count,
            "live_mutants_rejected": negative_count,
            "source_files_hash_bound": len(SOURCE_FILES),
        },
        "decision": {
            "production_approval": None,
            "production_ch34_gate": "pending",
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
        failures: list[str] = []
        validate_static(
            failures,
            requirements,
            contract,
            negative,
            args.source_dir,
        )
        if args.evidence_dir is None:
            report = {
                "schema": "pg36-ch34-validation-report-v1",
                "validated_at": utc_now(),
                "mode": "contracts-only",
                "passed": not failures,
                "failure_count": len(failures),
                "failures": failures,
                "declared_counterexamples": len(
                    negative.get("cases", [])
                ),
                "source_files_hash_bound": len(SOURCE_FILES),
                "production_ch34_gate": "pending",
            }
            write_json(args.output, report)
            if failures:
                raise LabError("; ".join(failures))
            return 0

        bundle = load_bundle(args.evidence_dir)
        bundle["requirements"] = requirements
        bundle["contract"] = contract
        bundle["negative"] = negative
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
        accepted_mutants = [
            row["id"]
            for row in mutant_results
            if row["rejected"] is not True
        ]
        if accepted_mutants:
            failures.append(
                "live mutants accepted: " + ", ".join(accepted_mutants)
            )
        run_id = bundle["exercise"].get("run_id")
        report = {
            "schema": "pg36-ch34-validation-report-v1",
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
            "production_ch34_gate": "pending",
        }
        write_json(args.output, report)
        if args.negative_output is None or args.public_summary is None:
            raise LabError(
                "complete validation requires negative and public outputs"
            )
        negative_report = {
            "schema": "pg36-ch34-negative-report-v1",
            "validated_at": utc_now(),
            "run_id": run_id,
            "passed": not accepted_mutants,
            "case_count": len(mutant_results),
            "rejected_count": sum(
                1 for row in mutant_results if row["rejected"]
            ),
            "live_mutant_count": len(mutant_results),
            "live_mutants_rejected": sum(
                1 for row in mutant_results if row["rejected"]
            ),
            "results": mutant_results,
        }
        write_json(args.negative_output, negative_report)
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
