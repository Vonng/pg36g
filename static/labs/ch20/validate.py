#!/usr/bin/env python3
"""Validate chapter 20 planned-switchover evidence and counterexamples."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any


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
        "forward_action": read_json(path / "forward-action.json"),
        "restore_action": read_json(path / "restore-action.json"),
        "reconciliation": read_json(path / "reconciliation.json"),
        "phases": {
            phase: read_json(path / "phases" / f"{phase}.json")
            for phase in (
                "before",
                "pre-switch",
                "after-forward",
                "restored",
            )
        },
        "client_probe_stderr": (
            path / "client-probe.stderr"
        ).read_text(encoding="utf-8"),
    }


def expected_host_map(requirements: dict[str, Any]) -> dict[str, str]:
    return {
        name: str(contract["address"])
        for name, contract in requirements["members"].items()
    }


def index_members(phase: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = phase.get("patroni", {}).get("members")
    if not isinstance(rows, list):
        fail("E_TOPOLOGY", "Patroni member list is missing")
    result = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(result) != len(rows):
        fail("E_TOPOLOGY", "Patroni member names are missing or duplicated")
    return result


def validate_documents(
    requirements: dict[str, Any],
    failure_model: dict[str, Any],
) -> None:
    if (
        requirements.get("schema") != "pg36-ch20-ha-requirements-v1"
        or requirements.get("release") != "1.0-sandbox"
        or "not-production-slo"
        not in str(requirements.get("status", ""))
    ):
        fail("E_SCHEMA", "requirements identity drifted")
    if (
        failure_model.get("schema") != "pg36-ch20-failure-model-v1"
        or failure_model.get("release") != requirements["release"]
    ):
        fail("E_SCHEMA", "failure model identity drifted")
    target = requirements.get("target", {})
    if (
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("pigsty_release") != "v4.4.0"
        or target.get("postgresql_major") != 18
        or target.get("patroni_version") != "4.1.3"
        or target.get("cluster") != "pg-test"
    ):
        fail("E_SCHEMA", "target identity drifted")
    if (
        target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or requirements.get("decision_boundary", {}).get(
            "production_ch20_gate"
        )
        != "pending"
    ):
        fail("E_PRODUCTION_CLAIM", "sandbox crossed the production boundary")
    scenarios = failure_model.get("scenarios", [])
    observed = [
        row
        for row in scenarios
        if row.get("evidence_state") == "observed-by-this-lab"
    ]
    if (
        len(scenarios) != 9
        or len(observed) != 1
        or observed[0].get("id") != "planned-primary-maintenance"
        or not failure_model.get("prohibited_inference")
    ):
        fail("E_FAILURE_MODEL", "failure model overclaims or lost scenarios")

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
    ]
    if requirements.get("required_exception_ids") != expected_exceptions:
        fail("E_EXCEPTION", "required exception set drifted")
    if [row.get("id") for row in requirements.get("exceptions", [])] != (
        expected_exceptions[6:]
    ):
        fail("E_EXCEPTION", "chapter-20 exception details drifted")


def validate_manifest(
    requirements: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    run_id = str(manifest.get("run_id", ""))
    try:
        parsed_run_id = uuid.UUID(run_id)
    except ValueError:
        fail("E_MANIFEST", "drill run_id is not a UUID")
    if (
        manifest.get("schema") != "pg36-ch20-drill-manifest-v1"
        or manifest.get("release") != requirements["release"]
        or manifest.get("target") != requirements["target"]["id"]
        or manifest.get("mode")
        != "planned-switchover-and-planned-baseline-restore"
        or manifest.get("production_approval") is not False
        or manifest.get("unplanned_failure_injected") is not False
        or manifest.get("secret_values_exported") != 0
        or str(parsed_run_id) != run_id
        or not isinstance(manifest.get("source_sha256"), dict)
        or not manifest.get("source_sha256")
        or any(
            not isinstance(name, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            for name, digest in manifest["source_sha256"].items()
        )
    ):
        fail("E_MANIFEST", "drill manifest identity or authority drifted")


def validate_policy(
    requirements: dict[str, Any],
    phase: dict[str, Any],
) -> None:
    expected = requirements["expected_dynamic_policy"]
    actual = phase.get("dynamic_policy", {})
    checks = {
        "ttl": expected["ttl_seconds"],
        "loop_wait": expected["loop_wait_seconds"],
        "retry_timeout": expected["retry_timeout_seconds"],
        "maximum_lag_on_failover": expected[
            "maximum_lag_on_failover_bytes"
        ],
        "synchronous_mode": expected["synchronous_mode"],
        "synchronous_mode_strict": expected["synchronous_mode_strict"],
        "failsafe_mode": expected["failsafe_mode"],
        "pause": False,
    }
    if any(actual.get(key) != value for key, value in checks.items()):
        fail("E_POLICY", f"Patroni policy drifted in {phase.get('phase')}")
    postgresql = actual.get("postgresql", {})
    if (
        postgresql.get("use_pg_rewind") is not expected["use_pg_rewind"]
        or postgresql.get("use_slots") is not expected["use_slots"]
    ):
        fail("E_POLICY", "rewind or slot policy drifted")

    local = phase.get("local_patroni", {})
    host_map = expected_host_map(requirements)
    if set(local) != set(host_map.values()):
        fail("E_POLICY", "local Patroni evidence host set drifted")
    for member, host in host_map.items():
        row = local[host]
        if (
            row.get("scope") != "pg-test"
            or row.get("member_name") != member
            or row.get("patroni_version")
            != requirements["target"]["patroni_version"]
            or row.get("watchdog", {}).get("mode")
            != expected["watchdog_mode"]
            or row.get("dcs_kind") != expected["dcs_kind"]
            or row.get("dcs_endpoint_count")
            != expected["dcs_member_count"]
        ):
            fail("E_POLICY", f"local Patroni policy drifted for {member}")


def validate_phase(
    requirements: dict[str, Any],
    phase_name: str,
    phase: dict[str, Any],
    expected_leader: str,
) -> int:
    if (
        phase.get("schema") != "pg36-ch20-ha-phase-v1"
        or phase.get("release") != requirements["release"]
        or phase.get("phase") != phase_name
        or phase.get("target") != requirements["target"]["id"]
    ):
        fail("E_SCHEMA", f"phase identity drifted for {phase_name}")
    validate_policy(requirements, phase)

    host_map = expected_host_map(requirements)
    members = index_members(phase)
    if set(members) != set(host_map):
        fail("E_TOPOLOGY", f"member set drifted in {phase_name}")
    for name, row in members.items():
        expected_role = "primary" if name == expected_leader else "replica"
        expected_state = "running" if name == expected_leader else "streaming"
        if (
            row.get("host") != host_map[name]
            or row.get("role") != expected_role
            or row.get("state") != expected_state
        ):
            fail("E_TOPOLOGY", f"Patroni topology drifted for {name}")
    timelines = {int(row["timeline"]) for row in members.values()}
    if len(timelines) != 1:
        fail("E_TIMELINE", f"Patroni members disagree on timeline in {phase_name}")
    timeline = next(iter(timelines))

    postgres = phase.get("postgres", {})
    if set(postgres) != set(host_map.values()):
        fail("E_TOPOLOGY", "PostgreSQL evidence host set drifted")
    system_ids = {
        str(row.get("system_identifier"))
        for row in postgres.values()
    }
    if len(system_ids) != 1 or not next(iter(system_ids)).isdigit():
        fail("E_LINEAGE", f"system identifier drifted in {phase_name}")
    for name, host in host_map.items():
        row = postgres[host]
        expected_recovery = name != expected_leader
        if (
            row.get("schema") != "pg36-ch20-postgresql-ha-facts-v1"
            or row.get("target_ip") != host
            or row.get("cluster_name") != "pg-test"
            or row.get("server_version_num", 0) // 10000 != 18
            or row.get("in_recovery") is not expected_recovery
        ):
            fail("E_TOPOLOGY", f"SQL identity/role drifted for {name}")
        settings = row.get("settings", {})
        if (
            settings.get("wal_log_hints") != "on"
            or settings.get("full_page_writes") != "on"
            or settings.get("archive_mode") != "on"
        ):
            fail("E_POLICY", f"WAL/rewind prerequisites drifted for {name}")
    primary = postgres[host_map[expected_leader]]
    current_timeline = primary.get("current_wal_timeline_id")
    if (
        not isinstance(current_timeline, int)
        or current_timeline != timeline
    ):
        fail("E_TIMELINE", "primary SQL WAL timeline and Patroni disagree")
    for row in postgres.values():
        checkpoint_timeline = row.get("checkpoint_timeline_id")
        if (
            not isinstance(checkpoint_timeline, int)
            or checkpoint_timeline > timeline
        ):
            fail("E_TIMELINE", "checkpoint timeline evidence is invalid")
    senders = primary.get("senders")
    expected_replicas = set(host_map) - {expected_leader}
    if (
        not isinstance(senders, list)
        or len(senders) != 2
        or {row.get("application_name") for row in senders}
        != expected_replicas
        or any(
            row.get("state") != "streaming"
            or row.get("sync_state") != "async"
            or row.get("client_addr")
            != host_map[str(row.get("application_name"))]
            or not isinstance(row.get("replay_gap_bytes"), (int, float))
            or row.get("replay_gap_bytes")
            > requirements["topology_acceptance"][
                "maximum_pre_switch_replay_lag_bytes"
            ]
            for row in senders
        )
    ):
        fail("E_TOPOLOGY", "primary does not see two async streaming senders")
    slots = primary.get("slots")
    expected_slots = {
        name.replace("-", "_")
        for name in expected_replicas
    }
    if (
        not isinstance(slots, list)
        or len(slots) != 2
        or {row.get("slot_name") for row in slots} != expected_slots
        or any(
            row.get("slot_type") != "physical"
            or row.get("active") is not True
            for row in slots
        )
    ):
        fail("E_WAL_RETENTION", "physical replication slots are not active")
    if primary.get("receivers") != []:
        fail("E_TOPOLOGY", "primary unexpectedly reports a WAL receiver")
    for name in expected_replicas:
        receiver_rows = postgres[host_map[name]].get("receivers")
        if (
            not isinstance(receiver_rows, list)
            or len(receiver_rows) != 1
            or receiver_rows[0].get("status") != "streaming"
            or receiver_rows[0].get("sender_host")
            != host_map[expected_leader]
            or receiver_rows[0].get("sender_port") != 5432
        ):
            fail("E_TOPOLOGY", f"WAL receiver drifted for {name}")
    return timeline


def validate_actions(
    requirements: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    for key, contract in (
        ("forward_action", requirements["planned_actions"]["forward"]),
        (
            "restore_action",
            requirements["planned_actions"]["restore_teaching_baseline"],
        ),
    ):
        action = evidence[key]
        if (
            action.get("schema") != "pg36-ch20-action-v1"
            or action.get("kind") != contract["kind"]
            or action.get("executor") != contract["executor"]
            or action.get("cluster") != "pg-test"
            or action.get("leader") != contract["leader"]
            or action.get("candidate") != contract["candidate"]
            or action.get("return_code") != 0
            or action.get("stderr_empty") is not True
            or not isinstance(action.get("stdout_sha256"), str)
            or len(action["stdout_sha256"]) != 64
            or action.get("finished_monotonic_ns", 0)
            <= action.get("started_monotonic_ns", 0)
            or action.get("duration_ms", 0) <= 0
            or action.get("stable_monotonic_ns", 0)
            < action.get("finished_monotonic_ns", 0)
        ):
            fail("E_ACTION", f"{key} identity or completion drifted")


def validate_reconciliation(
    requirements: dict[str, Any],
    reconciliation: dict[str, Any],
    manifest: dict[str, Any],
    forward_action: dict[str, Any],
    before_timeline: int,
    forward_timeline: int,
) -> None:
    probe_summary = reconciliation.get("probe_summary", {})
    if (
        reconciliation.get("schema") != "pg36-ch20-reconciliation-v1"
        or reconciliation.get("status") != "reconciled"
        or reconciliation.get("run_id") != manifest.get("run_id")
        or probe_summary.get("schema")
        != "pg36-ch20-client-summary-v1"
        or probe_summary.get("run_id") != manifest.get("run_id")
        or probe_summary.get("outcome") != "summary"
    ):
        fail("E_COMMIT_EVIDENCE", "reconciliation report identity drifted")
    counts = reconciliation.get("counts", {})
    contract = requirements["client_probe"]
    if (
        counts.get("events") != probe_summary.get("attempts")
        or counts.get("acknowledged")
        != probe_summary.get("acknowledged")
        or counts.get("unknown") != probe_summary.get("unknown")
        or counts.get("events")
        != counts.get("acknowledged", 0) + counts.get("unknown", 0)
        or counts.get("acknowledged", 0)
        < contract["minimum_acknowledged_attempts"]
        or counts.get("acknowledged_rows_missing")
        > contract["maximum_acknowledged_rows_missing"]
        or counts.get("duplicate_tokens")
        > contract["maximum_duplicate_tokens"]
        or counts.get("unreconciled_unknown_outcomes")
        > contract["maximum_unreconciled_unknown_outcomes"]
        or counts.get("persisted_rows")
        != counts.get("acknowledged", 0)
        + counts.get("unknown_committed", 0)
        or counts.get("unknown")
        != counts.get("unknown_committed", 0)
        + counts.get("unknown_absent", 0)
        + counts.get("unreconciled_unknown_outcomes", 0)
        or len(reconciliation.get("acknowledged_missing_tokens", []))
        != counts.get("acknowledged_rows_missing")
        or len(reconciliation.get("unknown_committed_tokens", []))
        != counts.get("unknown_committed")
        or len(reconciliation.get("unknown_absent_tokens", []))
        != counts.get("unknown_absent")
        or reconciliation.get("acknowledged_missing_tokens")
    ):
        fail("E_COMMIT_EVIDENCE", "commit token evidence is incomplete")
    metrics = reconciliation.get("metrics", {})
    gap = metrics.get(
        "conservative_write_gap_ms"
    )
    if (
        not isinstance(gap, (int, float))
        or gap > contract["maximum_observed_write_gap_ms"]
    ):
        fail("E_WRITE_GAP", "observed write gap exceeded sandbox objective")
    expected_action_to_stable_ms = (
        forward_action["stable_monotonic_ns"]
        - forward_action["started_monotonic_ns"]
    ) / 1_000_000
    action_command_ms = metrics.get("action_command_ms")
    action_to_stable_ms = metrics.get("action_to_stable_ms")
    if (
        not isinstance(action_command_ms, (int, float))
        or not isinstance(action_to_stable_ms, (int, float))
        or abs(
            action_command_ms
            - float(forward_action["duration_ms"])
        )
        > 0.001
        or abs(
            action_to_stable_ms
            - expected_action_to_stable_ms
        )
        > 0.001
        or not isinstance(metrics.get("maximum_adjacent_ack_gap_ms"), (int, float))
        or metrics.get("maximum_adjacent_ack_gap_ms", 0) <= 0
        or not isinstance(metrics.get("probe_interval_seconds"), (int, float))
        or metrics.get("probe_interval_seconds", 0) <= 0
    ):
        fail("E_MEASUREMENT", "client timing evidence is inconsistent")
    expected_timeline_hex = {
        f"{before_timeline:08X}",
        f"{forward_timeline:08X}",
    }
    if set(reconciliation.get("timeline_hex_seen", [])) != (
        expected_timeline_hex
    ):
        fail("E_TIMELINE", "client probe did not observe both timelines")


def validate_bundle(
    requirements: dict[str, Any],
    failure_model: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    validate_documents(requirements, failure_model)
    validate_manifest(requirements, evidence["manifest"])
    before = validate_phase(
        requirements,
        "before",
        evidence["phases"]["before"],
        "pg-test-1",
    )
    pre_switch = validate_phase(
        requirements,
        "pre-switch",
        evidence["phases"]["pre-switch"],
        "pg-test-1",
    )
    forward = validate_phase(
        requirements,
        "after-forward",
        evidence["phases"]["after-forward"],
        "pg-test-2",
    )
    restored = validate_phase(
        requirements,
        "restored",
        evidence["phases"]["restored"],
        "pg-test-1",
    )
    if pre_switch != before:
        fail("E_TIMELINE", "timeline changed before the planned action")
    if forward <= before or restored <= forward:
        fail("E_TIMELINE", "timeline did not advance on both switchovers")
    all_system_ids = {
        str(row["system_identifier"])
        for phase in evidence["phases"].values()
        for row in phase["postgres"].values()
    }
    if len(all_system_ids) != 1:
        fail("E_LINEAGE", "system identifier changed across the drill")
    validate_actions(requirements, evidence)
    validate_reconciliation(
        requirements,
        evidence["reconciliation"],
        evidence["manifest"],
        evidence["forward_action"],
        before,
        forward,
    )
    if evidence.get("client_probe_stderr", "").strip():
        fail("E_CLIENT_PROBE", "client probe wrote unexpected stderr")

    reconciliation = evidence["reconciliation"]
    return {
        "schema": "pg36-ch20-validation-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "decision": {
            "sandbox_planned_switchover": "accepted-with-exceptions",
            "production_ch20_gate": "pending",
            "unplanned_failure_drill": "not-run",
            "final_leader": "pg-test-1",
        },
        "topology": {
            "before_timeline": before,
            "forward_timeline": forward,
            "restored_timeline": restored,
            "system_identifier_relation": "one unchanged identifier",
            "members": 3,
        },
        "client": {
            "attempts": reconciliation["counts"]["events"],
            "acknowledged": reconciliation["counts"]["acknowledged"],
            "unknown": reconciliation["counts"]["unknown"],
            "acknowledged_rows_missing": reconciliation["counts"][
                "acknowledged_rows_missing"
            ],
            "unknown_committed": reconciliation["counts"][
                "unknown_committed"
            ],
            "unknown_absent": reconciliation["counts"]["unknown_absent"],
            "conservative_write_gap_ms": reconciliation["metrics"][
                "conservative_write_gap_ms"
            ],
            "action_to_stable_ms": reconciliation["metrics"][
                "action_to_stable_ms"
            ],
        },
        "accepted_exception_ids": requirements["required_exception_ids"],
        "canonical_sha256": {
            "requirements": canonical_sha256(requirements),
            "failure_model": canonical_sha256(failure_model),
        },
        "policies": [
            "planned-switchover-is-not-unplanned-failover",
            "one-system-identifier-survives-both-timelines",
            "exact-leader-candidate-and-final-baseline-are-enforced",
            "all-nonleaders-return-to-streaming",
            "acknowledged-and-unknown-commit-outcomes-are-reconciled",
            "client-write-gap-is-a-sampled-sandbox-observation",
            "watchdog-dcs-sync-and-tls-limitations-remain-explicit",
        ],
    }


def get_path(document: Any, path: list[Any]) -> Any:
    cursor = document
    for segment in path:
        cursor = cursor[segment]
    return cursor


def set_path(document: Any, path: list[Any], value: Any) -> None:
    cursor = document
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = value


def apply_patch(documents: dict[str, Any], patch: dict[str, Any]) -> None:
    target = patch.get("target")
    if target not in documents:
        fail("E_NEGATIVE_CASE", f"unknown patch target: {target}")
    path = patch.get("path")
    if not isinstance(path, list) or not path:
        fail("E_NEGATIVE_CASE", "patch path must be non-empty")
    if patch.get("op") == "replace":
        set_path(documents[target], path, patch.get("value"))
    elif patch.get("op") == "copy":
        source = patch.get("from")
        if not isinstance(source, list) or not source:
            fail("E_NEGATIVE_CASE", "copy patch needs from path")
        set_path(
            documents[target],
            path,
            copy.deepcopy(get_path(documents[target], source)),
        )
    else:
        fail("E_NEGATIVE_CASE", "unsupported negative patch operation")


def run_negative_suite(
    requirements: dict[str, Any],
    failure_model: dict[str, Any],
    evidence: dict[str, Any],
    cases: dict[str, Any],
) -> dict[str, Any]:
    if (
        cases.get("schema") != "pg36-ch20-negative-cases-v1"
        or cases.get("release") != requirements["release"]
    ):
        fail("E_SCHEMA", "negative suite identity drifted")
    rows = cases.get("cases")
    if not isinstance(rows, list) or not rows:
        fail("E_NEGATIVE_CASE", "negative suite has no cases")
    results: list[dict[str, str]] = []
    for case in rows:
        documents = {
            "requirements": copy.deepcopy(requirements),
            "failure_model": copy.deepcopy(failure_model),
            "evidence": copy.deepcopy(evidence),
        }
        for patch in case.get("patches", []):
            apply_patch(documents, patch)
        actual = "NO_ERROR"
        try:
            validate_bundle(
                documents["requirements"],
                documents["failure_model"],
                documents["evidence"],
            )
        except PolicyError as error:
            actual = error.code
        expected = str(case.get("expected_code"))
        if actual != expected:
            fail(
                "E_NEGATIVE_EXPECTATION",
                f"case {case.get('id')} expected {expected}, got {actual}",
            )
        results.append(
            {
                "id": str(case.get("id")),
                "expected_code": expected,
                "actual_code": actual,
            }
        )
    return {
        "schema": "pg36-ch20-negative-report-v1",
        "release": requirements["release"],
        "status": "ok",
        "case_count": len(results),
        "cases": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--failure-model", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        failure_model = read_json(args.failure_model)
        evidence = load_evidence(args.evidence)
        if args.negative_cases:
            report = run_negative_suite(
                requirements,
                failure_model,
                evidence,
                read_json(args.negative_cases),
            )
        else:
            report = validate_bundle(
                requirements,
                failure_model,
                evidence,
            )
    except (PolicyError, OSError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, PolicyError):
            payload = {
                "status": "error",
                "code": error.code,
                "message": error.message,
            }
        else:
            payload = {
                "status": "error",
                "code": "E_EVIDENCE",
                "message": str(error),
            }
        sys.stderr.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 1
    payload = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
