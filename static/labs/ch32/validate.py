#!/usr/bin/env python3
"""Validate chapter 32 contracts, evidence, and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    LabError,
    SOURCE_FILES,
    read_json,
    require_stable_source,
    source_hashes,
    upstream_hashes,
    utc_now,
    write_json,
)


EXPECTED_STATES = [
    "PREFLIGHT",
    "FIXTURE_BASE",
    "BACKUP_READY",
    "SAFE_BEFORE",
    "DAMAGE_COMMITTED",
    "POST_TARGET_WRITES",
    "WAL_ARCHIVED",
    "INCLUSIVE_REJECTED",
    "EXCLUSIVE_ACCEPTED",
    "RECONCILED",
    "CLEANED",
]

EXPECTED_MUTATIONS = {
    "requirements.production-data=true",
    "requirements.managed-pgdata=true",
    "requirements.patroni-change=true",
    "requirements.expire=true",
    "requirements.target-type=time",
    "requirements.exclusive=false",
    "requirements.timeline=latest",
    "requirements.archive-mode=on",
    "requirements.listen-addresses=*",
    "contract.remove-inclusive-rejected",
    "contract.skip-inclusive",
    "contract.allow-managed-pgdata",
    "contract.allow-expire",
    "preflight.target=production",
    "preflight.primary=wrong",
    "preflight.replica=stopped",
    "preflight.source-hash=wrong",
    "preflight.upstream-hash=wrong",
    "evidence.damage-xid=wrong",
    "evidence.backup-label=wrong",
    "evidence.archive-covered=false",
    "inclusive.damage-absent",
    "inclusive.accepted=true",
    "exclusive.damage-present",
    "exclusive.safe-missing",
    "exclusive.post-present",
    "reconcile.rows=999",
    "reconcile.post-preserved=false",
    "reconcile.external-dispatch=1",
    "evidence.route-changed=true",
    "cleanup.restore-root-present=true",
    "evidence.production-gate=approved",
}

EVIDENCE_FILES = {
    "preflight": "preflight-evidence.json",
    "manifest": "exercise-manifest.json",
    "source_before": "source-before.json",
    "fixture": "fixture.json",
    "backup": "backup.json",
    "inclusive_plan": "inclusive-plan.json",
    "inclusive": "inclusive-recovery.json",
    "exclusive_plan": "exclusive-plan.json",
    "exclusive": "exclusive-recovery.json",
    "reconciliation": "reconciliation.json",
    "source_after": "source-after.json",
    "cleanup": "cleanup.json",
}


class ValidationError(LabError):
    """Raised when validation input cannot be loaded."""


def fail_if(
    errors: list[str],
    condition: bool,
    code: str,
) -> None:
    if condition:
        errors.append(code)


def all_false(value: dict[str, Any]) -> bool:
    return all(item is False for item in value.values())


def positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def audit_map(candidate: dict[str, Any]) -> dict[str, str]:
    state = candidate.get("effective_state", {})
    return {
        str(row.get("stage")): str(row.get("xact_id"))
        for row in state.get("audits", [])
        if isinstance(row, dict)
    }


def validate_requirements(
    errors: list[str],
    requirements: dict[str, Any],
) -> None:
    fail_if(
        errors,
        requirements.get("schema")
        != "pg36-ch32-pitr-requirements-v1",
        "E_REQ_SCHEMA",
    )
    target = requirements.get("target", {})
    fail_if(
        errors,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("cluster") != "pg-test"
        or target.get("source_primary") != "pg-test-1"
        or target.get("source_address") != "10.10.10.11"
        or target.get("restore_host") != "pg-test-3"
        or target.get("restore_address") != "10.10.10.13"
        or target.get("postgresql_major") != 18
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False,
        "E_REQ_TARGET",
    )
    fixture = requirements.get("fixture", {})
    fail_if(
        errors,
        fixture.get("database") != "test"
        or fixture.get("schema") != "pg36_ch32"
        or fixture.get("account_count") != 5000
        or fixture.get("victim_count") != 1000
        or fixture.get("post_target_legitimate_count") != 100
        or fixture.get("safe_delta_cents") != 100
        or fixture.get("post_target_delta_cents") != 700
        or fixture.get("wrong_outbox_events") != 1000
        or fixture.get("external_dispatch_enabled") is not False,
        "E_REQ_FIXTURE",
    )
    repository = requirements.get("repository", {})
    fail_if(
        errors,
        repository.get("stanza") != "pg-test"
        or repository.get("repo") != 1
        or repository.get("fresh_backup_type") != "full"
        or repository.get("archive_continuity_required") is not True
        or repository.get("fresh_backup_retained") is not True
        or repository.get("expire_permitted") is not False,
        "E_REQ_REPOSITORY",
    )
    restore = requirements.get("restore", {})
    fail_if(
        errors,
        restore.get("root_prefix") != "/data/pg36-ch32-restore"
        or restore.get("port") != 55433
        or restore.get("target_type") != "xid"
        or restore.get("target_inclusive_candidate_required") is not True
        or restore.get("accepted_target_exclusive") is not True
        or restore.get("target_action") != "promote"
        or restore.get("target_timeline") != "current"
        or restore.get("side_restore") is not True
        or restore.get("pig_no_restart") is not True
        or restore.get("listen_addresses") != ""
        or restore.get("unix_socket_permissions") != "0700"
        or restore.get("ssl") is not False
        or restore.get("archive_mode") != "off"
        or restore.get("patroni_managed") is not False
        or restore.get("cleanup_restore_roots") is not True,
        "E_REQ_RESTORE",
    )
    risk = requirements.get("risk", {})
    fail_if(
        errors,
        risk.get("exercise")
        != "L2-bounded-disposable-fixture-and-side-restore"
        or any(
            risk.get(name) is not False
            for name in (
                "managed_pgdata_permitted",
                "patroni_change_permitted",
                "dcs_change_permitted",
                "service_route_change_permitted",
                "unrelated_connection_termination_permitted",
                "force_drop_permitted",
                "manual_wal_file_change_permitted",
            )
        ),
        "E_REQ_RISK",
    )
    acceptance = requirements.get("acceptance", {})
    fail_if(
        errors,
        acceptance.get("damage_xid_must_be_derived_from_source_audit")
        is not True
        or acceptance.get("inclusive_candidate_must_contain_damage")
        is not True
        or acceptance.get("exclusive_candidate_must_exclude_damage")
        is not True
        or acceptance.get(
            "reconciliation_must_preserve_post_target_legitimate_writes"
        )
        is not True
        or acceptance.get("external_dispatch_count_must_remain_zero")
        is not True
        or acceptance.get("business_cutover_performed") is not False
        or acceptance.get("production_ch32_gate") != "pending",
        "E_REQ_ACCEPTANCE",
    )


def validate_contract(
    errors: list[str],
    contract: dict[str, Any],
) -> None:
    fail_if(
        errors,
        contract.get("schema")
        != "pg36-ch32-recovery-contract-v1",
        "E_CONTRACT_SCHEMA",
    )
    states = contract.get("states", [])
    fail_if(
        errors,
        states != EXPECTED_STATES,
        "E_CONTRACT_STATES",
    )
    expected_transitions = [
        [left, right]
        for left, right in zip(EXPECTED_STATES, EXPECTED_STATES[1:])
    ]
    fail_if(
        errors,
        contract.get("transitions") != expected_transitions,
        "E_CONTRACT_TRANSITIONS",
    )
    allowed = "\n".join(contract.get("allowed_mutations", []))
    forbidden = "\n".join(contract.get("forbidden_mutations", []))
    fail_if(
        errors,
        "side restore" not in allowed
        or "repair the exact fixture" not in allowed
        or "restore over /pg/data" not in forbidden
        or "expire or delete backups" not in forbidden
        or "enable TCP" not in forbidden,
        "E_CONTRACT_BOUNDARY",
    )
    gates = contract.get("decision_gates", {})
    fail_if(
        errors,
        gates.get("inclusive_candidate_contains_damage") != "rejected"
        or gates.get("target_without_audit_xid") != "blocked"
        or gates.get("post_target_write_set_unknown") != "blocked"
        or gates.get("business_cutover") != "not-performed"
        or gates.get("production_ch32_gate") != "pending",
        "E_CONTRACT_GATES",
    )


def validate_negative_catalog(
    errors: list[str],
    negative: dict[str, Any],
) -> None:
    cases = negative.get("cases", [])
    mutations = [
        row.get("mutation")
        for row in cases
        if isinstance(row, dict)
    ]
    identifiers = [
        row.get("id")
        for row in cases
        if isinstance(row, dict)
    ]
    fail_if(
        errors,
        negative.get("schema") != "pg36-ch32-negative-cases-v1"
        or len(cases) != 32
        or len(set(identifiers)) != 32
        or set(mutations) != EXPECTED_MUTATIONS,
        "E_NEGATIVE_CATALOG",
    )


def validate_preflight(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
    source_dir: Path,
) -> None:
    preflight = documents["preflight"]
    fail_if(
        errors,
        preflight.get("schema") != "pg36-ch32-preflight-v1"
        or preflight.get("target") != requirements["target"]["id"]
        or preflight.get("mutation") != "none",
        "E_PREFLIGHT_IDENTITY",
    )
    try:
        require_stable_source(
            preflight.get("topology", {}),
            requirements,
        )
    except LabError:
        errors.append("E_PREFLIGHT_TOPOLOGY")
    source = preflight.get("source", {})
    fail_if(
        errors,
        source.get("cluster_name") != "pg-test"
        or source.get("in_recovery") is not False
        or source.get("fixture_schema_exists") is not False,
        "E_PREFLIGHT_SOURCE",
    )
    restore_member = preflight.get("restore_member", {})
    fail_if(
        errors,
        restore_member.get("cluster_name") != "pg-test"
        or restore_member.get("in_recovery") is not True
        or restore_member.get("fixture_schema_exists") is not False,
        "E_PREFLIGHT_RESTORE_MEMBER",
    )
    restore_host = preflight.get("restore_host", {})
    fail_if(
        errors,
        restore_host.get("candidate_count") != 0
        or restore_host.get("prefix_symlink") is not False
        or restore_host.get("tcp_listener") is not False,
        "E_PREFLIGHT_RESTORE_HOST",
    )
    fail_if(
        errors,
        preflight.get("toolchain", {}).get(
            "pig_pitr_all_required_flags"
        )
        is not True,
        "E_PREFLIGHT_TOOLCHAIN",
    )
    fail_if(
        errors,
        not all_false(preflight.get("claims", {})),
        "E_PREFLIGHT_MUTATION",
    )
    fail_if(
        errors,
        preflight.get("source_sha256") != source_hashes(source_dir),
        "E_PREFLIGHT_SOURCE_HASH",
    )
    fail_if(
        errors,
        preflight.get("upstream_sha256")
        != upstream_hashes(source_dir, requirements),
        "E_PREFLIGHT_UPSTREAM_HASH",
    )


def validate_manifest(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
    source_dir: Path,
) -> None:
    manifest = documents["manifest"]
    preflight = documents["preflight"]
    fail_if(
        errors,
        manifest.get("schema")
        != "pg36-ch32-exercise-manifest-v1"
        or manifest.get("status") != "completed"
        or manifest.get("target") != requirements["target"]["id"]
        or manifest.get("preflight_run_id") != preflight.get("run_id")
        or manifest.get("mode")
        != "random-xid-pitr-and-reconciliation",
        "E_MANIFEST_IDENTITY",
    )
    fail_if(
        errors,
        manifest.get("production_approval") is not False
        or manifest.get("production_data") is not False
        or manifest.get("production_traffic") is not False
        or manifest.get("business_cutover_performed") is not False
        or manifest.get("external_dispatch_enabled") is not False
        or manifest.get("managed_pgdata_touched") is not False
        or manifest.get("patroni_changed") is not False
        or manifest.get("dcs_changed") is not False
        or manifest.get("route_changed") is not False
        or manifest.get("backup_expired") is not False,
        "E_MANIFEST_SAFETY",
    )
    fail_if(
        errors,
        manifest.get("damage_xid_source")
        != "pg36_ch32.incident_audit"
        or manifest.get("inclusive_candidate") != "rejected"
        or manifest.get("exclusive_candidate") != "accepted"
        or manifest.get("reconciliation") != "completed"
        or manifest.get("cleanup") != "completed"
        or manifest.get("fresh_backup_retained") is not True
        or manifest.get("production_ch32_gate") != "pending",
        "E_MANIFEST_OUTCOME",
    )
    fail_if(
        errors,
        manifest.get("source_sha256") != source_hashes(source_dir)
        or len(manifest.get("source_sha256", {}))
        != len(SOURCE_FILES),
        "E_MANIFEST_SOURCE_HASH",
    )


def validate_fixture_and_backup(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    fixture = documents["fixture"]
    manifest = documents["manifest"]
    backup = documents["backup"]
    expected = requirements["fixture"]
    fail_if(
        errors,
        fixture.get("schema") != "pg36-ch32-fixture-v1"
        or fixture.get("run_id") != manifest.get("run_id")
        or fixture.get("account_count") != expected["account_count"]
        or fixture.get("victim_count") != expected["victim_count"]
        or fixture.get("post_target_count")
        != expected["post_target_legitimate_count"]
        or fixture.get("safe_delta_cents") != expected["safe_delta_cents"]
        or fixture.get("post_target_delta_cents")
        != expected["post_target_delta_cents"]
        or fixture.get("external_dispatch_count") != 0,
        "E_FIXTURE_SHAPE",
    )
    start = fixture.get("victim_start")
    end = fixture.get("victim_end")
    post_end = fixture.get("post_target_end")
    fail_if(
        errors,
        not isinstance(start, int)
        or not isinstance(end, int)
        or not isinstance(post_end, int)
        or start < 1
        or end - start + 1 != expected["victim_count"]
        or post_end - start + 1
        != expected["post_target_legitimate_count"]
        or end > expected["account_count"],
        "E_FIXTURE_RANGE",
    )
    boundary = fixture.get("incident_boundary", {})
    damage = fixture.get("damage_transaction", {})
    safe = fixture.get("safe_transaction", {})
    post = fixture.get("post_target_transaction", {})
    fail_if(
        errors,
        not str(boundary.get("damage_xid", "")).isdigit()
        or boundary.get("damage_xid") != damage.get("xact_id")
        or boundary.get("post_target_xid") != post.get("xact_id")
        or safe.get("ledger_count") != expected["victim_count"]
        or damage.get("pending_outbox_count")
        != expected["wrong_outbox_events"]
        or damage.get("external_dispatch_count") != 0
        or post.get("ledger_count")
        != expected["post_target_legitimate_count"],
        "E_FIXTURE_BOUNDARY",
    )
    fail_if(
        errors,
        backup.get("schema") != "pg36-ch32-backup-v1"
        or not isinstance(backup.get("label"), str)
        or not backup.get("label")
        or backup.get("type") != "full"
        or backup.get("error") is not False
        or backup.get("repository_status_code") != 0
        or not positive_number(backup.get("info", {}).get("size"))
        or not positive_number(
            backup.get("info", {})
            .get("repository", {})
            .get("delta")
        )
        or backup.get("archive_covered") is not True
        or backup.get("maximum_archived_wal", "")
        < backup.get("required_wal_segment", "")
        or backup.get("retained") is not True
        or backup.get("expire_executed") is not False,
        "E_BACKUP",
    )


def validate_plan(
    errors: list[str],
    plan: dict[str, Any],
    *,
    candidate: str,
    inclusive: bool,
    fixture: dict[str, Any],
    backup: dict[str, Any],
) -> None:
    fail_if(
        errors,
        plan.get("schema") != "pg36-ch32-pitr-plan-v1"
        or plan.get("candidate") != candidate
        or plan.get("backup_label") != backup.get("label")
        or plan.get("target_type") != "xid"
        or plan.get("target")
        != fixture.get("incident_boundary", {}).get("damage_xid")
        or plan.get("target_inclusive") is not inclusive
        or plan.get("target_timeline") != "current"
        or plan.get("target_action") != "promote"
        or plan.get("side_restore") is not True
        or plan.get("no_restart") is not True
        or plan.get("archive_mode") != "off"
        or not isinstance(plan.get("plan"), (dict, list)),
        f"E_{candidate.upper()}_PLAN",
    )


def validate_isolation(
    errors: list[str],
    candidate: dict[str, Any],
    *,
    name: str,
    port: int,
) -> None:
    state = candidate.get("effective_state", {})
    runtime = candidate.get("runtime_isolation", {})
    fail_if(
        errors,
        state.get("in_recovery") is not False
        or state.get("archive_mode") != "off"
        or state.get("listen_addresses") != ""
        or state.get("port") != port
        or state.get("ssl") is not False
        or state.get("shared_preload_libraries") != ""
        or state.get("cluster_name") != f"pg36-ch32-{name}"
        or candidate.get("patroni_managed") is not False
        or runtime.get("tcp_listener") is not False
        or runtime.get("socket_exists") is not True
        or runtime.get("socket_mode") != "700"
        or runtime.get("socket_owner") != "postgres:postgres"
        or runtime.get("postmaster_pid_exists") is not True,
        f"E_{name.upper()}_ISOLATION",
    )


def validate_candidates(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    fixture = documents["fixture"]
    backup = documents["backup"]
    inclusive = documents["inclusive"]
    exclusive = documents["exclusive"]
    expected = requirements["fixture"]
    damage_xid = fixture.get("incident_boundary", {}).get("damage_xid")

    validate_plan(
        errors,
        documents["inclusive_plan"],
        candidate="inclusive",
        inclusive=True,
        fixture=fixture,
        backup=backup,
    )
    validate_plan(
        errors,
        documents["exclusive_plan"],
        candidate="exclusive",
        inclusive=False,
        fixture=fixture,
        backup=backup,
    )
    validate_isolation(
        errors,
        inclusive,
        name="inclusive",
        port=requirements["restore"]["port"],
    )
    source_timeline = documents["source_before"].get(
        "postgres", {}
    ).get("checkpoint_timeline")
    fail_if(
        errors,
        not isinstance(source_timeline, int)
        or inclusive.get("effective_state", {}).get("timeline")
        != source_timeline + 1
        or exclusive.get("effective_state", {}).get("timeline")
        != source_timeline + 1
        or not positive_number(inclusive.get("restore_copy_ms"))
        or not positive_number(inclusive.get("start_to_promoted_ms"))
        or not positive_number(inclusive.get("validation_ms"))
        or not positive_number(exclusive.get("restore_copy_ms"))
        or not positive_number(exclusive.get("start_to_promoted_ms"))
        or not positive_number(exclusive.get("validation_ms")),
        "E_CANDIDATE_TIMING_LINEAGE",
    )
    validate_isolation(
        errors,
        exclusive,
        name="exclusive",
        port=requirements["restore"]["port"],
    )

    inclusive_state = inclusive.get("effective_state", {})
    inclusive_audits = audit_map(inclusive)
    fail_if(
        errors,
        inclusive.get("schema")
        != "pg36-ch32-recovery-candidate-v1"
        or inclusive.get("candidate") != "inclusive"
        or inclusive.get("backup_label") != backup.get("label")
        or inclusive.get("damage_xid") != damage_xid
        or inclusive.get("target_inclusive") is not True
        or inclusive.get("accepted") is not False
        or inclusive_audits.get("damage") != damage_xid
        or set(inclusive_audits)
        != {"base", "safe-before", "damage"}
        or inclusive_state.get("safe_ledger_count")
        != expected["victim_count"]
        or inclusive_state.get("post_ledger_count") != 0
        or inclusive_state.get("pending_outbox_count")
        != expected["wrong_outbox_events"]
        or inclusive_state.get("victims", {}).get("mispriced")
        != expected["victim_count"],
        "E_INCLUSIVE_BOUNDARY",
    )

    exclusive_state = exclusive.get("effective_state", {})
    exclusive_audits = audit_map(exclusive)
    start = fixture["victim_start"]
    end = fixture["victim_end"]
    victim_base = sum(
        100000 + account_id
        for account_id in range(start, end + 1)
    )
    expected_victim_sum = (
        victim_base
        + expected["victim_count"] * expected["safe_delta_cents"]
    )
    fail_if(
        errors,
        exclusive.get("schema")
        != "pg36-ch32-recovery-candidate-v1"
        or exclusive.get("candidate") != "exclusive"
        or exclusive.get("backup_label") != backup.get("label")
        or exclusive.get("damage_xid") != damage_xid
        or exclusive.get("target_inclusive") is not False
        or exclusive.get("accepted") is not True
        or set(exclusive_audits) != {"base", "safe-before"}
        or exclusive_state.get("safe_ledger_count")
        != expected["victim_count"]
        or exclusive_state.get("post_ledger_count") != 0
        or exclusive_state.get("pending_outbox_count") != 0
        or exclusive_state.get("victims", {}).get("active")
        != expected["victim_count"]
        or exclusive_state.get("victims", {}).get("mispriced") != 0
        or exclusive_state.get("victims", {}).get("balance_cents")
        != expected_victim_sum
        or exclusive.get("recovered_account_count")
        != expected["victim_count"],
        "E_EXCLUSIVE_BOUNDARY",
    )


def validate_reconciliation(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    value = documents["reconciliation"]
    fixture = requirements["fixture"]
    expected = value.get("expected_manifest", {})
    actual = value.get("actual_manifest", {})
    fail_if(
        errors,
        value.get("schema") != "pg36-ch32-reconciliation-v1"
        or value.get("run_id")
        != documents["manifest"].get("run_id")
        or value.get("method")
        != "exclusive-history-plus-audited-post-target-delta"
        or value.get("recovered_rows") != fixture["victim_count"]
        or value.get("audited_post_target_rows")
        != fixture["post_target_legitimate_count"]
        or value.get("conditional_rows_repaired")
        != fixture["victim_count"]
        or value.get("wrong_outbox_canceled")
        != fixture["wrong_outbox_events"]
        or value.get("external_dispatch_count") != 0
        or value.get("raw_exclusive_missing_legitimate_writes")
        != fixture["post_target_legitimate_count"]
        or value.get("reconciled_fixture_data_loss_rows") != 0
        or value.get("business_cutover_performed") is not False,
        "E_RECONCILIATION_COUNTS",
    )
    fail_if(
        errors,
        actual.get("accounts") != expected.get("accounts")
        or actual.get("total_balance_cents")
        != expected.get("total_balance_cents")
        or actual.get("victims", {}).get("active")
        != expected.get("victims_active")
        or actual.get("victims", {}).get("mispriced") != 0
        or actual.get("safe_ledger_count")
        != expected.get("safe_ledger_count")
        or actual.get("post_ledger_count")
        != expected.get("post_ledger_count")
        or actual.get("pending_outbox_count")
        != expected.get("pending_outbox_count")
        or actual.get("canceled_outbox_count")
        != expected.get("canceled_outbox_count")
        or actual.get("external_dispatch_count") != 0,
        "E_RECONCILIATION_MANIFEST",
    )


def validate_postflight(
    errors: list[str],
    documents: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    source_before = documents["source_before"]
    source_after = documents["source_after"]
    cleanup = documents["cleanup"]
    try:
        require_stable_source(
            source_before.get("topology", {}),
            requirements,
        )
        require_stable_source(
            source_after.get("topology", {}),
            requirements,
        )
    except LabError:
        errors.append("E_POSTFLIGHT_TOPOLOGY")
    fail_if(
        errors,
        source_after.get("postgres", {}).get("fixture_schema_exists")
        is not False
        or source_after.get("source_system_identifier_unchanged")
        is not True
        or source_after.get("backup_retained") is not True,
        "E_POSTFLIGHT_SOURCE",
    )
    fail_if(
        errors,
        cleanup.get("schema") != "pg36-ch32-cleanup-v1"
        or cleanup.get("run_id")
        != documents["manifest"].get("run_id")
        or cleanup.get("fixture", {}).get("schema_exists") is not False
        or cleanup.get("fixture", {}).get("exact_marker_cleanup")
        is not True
        or cleanup.get("inclusive", {}).get("root_removed") is not True
        or cleanup.get("exclusive", {}).get("root_removed") is not True
        or cleanup.get("restore_prefix", {}).get("entries") != 0
        or cleanup.get("restore_prefix", {}).get("tcp_listener")
        is not False
        or cleanup.get("exact_restore_roots_removed") is not True
        or cleanup.get("fixture_schema_removed") is not True
        or cleanup.get("backup_retained") is not True
        or cleanup.get("backup_expired") is not False
        or cleanup.get("archived_wal_deleted") is not False
        or cleanup.get("unrelated_process_terminated") is not False
        or cleanup.get("patroni_changed") is not False
        or cleanup.get("dcs_changed") is not False
        or cleanup.get("route_changed") is not False,
        "E_CLEANUP",
    )


def validate_documents(
    documents: dict[str, Any],
    requirements: dict[str, Any],
    contract: dict[str, Any],
    negative: dict[str, Any],
    source_dir: Path,
) -> list[str]:
    errors: list[str] = []
    validate_requirements(errors, requirements)
    validate_contract(errors, contract)
    validate_negative_catalog(errors, negative)
    validate_preflight(
        errors,
        documents,
        requirements,
        source_dir,
    )
    validate_manifest(
        errors,
        documents,
        requirements,
        source_dir,
    )
    validate_fixture_and_backup(errors, documents, requirements)
    validate_candidates(errors, documents, requirements)
    validate_reconciliation(errors, documents, requirements)
    validate_postflight(errors, documents, requirements)
    return sorted(set(errors))


def load_evidence(root: Path) -> dict[str, Any]:
    result = {}
    for label, name in EVIDENCE_FILES.items():
        path = root / name
        if not path.is_file():
            raise ValidationError(f"evidence file missing: {path}")
        result[label] = read_json(path)
    return result


def mutate_topology_role(
    topology: dict[str, Any],
    member: str,
    *,
    role: str | None = None,
    state: str | None = None,
) -> None:
    for row in topology.get("members", []):
        if row.get("member") != member:
            continue
        if role is not None:
            row["role"] = role
        if state is not None:
            row["state"] = state
        return
    raise ValidationError(f"mutation member missing: {member}")


def apply_mutation(name: str, bundle: dict[str, Any]) -> None:
    requirements = bundle["requirements"]
    contract = bundle["contract"]
    documents = bundle["documents"]
    preflight = documents["preflight"]
    fixture = documents["fixture"]
    inclusive = documents["inclusive"]
    exclusive = documents["exclusive"]
    reconciliation = documents["reconciliation"]
    cleanup = documents["cleanup"]

    if name == "requirements.production-data=true":
        requirements["target"]["production_data_permitted"] = True
    elif name == "requirements.managed-pgdata=true":
        requirements["risk"]["managed_pgdata_permitted"] = True
    elif name == "requirements.patroni-change=true":
        requirements["risk"]["patroni_change_permitted"] = True
    elif name == "requirements.expire=true":
        requirements["repository"]["expire_permitted"] = True
    elif name == "requirements.target-type=time":
        requirements["restore"]["target_type"] = "time"
    elif name == "requirements.exclusive=false":
        requirements["restore"]["accepted_target_exclusive"] = False
    elif name == "requirements.timeline=latest":
        requirements["restore"]["target_timeline"] = "latest"
    elif name == "requirements.archive-mode=on":
        requirements["restore"]["archive_mode"] = "on"
    elif name == "requirements.listen-addresses=*":
        requirements["restore"]["listen_addresses"] = "*"
    elif name == "contract.remove-inclusive-rejected":
        contract["states"].remove("INCLUSIVE_REJECTED")
    elif name == "contract.skip-inclusive":
        contract["transitions"].remove(
            ["WAL_ARCHIVED", "INCLUSIVE_REJECTED"]
        )
    elif name == "contract.allow-managed-pgdata":
        contract["forbidden_mutations"] = [
            row
            for row in contract["forbidden_mutations"]
            if "restore over /pg/data" not in row
        ]
    elif name == "contract.allow-expire":
        contract["forbidden_mutations"] = [
            row
            for row in contract["forbidden_mutations"]
            if "expire or delete backups" not in row
        ]
    elif name == "preflight.target=production":
        preflight["target"] = "production/pg-main"
    elif name == "preflight.primary=wrong":
        mutate_topology_role(
            preflight["topology"],
            "pg-test-1",
            role="replica",
        )
    elif name == "preflight.replica=stopped":
        mutate_topology_role(
            preflight["topology"],
            "pg-test-2",
            state="stopped",
        )
    elif name == "preflight.source-hash=wrong":
        first = next(iter(preflight["source_sha256"]))
        preflight["source_sha256"][first] = "0" * 64
    elif name == "preflight.upstream-hash=wrong":
        first = next(iter(preflight["upstream_sha256"]))
        preflight["upstream_sha256"][first]["sha256"] = "0" * 64
    elif name == "evidence.damage-xid=wrong":
        fixture["incident_boundary"]["damage_xid"] = "0"
    elif name == "evidence.backup-label=wrong":
        documents["inclusive_plan"]["backup_label"] = "wrong"
    elif name == "evidence.archive-covered=false":
        documents["backup"]["archive_covered"] = False
    elif name == "inclusive.damage-absent":
        inclusive["effective_state"]["audits"] = [
            row
            for row in inclusive["effective_state"]["audits"]
            if row.get("stage") != "damage"
        ]
    elif name == "inclusive.accepted=true":
        inclusive["accepted"] = True
    elif name == "exclusive.damage-present":
        exclusive["effective_state"]["audits"].append(
            {
                "stage": "damage",
                "xact_id": fixture["incident_boundary"]["damage_xid"],
                "wal_lsn": "0/0",
            }
        )
    elif name == "exclusive.safe-missing":
        exclusive["effective_state"]["safe_ledger_count"] = 0
    elif name == "exclusive.post-present":
        exclusive["effective_state"]["post_ledger_count"] = 100
    elif name == "reconcile.rows=999":
        reconciliation["conditional_rows_repaired"] = 999
    elif name == "reconcile.post-preserved=false":
        reconciliation["reconciled_fixture_data_loss_rows"] = 1
    elif name == "reconcile.external-dispatch=1":
        reconciliation["external_dispatch_count"] = 1
    elif name == "evidence.route-changed=true":
        documents["manifest"]["route_changed"] = True
    elif name == "cleanup.restore-root-present=true":
        cleanup["restore_prefix"]["entries"] = 1
    elif name == "evidence.production-gate=approved":
        documents["manifest"]["production_ch32_gate"] = "approved"
    else:
        raise ValidationError(f"unknown mutation: {name}")


def public_summary(
    documents: dict[str, Any],
    requirements: dict[str, Any],
) -> dict[str, Any]:
    manifest = documents["manifest"]
    preflight = documents["preflight"]
    fixture = documents["fixture"]
    backup = documents["backup"]
    inclusive = documents["inclusive"]
    exclusive = documents["exclusive"]
    reconciliation = documents["reconciliation"]
    cleanup = documents["cleanup"]
    return {
        "schema": "pg36-ch32-pitr-run-v1",
        "generated_at": manifest["completed_at"],
        "run_id": manifest["run_id"],
        "preflight_run_id": preflight["run_id"],
        "environment": {
            "target": requirements["target"]["id"],
            "cluster": requirements["target"]["cluster"],
            "postgresql": preflight["source"]["server_version"],
            "pig": str(preflight["toolchain"]["pig"]).splitlines()[0],
            "pgbackrest": preflight["toolchain"]["pgbackrest"],
            "topology": "one primary and two streaming replicas",
            "source_timeline":
                documents["source_before"]["postgres"][
                    "checkpoint_timeline"
                ],
        },
        "incident": {
            "accounts": fixture["account_count"],
            "victims": fixture["victim_count"],
            "post_target_legitimate_writes":
                fixture["post_target_count"],
            "wrong_outbox_events":
                fixture["damage_transaction"][
                    "pending_outbox_count"
                ],
            "target_type": "xid",
            "target_derived_from_source_audit": True,
            "target_identification_ms":
                fixture["target_identification_ms"],
            "external_dispatch_count": 0,
        },
        "backup": {
            "type": backup["type"],
            "label": backup["label"],
            "command_ms": backup["command_ms"],
            "check_ms": backup["check_ms"],
            "archive_covered": backup["archive_covered"],
            "retained": backup["retained"],
            "expire_executed": backup["expire_executed"],
            "logical_size_bytes": backup["info"]["size"],
            "repository_delta_bytes":
                backup["info"]["repository"]["delta"],
        },
        "candidates": {
            "inclusive": {
                "target_inclusive": True,
                "damage_present": True,
                "post_target_present": False,
                "accepted": inclusive["accepted"],
                "plan_ms":
                    documents["inclusive_plan"]["plan_ms"],
                "restore_copy_ms": inclusive["restore_copy_ms"],
                "start_to_promoted_ms":
                    inclusive["start_to_promoted_ms"],
                "validation_ms": inclusive["validation_ms"],
                "promoted_timeline":
                    inclusive["effective_state"]["timeline"],
            },
            "exclusive": {
                "target_inclusive": False,
                "safe_transaction_present": True,
                "damage_present": False,
                "post_target_present": False,
                "accepted": exclusive["accepted"],
                "plan_ms":
                    documents["exclusive_plan"]["plan_ms"],
                "restore_copy_ms": exclusive["restore_copy_ms"],
                "start_to_promoted_ms":
                    exclusive["start_to_promoted_ms"],
                "validation_ms": exclusive["validation_ms"],
                "promoted_timeline":
                    exclusive["effective_state"]["timeline"],
            },
        },
        "reconciliation": {
            "method": reconciliation["method"],
            "recovered_rows": reconciliation["recovered_rows"],
            "post_target_rows_preserved":
                reconciliation["audited_post_target_rows"],
            "wrong_outbox_canceled":
                reconciliation["wrong_outbox_canceled"],
            "raw_exclusive_missing_legitimate_writes":
                reconciliation[
                    "raw_exclusive_missing_legitimate_writes"
                ],
            "reconciled_fixture_data_loss_rows":
                reconciliation["reconciled_fixture_data_loss_rows"],
            "reconciliation_ms":
                reconciliation["reconciliation_ms"],
            "business_manifest_matches": True,
        },
        "safety": {
            "production_data": False,
            "production_traffic": False,
            "managed_pgdata_touched": False,
            "patroni_changed": False,
            "dcs_changed": False,
            "route_changed": False,
            "tcp_listener_created": False,
            "external_dispatch_count": 0,
            "business_cutover_performed": False,
            "backup_or_wal_deleted": False,
        },
        "cleanup": {
            "fixture_schema_removed":
                cleanup["fixture_schema_removed"],
            "restore_roots_removed":
                cleanup["exact_restore_roots_removed"],
            "fresh_backup_retained": cleanup["backup_retained"],
        },
        "evidence": {
            "declared_counterexamples": 32,
            "live_evidence_mutants": 32,
            "source_files_hash_bound": len(SOURCE_FILES),
            "raw_system_identifier_exported": False,
            "secret_values_exported": 0,
            "timings_are_sandbox_observations": True,
            "production_rto_claimed": False,
        },
        "decision": {
            "production_approval": None,
            "production_ch32_gate": "pending",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--negative-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        contract = read_json(
            args.source_dir / "recovery-contract.json"
        )
        negative_path = (
            args.negative_cases
            or args.source_dir / "negative-cases.json"
        )
        negative = read_json(negative_path)
        static_errors: list[str] = []
        validate_requirements(static_errors, requirements)
        validate_contract(static_errors, contract)
        validate_negative_catalog(static_errors, negative)
        source = source_hashes(args.source_dir)
        upstream = upstream_hashes(args.source_dir, requirements)

        documents: dict[str, Any] | None = None
        positive_errors = sorted(set(static_errors))
        if args.evidence_dir is not None:
            documents = load_evidence(args.evidence_dir)
            positive_errors = validate_documents(
                documents,
                requirements,
                contract,
                negative,
                args.source_dir,
            )

        negative_report: dict[str, Any] | None = None
        if args.negative_output is not None:
            if documents is None:
                negative_report = {
                    "schema": "pg36-ch32-negative-report-v1",
                    "generated_at": utc_now(),
                    "passed": len(static_errors) == 0,
                    "catalog_only": True,
                    "case_count": len(negative.get("cases", [])),
                    "known_mutations": len(EXPECTED_MUTATIONS),
                }
            else:
                results = []
                for case in negative["cases"]:
                    mutation = str(case["mutation"])
                    mutated = {
                        "requirements": copy.deepcopy(requirements),
                        "contract": copy.deepcopy(contract),
                        "negative": copy.deepcopy(negative),
                        "documents": copy.deepcopy(documents),
                    }
                    apply_mutation(mutation, mutated)
                    mutation_errors = validate_documents(
                        mutated["documents"],
                        mutated["requirements"],
                        mutated["contract"],
                        mutated["negative"],
                        args.source_dir,
                    )
                    results.append(
                        {
                            "id": case["id"],
                            "mutation": mutation,
                            "rejected": bool(mutation_errors),
                            "errors": mutation_errors,
                        }
                    )
                rejected = sum(
                    row["rejected"] is True for row in results
                )
                negative_report = {
                    "schema": "pg36-ch32-negative-report-v1",
                    "generated_at": utc_now(),
                    "passed": rejected == len(results),
                    "case_count": len(results),
                    "rejected_count": rejected,
                    "live_mutant_count": len(results),
                    "live_mutants_rejected": rejected,
                    "results": results,
                }
            write_json(args.negative_output, negative_report)

        passed = (
            len(positive_errors) == 0
            and (
                negative_report is None
                or negative_report.get("passed") is True
            )
        )
        report = {
            "schema": "pg36-ch32-validation-report-v1",
            "generated_at": utc_now(),
            "passed": passed,
            "failure_count": len(positive_errors),
            "failures": positive_errors,
            "declared_counterexamples":
                len(negative.get("cases", [])),
            "live_evidence_mutants": (
                negative_report.get("live_mutant_count", 0)
                if negative_report
                else 0
            ),
            "source_files_hash_bound": len(source),
            "source_sha256": source,
            "upstream_sha256": upstream,
            "production_ch32_gate": "pending",
        }
        write_json(args.output, report)

        if not passed:
            sys.stderr.write(
                "validation failed: "
                + ", ".join(positive_errors or ["negative suite"])
                + "\n"
            )
            return 1
        if documents is not None and args.public_summary is not None:
            write_json(
                args.public_summary,
                public_summary(documents, requirements),
            )
    except (LabError, KeyError, TypeError, ValueError, OSError) as exc:
        sys.stderr.write(f"validation failed: {exc}\n")
        return 1

    print("status=validation-ok")
    print(f"source_files_hash_bound={len(SOURCE_FILES)}")
    print(
        "declared_counterexamples="
        f"{len(negative.get('cases', []))}"
    )
    if args.evidence_dir is not None:
        print("live_evidence_mutants=32")
        print("production_ch32_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
