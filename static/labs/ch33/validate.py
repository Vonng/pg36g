#!/usr/bin/env python3
"""Validate chapter 33 contracts, evidence, and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from common import LabError, read_json, sha256_file, write_json


SOURCE_FILES = [
    "requirements.json",
    "failure-model.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "common.py",
    "capture.py",
    "private_client_service.py",
    "client_probe.py",
    "exercise.py",
    "rebuild_lab.py",
    "validate.py",
    "review.py",
    "task.sh",
]

MANAGED_FILES = [
    "before.json",
    "stop-action.json",
    "old-primary-fence.json",
    "failed.json",
    "start-action.json",
    "rejoined.json",
    "journal-projection.json",
    "client-reconciliation.json",
    "baseline-restore-action.json",
    "restored.json",
    "fixture-cleanup.json",
    "dcs-tabletop.json",
    "drill-manifest.json",
]

KNOWN_MUTATIONS = {
    "requirements.production_data=true",
    "requirements.production_traffic=true",
    "requirements.managed_reinit=true",
    "requirements.dcs_mutation=true",
    "requirements.network_partition=true",
    "requirements.hardware_fence_claim=true",
    "requirements.dcs_members=3",
    "requirements.synchronous_mode=true",
    "model.remove-failure-domain",
    "model.remove-dcs-scenario",
    "model.dcs-promotion=true",
    "model.remove-fence-invariant",
    "model.remove-basebackup-fallback",
    "evidence.before.primary-count=2",
    "evidence.before.pause=true",
    "evidence.before.system-id=split",
    "evidence.before.lag=over-budget",
    "evidence.action.host=pg-test-2",
    "evidence.action.service-stop=false",
    "evidence.fence.service-active=true",
    "evidence.fence.postmaster-alive=true",
    "evidence.failed.leader=pg-test-3",
    "evidence.failed.old-primary-writable=true",
    "evidence.failed.timeline=same",
    "evidence.rejoined.old-primary=stopped",
    "evidence.client.acked-missing=1",
    "evidence.client.duplicates=1",
    "evidence.client.unreconciled=1",
    "evidence.rewind.system-id=split",
    "evidence.rewind.divergent-marker=true",
    "evidence.basebackup.streaming=false",
    "evidence.cleanup.root-left=true",
    "evidence.production-gate=approved",
}


def fail_if(
    failures: list[str],
    condition: bool,
    message: str,
) -> None:
    if condition:
        failures.append(message)


def phase_members(phase: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = phase.get("patroni", {}).get("members", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }


def primary_names(phase: dict[str, Any]) -> list[str]:
    return [
        name
        for name, row in phase_members(phase).items()
        if row.get("role") == "primary"
    ]


def primary_timeline(
    phase: dict[str, Any],
    leader: str,
) -> int:
    return int(phase_members(phase)[leader]["timeline"])


def validate_requirements(
    failures: list[str],
    value: dict[str, Any],
) -> None:
    fail_if(
        failures,
        value.get("schema") != "pg36-ch33-failover-requirements-v1",
        "requirements schema drifted",
    )
    target = value.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("cluster") != "pg-test"
        or target.get("initial_primary") != "pg-test-1"
        or target.get("postgresql_major") != 18
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False,
        "target identity or production boundary drifted",
    )
    fail_if(
        failures,
        set(value.get("members", {}))
        != {"pg-test-1", "pg-test-2", "pg-test-3"},
        "managed member set drifted",
    )
    managed = value.get("managed_failover", {})
    fail_if(
        failures,
        managed.get("fault") != "controlled-patroni-service-stop"
        or set(managed.get("eligible_candidates", []))
        != {"pg-test-2", "pg-test-3"}
        or managed.get("candidate_selection")
        != "automatic-Patroni-election-no-forced-candidate"
        or managed.get(
            "old_primary_must_be_process_fenced_before_candidate_acceptance"
        )
        is not True
        or managed.get(
            "automatic_rejoin_must_stream_before_baseline_restore"
        )
        is not True,
        "managed failover contract drifted",
    )
    policy = value.get("expected_dynamic_policy", {})
    fail_if(
        failures,
        policy.get("ttl_seconds") != 30
        or policy.get("loop_wait_seconds") != 5
        or policy.get("retry_timeout_seconds") != 10
        or policy.get("maximum_lag_on_failover_bytes") != 1048576
        or policy.get("synchronous_mode") is not False
        or policy.get("synchronous_mode_strict") is not False
        or policy.get("failsafe_mode") is not True
        or policy.get("use_pg_rewind") is not True
        or policy.get("use_slots") is not True
        or policy.get("watchdog_mode") != "off"
        or policy.get("dcs_kind") != "etcd3"
        or policy.get("dcs_member_count") != 1,
        "observed Patroni policy contract drifted",
    )
    rebuild = value.get("rebuild_lab", {})
    fail_if(
        failures,
        rebuild.get("address") != "10.10.10.13"
        or rebuild.get("root_prefix") != "/tmp/pg36-ch33-rebuild"
        or rebuild.get("listen_addresses") != ""
        or rebuild.get("data_checksums") is not True
        or rebuild.get("never_run_divergent_primaries_concurrently")
        is not True
        or rebuild.get("exact_cleanup_required") is not True,
        "disposable rebuild contract drifted",
    )
    tabletop = value.get("dcs_tabletop", {})
    fail_if(
        failures,
        tabletop.get("scenario_count") != 6
        or tabletop.get("draw_count") != 1
        or tabletop.get("live_dcs_fault_injection") is not False
        or tabletop.get("live_network_partition_injection") is not False
        or tabletop.get(
            "decision_must_not_reset_election_state_blindly"
        )
        is not True,
        "DCS tabletop boundary drifted",
    )
    risk = value.get("risk", {})
    fail_if(
        failures,
        risk.get("managed_exercise")
        != "L2-controlled-service-stop-start-and-planned-baseline-restore"
        or risk.get("rebuild_exercise")
        != "L2-disposable-local-postgresql-directories"
        or any(
            risk.get(key) is not False
            for key in (
                "managed_pgdata_delete_permitted",
                "managed_reinit_permitted",
                "patroni_dynamic_config_change_permitted",
                "dcs_mutation_permitted",
                "network_partition_permitted",
                "route_change_permitted",
                "hardware_fencing_claim_permitted",
                "production_failover_claim_permitted",
            )
        ),
        "risk boundary drifted",
    )
    acceptance = value.get("acceptance", {})
    fail_if(
        failures,
        acceptance.get("production_ch33_gate") != "pending"
        or acceptance.get("forward_timeline_must_advance") is not True
        or acceptance.get("all_acknowledged_tokens_must_exist_once")
        is not True
        or acceptance.get("rebuild_divergent_marker_must_disappear")
        is not True,
        "acceptance gate drifted",
    )
    fail_if(
        failures,
        len(value.get("exceptions", [])) != 6,
        "declared sandbox exceptions drifted",
    )


def validate_model(
    failures: list[str],
    value: dict[str, Any],
) -> None:
    fail_if(
        failures,
        value.get("schema") != "pg36-ch33-failure-model-v1",
        "failure model schema drifted",
    )
    domains = value.get("failure_domains", [])
    fail_if(
        failures,
        not isinstance(domains, list)
        or len(domains) != 5
        or len({row.get("id") for row in domains}) != 5
        or any(
            not row.get("signals")
            or not row.get("safe_first_action")
            or not row.get("not_proven")
            for row in domains
        ),
        "failure-domain decision table drifted",
    )
    scenarios = value.get("dcs_scenarios", [])
    fail_if(
        failures,
        not isinstance(scenarios, list)
        or len(scenarios) != 6
        or len({row.get("id") for row in scenarios}) != 6
        or any(
            not row.get("required_evidence")
            or not row.get("expected_decision")
            or row.get("promotion_permitted") is True
            for row in scenarios
        ),
        "DCS scenario library permits a blind promotion",
    )
    invariants = value.get("promotion_invariants", [])
    fail_if(
        failures,
        len(invariants) != 5
        or not any("fence" in str(row).lower() for row in invariants)
        or not any(
            "system identifier" in str(row).lower()
            and "timeline" in str(row).lower()
            for row in invariants
        ),
        "promotion invariants are incomplete",
    )
    decisions = value.get("rebuild_decision", [])
    fail_if(
        failures,
        len(decisions) != 3
        or not any("pg_rewind" in str(row.get("action")) for row in decisions)
        or not any(
            "fresh base backup" in str(row.get("action"))
            for row in decisions
        )
        or not any(
            "stop" in str(row.get("action")).lower()
            for row in decisions
        ),
        "rebuild fallback ladder is incomplete",
    )


def validate_healthy_phase(
    failures: list[str],
    phase: dict[str, Any],
    leader: str,
    label: str,
) -> None:
    members = phase_members(phase)
    fail_if(
        failures,
        set(members) != {"pg-test-1", "pg-test-2", "pg-test-3"}
        or primary_names(phase) != [leader]
        or members.get(leader, {}).get("state") != "running"
        or any(
            row.get("role") != "replica"
            or row.get("state") != "streaming"
            for name, row in members.items()
            if name != leader
        ),
        f"{label} topology is not one primary and two streaming replicas",
    )


def validate_evidence(
    failures: list[str],
    bundle: dict[str, Any],
    source_dir: Path,
) -> None:
    managed = bundle["managed"]
    requirements = bundle["requirements"]
    before = managed["before.json"]
    failed = managed["failed.json"]
    rejoined = managed["rejoined.json"]
    restored = managed["restored.json"]
    selected = failed.get("selected_leader")
    eligible = set(
        requirements["managed_failover"]["eligible_candidates"]
    )

    validate_healthy_phase(
        failures, before, "pg-test-1", "preflight"
    )
    policy = before.get("dynamic_policy", {})
    expected = requirements["expected_dynamic_policy"]
    fail_if(
        failures,
        policy.get("pause") is not False
        or policy.get("ttl") != expected["ttl_seconds"]
        or policy.get("loop_wait") != expected["loop_wait_seconds"]
        or policy.get("retry_timeout") != expected["retry_timeout_seconds"]
        or policy.get("maximum_lag_on_failover")
        != expected["maximum_lag_on_failover_bytes"]
        or policy.get("synchronous_mode") is not False
        or policy.get("failsafe_mode") is not True,
        "live Patroni policy drifted",
    )
    before_sql = before.get("postgres", {})
    before_ids = {
        row.get("system_identifier")
        for row in before_sql.values()
    }
    fail_if(
        failures,
        len(before_sql) != 3
        or any(row.get("available") is not True for row in before_sql.values())
        or len(before_ids) != 1
        or before_sql.get("pg-test-1", {}).get("in_recovery") is not False
        or any(
            before_sql.get(name, {}).get("in_recovery") is not True
            for name in ("pg-test-2", "pg-test-3")
        ),
        "preflight SQL lineage or roles drifted",
    )
    senders = before_sql.get("pg-test-1", {}).get("senders", [])
    fail_if(
        failures,
        len(senders) != 2
        or any(
            row.get("state") != "streaming"
            or row.get("replay_gap_bytes") is None
            or int(row["replay_gap_bytes"])
            > expected["maximum_lag_on_failover_bytes"]
            for row in senders
        ),
        "preflight replay lag is outside policy",
    )

    stop = managed["stop-action.json"]
    fail_if(
        failures,
        stop.get("kind") != "controlled-patroni-stop"
        or stop.get("member") != "pg-test-1"
        or stop.get("address") != "10.10.10.11"
        or stop.get("return_code") != 0,
        "controlled service-stop action drifted",
    )
    fence = managed["old-primary-fence.json"]
    fail_if(
        failures,
        fence.get("member_name") != "pg-test-1"
        or fence.get("service_active") is not False
        or fence.get("postmaster_alive") is not False
        or fence.get("patroni_rest_reachable") is not False
        or int(fence.get("verified_monotonic_ns", 0))
        <= int(stop.get("started_monotonic_ns", 0)),
        "old-primary process fence is incomplete",
    )

    failed_members = phase_members(failed)
    other = eligible - {selected}
    fail_if(
        failures,
        selected not in eligible
        or primary_names(failed) != [selected]
        or failed_members.get(selected, {}).get("state") != "running"
        or any(
            failed_members.get(name, {}).get("role") != "replica"
            or failed_members.get(name, {}).get("state") != "streaming"
            for name in other
        )
        or failed.get("postgres", {})
        .get("pg-test-1", {})
        .get("available")
        is not False
        or int(fence.get("verified_monotonic_ns", 0))
        > int(failed.get("stable_monotonic_ns", 0)),
        "automatic failover topology or fence ordering drifted",
    )
    initial_timeline = primary_timeline(before, "pg-test-1")
    failover_timeline = primary_timeline(failed, str(selected))
    fail_if(
        failures,
        failover_timeline <= initial_timeline,
        "automatic failover did not advance timeline",
    )

    validate_healthy_phase(
        failures, rejoined, str(selected), "rejoined"
    )
    fail_if(
        failures,
        rejoined.get("postgres", {})
        .get("pg-test-1", {})
        .get("in_recovery")
        is not True,
        "old primary did not rejoin as a SQL standby",
    )
    start = managed["start-action.json"]
    fail_if(
        failures,
        start.get("kind") != "controlled-patroni-start"
        or start.get("member") != "pg-test-1"
        or start.get("return_code") != 0
        or int(rejoined.get("stable_monotonic_ns", 0))
        <= int(start.get("started_monotonic_ns", 0)),
        "old-primary start/rejoin evidence drifted",
    )
    journal = managed["journal-projection.json"]
    fail_if(
        failures,
        journal.get("return_code") != 0
        or journal.get("raw_log_exported") is not False
        or not isinstance(journal.get("sha256"), str)
        or len(journal.get("sha256", "")) != 64,
        "journal projection is incomplete or exports raw logs",
    )

    client = managed["client-reconciliation.json"]
    probe = requirements["client_probe"]
    fail_if(
        failures,
        client.get("passed") is not True
        or int(client.get("acknowledged", 0))
        < probe["minimum_acknowledged_attempts"]
        or client.get("acknowledged_missing") != 0
        or client.get("duplicate_tokens") != 0
        or client.get("unreconciled_unknown_outcomes") != 0
        or float(client.get("maximum_ack_gap_ms", 10**9))
        > probe["maximum_observed_write_gap_ms"]
        or client.get("initial_timeline") != initial_timeline
        or client.get("failover_timeline") != failover_timeline
        or int(client.get("old_timeline_acknowledged", 0)) <= 0
        or int(client.get("new_primary_acknowledged", 0)) <= 0
        or client.get("persisted_rows")
        < client.get("acknowledged"),
        "client write/reconciliation evidence drifted",
    )

    restore_action = managed["baseline-restore-action.json"]
    fail_if(
        failures,
        restore_action.get("kind") != "planned-switchover"
        or restore_action.get("leader") != selected
        or restore_action.get("candidate") != "pg-test-1"
        or restore_action.get("return_code") != 0,
        "baseline restore action drifted",
    )
    validate_healthy_phase(
        failures, restored, "pg-test-1", "restored"
    )
    restored_timeline = primary_timeline(restored, "pg-test-1")
    fail_if(
        failures,
        restored_timeline <= failover_timeline,
        "baseline switchover did not advance timeline",
    )
    restored_ids = {
        row.get("system_identifier")
        for row in restored.get("postgres", {}).values()
    }
    fail_if(
        failures,
        restored_ids != before_ids,
        "managed system identifier changed",
    )
    cleanup = managed["fixture-cleanup.json"]
    fail_if(
        failures,
        cleanup.get("marker_matched") is not True
        or cleanup.get("schema_removed") is not True
        or cleanup.get("external_dispatch_count") != 0,
        "managed fixture cleanup drifted",
    )
    tabletop = managed["dcs-tabletop.json"]
    scenario_ids = {
        row["id"] for row in bundle["model"]["dcs_scenarios"]
    }
    fail_if(
        failures,
        tabletop.get("scenario_count") != 6
        or tabletop.get("drawn", {}).get("id") not in scenario_ids
        or tabletop.get("live_dcs_fault_injected") is not False
        or tabletop.get("live_network_partition_injected") is not False
        or tabletop.get("leader_key_deleted") is not False
        or tabletop.get("decision_only") is not True
        or tabletop.get("production_action_authorized") is not False,
        "DCS decision exercise crossed the no-mutation boundary",
    )

    manifest = managed["drill-manifest.json"]
    run_id = manifest.get("run_id")
    fail_if(
        failures,
        manifest.get("schema") != "pg36-ch33-drill-manifest-v1"
        or manifest.get("target") != "pg36-l2-vagrant/pg-test"
        or manifest.get("production_approval") is not False
        or manifest.get("secret_values_exported") != 0
        or any(
            document.get("run_id") != run_id
            for document in (
                client,
                cleanup,
                tabletop,
            )
        ),
        "managed run identity binding drifted",
    )
    source_hashes = manifest.get("source_sha256", {})
    fail_if(
        failures,
        set(source_hashes) != set(SOURCE_FILES)
        or any(
            source_hashes.get(name)
            != sha256_file(source_dir / name)
            for name in SOURCE_FILES
        ),
        "managed evidence source hashes drifted",
    )

    rebuild = bundle["rebuild"]
    fail_if(
        failures,
        rebuild.get("schema") != "pg36-ch33-rebuild-evidence-v1"
        or rebuild.get("run_id") != run_id
        or rebuild.get("managed_pgdata_touched") is not False
        or rebuild.get("patroni_registered") is not False
        or rebuild.get("dcs_changed") is not False
        or rebuild.get("route_changed") is not False
        or rebuild.get("concurrent_divergent_primaries") is not False
        or rebuild.get("listen_addresses") != "",
        "disposable rebuild safety boundary drifted",
    )
    rewind_target = rebuild.get("rewind_target", {})
    basebackup_target = rebuild.get("basebackup_target", {})
    fail_if(
        failures,
        rebuild.get("same_system_identifier") is not True
        or rebuild.get("timeline_diverged") is not True
        or rebuild.get("rewind_target_has_new_primary") is not True
        or rebuild.get("rewind_target_has_old_divergent") is not False
        or set(rewind_target.get("markers", []))
        != {"base", "new-primary", "after-divergence"}
        or rewind_target.get("in_recovery") is not True
        or rewind_target.get("receiver_status") != "streaming",
        "pg_rewind lineage validation drifted",
    )
    fail_if(
        failures,
        rebuild.get("basebackup_target_streaming") is not True
        or basebackup_target.get("in_recovery") is not True
        or basebackup_target.get("receiver_status") != "streaming"
        or set(basebackup_target.get("markers", []))
        != {"base", "new-primary", "after-divergence"},
        "fresh basebackup validation drifted",
    )
    rebuild_cleanup = rebuild.get("cleanup", {})
    fail_if(
        failures,
        rebuild_cleanup.get("root_exists_after") is not False
        or rebuild_cleanup.get("running_instances_after") != []
        or rebuild_cleanup.get("exact_marker_matched") is not True,
        "disposable rebuild cleanup drifted",
    )
    fail_if(
        failures,
        bundle.get("production_gate") != "pending",
        "production chapter gate was opened",
    )


def load_bundle(
    source_dir: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    managed_dir = evidence_dir / "managed"
    missing = [
        name
        for name in MANAGED_FILES
        if not (managed_dir / name).is_file()
    ]
    if missing or not (evidence_dir / "rebuild.json").is_file():
        raise LabError(
            "incomplete chapter 33 evidence bundle: "
            + ", ".join(missing or ["rebuild.json"])
        )
    return {
        "requirements": read_json(source_dir / "requirements.json"),
        "model": read_json(source_dir / "failure-model.json"),
        "managed": {
            name: read_json(managed_dir / name)
            for name in MANAGED_FILES
        },
        "rebuild": read_json(evidence_dir / "rebuild.json"),
        "production_gate": "pending",
    }


def mutate(bundle: dict[str, Any], name: str) -> None:
    requirements = bundle["requirements"]
    model = bundle["model"]
    managed = bundle["managed"]
    before = managed["before.json"]
    failed = managed["failed.json"]
    rebuild = bundle["rebuild"]

    if name == "requirements.production_data=true":
        requirements["target"]["production_data_permitted"] = True
    elif name == "requirements.production_traffic=true":
        requirements["target"]["production_traffic_permitted"] = True
    elif name == "requirements.managed_reinit=true":
        requirements["risk"]["managed_reinit_permitted"] = True
    elif name == "requirements.dcs_mutation=true":
        requirements["risk"]["dcs_mutation_permitted"] = True
    elif name == "requirements.network_partition=true":
        requirements["risk"]["network_partition_permitted"] = True
    elif name == "requirements.hardware_fence_claim=true":
        requirements["risk"]["hardware_fencing_claim_permitted"] = True
    elif name == "requirements.dcs_members=3":
        requirements["expected_dynamic_policy"]["dcs_member_count"] = 3
    elif name == "requirements.synchronous_mode=true":
        requirements["expected_dynamic_policy"]["synchronous_mode"] = True
    elif name == "model.remove-failure-domain":
        model["failure_domains"].pop()
    elif name == "model.remove-dcs-scenario":
        model["dcs_scenarios"].pop()
    elif name == "model.dcs-promotion=true":
        model["dcs_scenarios"][0]["promotion_permitted"] = True
    elif name == "model.remove-fence-invariant":
        model["promotion_invariants"] = [
            row
            for row in model["promotion_invariants"]
            if "fence" not in row.lower()
        ]
    elif name == "model.remove-basebackup-fallback":
        model["rebuild_decision"] = [
            row
            for row in model["rebuild_decision"]
            if "fresh base backup" not in row["action"]
        ]
    elif name == "evidence.before.primary-count=2":
        members = phase_members(before)
        members["pg-test-2"]["role"] = "primary"
        members["pg-test-2"]["state"] = "running"
    elif name == "evidence.before.pause=true":
        before["dynamic_policy"]["pause"] = True
    elif name == "evidence.before.system-id=split":
        before["postgres"]["pg-test-2"]["system_identifier"] = "split"
    elif name == "evidence.before.lag=over-budget":
        before["postgres"]["pg-test-1"]["senders"][0][
            "replay_gap_bytes"
        ] = 1048577
    elif name == "evidence.action.host=pg-test-2":
        managed["stop-action.json"]["member"] = "pg-test-2"
    elif name == "evidence.action.service-stop=false":
        managed["stop-action.json"]["kind"] = "observation-only"
    elif name == "evidence.fence.service-active=true":
        managed["old-primary-fence.json"]["service_active"] = True
    elif name == "evidence.fence.postmaster-alive=true":
        managed["old-primary-fence.json"]["postmaster_alive"] = True
    elif name == "evidence.failed.leader=pg-test-3":
        selected = failed["selected_leader"]
        failed["selected_leader"] = (
            "pg-test-2" if selected == "pg-test-3" else "pg-test-3"
        )
    elif name == "evidence.failed.old-primary-writable=true":
        failed["postgres"]["pg-test-1"] = {
            "available": True,
            "in_recovery": False,
        }
    elif name == "evidence.failed.timeline=same":
        leader = failed["selected_leader"]
        phase_members(failed)[leader]["timeline"] = primary_timeline(
            before, "pg-test-1"
        )
    elif name == "evidence.rejoined.old-primary=stopped":
        phase_members(managed["rejoined.json"])["pg-test-1"][
            "state"
        ] = "stopped"
    elif name == "evidence.client.acked-missing=1":
        managed["client-reconciliation.json"][
            "acknowledged_missing"
        ] = 1
    elif name == "evidence.client.duplicates=1":
        managed["client-reconciliation.json"]["duplicate_tokens"] = 1
    elif name == "evidence.client.unreconciled=1":
        managed["client-reconciliation.json"][
            "unreconciled_unknown_outcomes"
        ] = 1
    elif name == "evidence.rewind.system-id=split":
        rebuild["rewind_target"]["system_identifier"] = "split"
        rebuild["same_system_identifier"] = False
    elif name == "evidence.rewind.divergent-marker=true":
        rebuild["rewind_target_has_old_divergent"] = True
        rebuild["rewind_target"]["markers"].append(
            "old-primary-divergent"
        )
    elif name == "evidence.basebackup.streaming=false":
        rebuild["basebackup_target_streaming"] = False
    elif name == "evidence.cleanup.root-left=true":
        rebuild["cleanup"]["root_exists_after"] = True
    elif name == "evidence.production-gate=approved":
        bundle["production_gate"] = "approved"
    else:
        raise LabError(f"unknown mutation: {name}")


def validate_bundle(
    bundle: dict[str, Any],
    source_dir: Path,
) -> list[str]:
    failures: list[str] = []
    validate_requirements(failures, bundle["requirements"])
    validate_model(failures, bundle["model"])
    validate_evidence(failures, bundle, source_dir)
    return failures


def build_public_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    managed = bundle["managed"]
    requirements = bundle["requirements"]
    before = managed["before.json"]
    failed = managed["failed.json"]
    rejoined = managed["rejoined.json"]
    restored = managed["restored.json"]
    stop = managed["stop-action.json"]
    start = managed["start-action.json"]
    fence = managed["old-primary-fence.json"]
    client = managed["client-reconciliation.json"]
    restore = managed["baseline-restore-action.json"]
    manifest = managed["drill-manifest.json"]
    rebuild = bundle["rebuild"]
    selected = str(failed["selected_leader"])
    return {
        "schema": "pg36-ch33-reference-run-v1",
        "captured_at": manifest["captured_at"],
        "run_id": manifest["run_id"],
        "target": manifest["target"],
        "environment": {
            "cluster": "pg-test",
            "postgresql": requirements["target"][
                "postgresql_observed"
            ],
            "patroni": requirements["target"]["patroni_observed"],
            "pig": requirements["target"]["pig_observed"],
            "members": 3,
            "dcs_kind": "etcd3",
            "dcs_members": 1,
            "watchdog_mode": "off",
            "synchronous_mode": False,
            "failsafe_mode": True,
        },
        "managed_failover": {
            "fault": "controlled-patroni-service-stop",
            "old_primary": "pg-test-1",
            "selected_candidate": selected,
            "eligible_candidates": ["pg-test-2", "pg-test-3"],
            "candidate_forced": False,
            "initial_timeline": primary_timeline(
                before, "pg-test-1"
            ),
            "failover_timeline": primary_timeline(failed, selected),
            "restored_timeline": primary_timeline(
                restored, "pg-test-1"
            ),
            "service_stop_ms": stop["duration_ms"],
            "fence_from_action_start_ms": (
                int(fence["verified_monotonic_ns"])
                - int(stop["started_monotonic_ns"])
            )
            / 1_000_000,
            "control_plane_failover_ms": client[
                "control_plane_failover_ms"
            ],
            "old_primary_rejoin_ms": (
                int(rejoined["stable_monotonic_ns"])
                - int(start["started_monotonic_ns"])
            )
            / 1_000_000,
            "planned_baseline_restore_ms": restore["duration_ms"],
            "old_primary_rejoined_streaming": True,
            "baseline_restored_to": "pg-test-1",
        },
        "client": {
            key: client[key]
            for key in (
                "attempts",
                "acknowledged",
                "unknown",
                "persisted_rows",
                "acknowledged_missing",
                "duplicate_tokens",
                "unreconciled_unknown_outcomes",
                "maximum_ack_gap_ms",
                "measurement_resolution_ms",
                "old_timeline_acknowledged",
                "new_primary_acknowledged",
                "backend_attribution",
            )
        },
        "dcs_tabletop": {
            "scenario_library": 6,
            "drawn_scenario": managed["dcs-tabletop.json"][
                "drawn"
            ]["id"],
            "live_dcs_fault_injected": False,
            "live_network_partition_injected": False,
            "decision_only": True,
        },
        "rebuild": {
            "postgresql": rebuild["postgresql_version"],
            "same_system_identifier": rebuild[
                "same_system_identifier"
            ],
            "timeline_diverged": rebuild["timeline_diverged"],
            "pg_rewind_ms": rebuild["rewind"]["duration_ms"],
            "rewind_target_streaming": (
                rebuild["rewind_target"]["receiver_status"]
                == "streaming"
            ),
            "rewind_new_branch_markers": rebuild[
                "rewind_target_has_new_primary"
            ],
            "rewind_old_divergent_marker": rebuild[
                "rewind_target_has_old_divergent"
            ],
            "fresh_basebackup_ms": rebuild["fresh_basebackup"][
                "duration_ms"
            ],
            "fresh_basebackup_streaming": rebuild[
                "basebackup_target_streaming"
            ],
            "temporary_root_removed": (
                rebuild["cleanup"]["root_exists_after"] is False
            ),
        },
        "safety": {
            "old_primary_process_fenced_before_acceptance": True,
            "managed_pgdata_deleted": False,
            "managed_reinit_executed": False,
            "dcs_changed": False,
            "network_partition_injected": False,
            "route_changed": False,
            "hardware_fence_claimed": False,
            "raw_patroni_log_exported": False,
            "secret_values_exported": 0,
            "fixture_schema_removed": managed[
                "fixture-cleanup.json"
            ]["schema_removed"],
            "external_dispatch_count": 0,
        },
        "validation": {
            "declared_counterexamples_rejected": 33,
            "live_evidence_mutants_rejected": 33,
            "source_files_hash_bound": len(SOURCE_FILES),
        },
        "decision": {
            "result": (
                "controlled-process-failover-rejoin-and-"
                "disposable-rebuild-demonstrated"
            ),
            "production_approval": None,
            "production_ch33_gate": "pending",
        },
        "claims_not_made": [
            "host power loss, storage failure, or asymmetric network partition was injected",
            "the single-member DCS proves quorum availability",
            "hardware watchdog fencing was exercised",
            "asynchronous replication guarantees zero production RPO",
            "managed patronictl reinit was executed",
            "sandbox timings are a production RTO SLO"
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        model = read_json(args.source_dir / "failure-model.json")
        negative = read_json(args.negative_cases)
        cases = negative.get("cases", [])
        mutations = [
            row.get("mutation")
            for row in cases
            if isinstance(row, dict)
        ]
        source_failures: list[str] = []
        validate_requirements(source_failures, requirements)
        validate_model(source_failures, model)
        fail_if(
            source_failures,
            negative.get("schema")
            != "pg36-ch33-negative-cases-v1"
            or len(cases) != 33
            or len(set(mutations)) != 33
            or set(mutations) != KNOWN_MUTATIONS,
            "negative-case declaration drifted",
        )
        for name in SOURCE_FILES:
            fail_if(
                source_failures,
                not (args.source_dir / name).is_file(),
                f"source file missing: {name}",
            )

        bundle: dict[str, Any] | None = None
        evidence_failures: list[str] = []
        rejected: list[dict[str, Any]] = []
        if args.evidence_dir is not None:
            bundle = load_bundle(args.source_dir, args.evidence_dir)
            evidence_failures = validate_bundle(bundle, args.source_dir)
            for case in cases:
                candidate = copy.deepcopy(bundle)
                mutation = str(case["mutation"])
                mutate(candidate, mutation)
                failures = validate_bundle(candidate, args.source_dir)
                rejected.append(
                    {
                        "id": case["id"],
                        "mutation": mutation,
                        "rejected": bool(failures),
                        "first_failure": (
                            failures[0] if failures else None
                        ),
                    }
                )
                if not failures:
                    evidence_failures.append(
                        f"mutant survived: {mutation}"
                    )

        failures = source_failures + evidence_failures
        report = {
            "schema": "pg36-ch33-validation-report-v1",
            "passed": not failures,
            "failure_count": len(failures),
            "failures": failures,
            "declared_counterexamples": len(cases),
            "live_evidence_mutants": len(rejected),
            "live_evidence_mutants_rejected": sum(
                row["rejected"] for row in rejected
            ),
            "source_files_hash_bound": len(SOURCE_FILES),
            "production_ch33_gate": "pending",
        }
        if bundle is not None:
            failed = bundle["managed"]["failed.json"]
            selected = str(failed["selected_leader"])
            report.update(
                {
                    "run_id": bundle["managed"][
                        "drill-manifest.json"
                    ]["run_id"],
                    "selected_candidate": selected,
                    "initial_timeline": primary_timeline(
                        bundle["managed"]["before.json"],
                        "pg-test-1",
                    ),
                    "failover_timeline": primary_timeline(
                        failed, selected
                    ),
                    "restored_timeline": primary_timeline(
                        bundle["managed"]["restored.json"],
                        "pg-test-1",
                    ),
                }
            )
        write_json(args.output, report)
        if args.negative_output is not None:
            write_json(
                args.negative_output,
                {
                    "schema": "pg36-ch33-negative-report-v1",
                    "passed": (
                        len(rejected) == 33
                        and all(row["rejected"] for row in rejected)
                    ),
                    "case_count": len(cases),
                    "rejected_count": sum(
                        row["rejected"] for row in rejected
                    ),
                    "live_mutant_count": len(rejected),
                    "live_mutants_rejected": sum(
                        row["rejected"] for row in rejected
                    ),
                    "results": rejected,
                },
            )
        if bundle is not None and args.public_summary is not None:
            write_json(
                args.public_summary,
                build_public_summary(bundle),
            )
    except (KeyError, TypeError, OSError, LabError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    if failures:
        print(
            "validation failed: " + "; ".join(failures),
            file=sys.stderr,
        )
        return 1
    print("status=validation-ok")
    print(f"declared_counterexamples={len(cases)}")
    print(f"live_evidence_mutants={len(rejected)}")
    print(f"source_files_hash_bound={len(SOURCE_FILES)}")
    print("production_ch33_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
