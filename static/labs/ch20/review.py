#!/usr/bin/env python3
"""Review one complete chapter 20 planned-switchover evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_NEGATIVE_CODES = {
    "claim-production-from-sandbox": "E_PRODUCTION_CLAIM",
    "switch-to-unreviewed-candidate": "E_ACTION",
    "ignore-switchover-command-failure": "E_ACTION",
    "accept-a-foreign-system-identifier": "E_LINEAGE",
    "accept-two-leaders-after-switch": "E_TOPOLOGY",
    "accept-no-timeline-advance": "E_TIMELINE",
    "leave-old-primary-out-of-cluster": "E_TOPOLOGY",
    "lose-an-acknowledged-token": "E_COMMIT_EVIDENCE",
    "leave-unknown-commit-unreconciled": "E_COMMIT_EVIDENCE",
    "accept-write-gap-over-objective": "E_WRITE_GAP",
}

EXPECTED_EXCEPTION_IDS = [
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

# These two files describe a completed reference run. They are outcomes rather
# than inputs to a new run, so drill.py deliberately excludes them from the
# source-input manifest.
OUTCOME_FILES = {"drill-run.json", "migration-effort.json"}


class ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_inputs(source: Path) -> dict[str, str]:
    return {
        path.name: sha256(path)
        for path in sorted(source.iterdir())
        if path.is_file() and path.name not in OUTCOME_FILES
    }


def review_source_identity(
    drill: Path,
    source: Path,
    requirements: dict[str, Any],
    failure_model: dict[str, Any],
) -> None:
    manifest = load_json(drill / "drill-manifest.json")
    require(
        manifest.get("schema") == "pg36-ch20-drill-manifest-v1"
        and manifest.get("release") == "1.0-sandbox"
        and manifest.get("target") == "pg36-l2-vagrant/pg-test"
        and manifest.get("mode")
        == "planned-switchover-and-planned-baseline-restore"
        and manifest.get("production_approval") is False
        and manifest.get("unplanned_failure_injected") is False
        and manifest.get("secret_values_exported") == 0,
        "drill manifest identity or authority drifted",
    )
    require(
        manifest.get("source_sha256") == source_inputs(source),
        "captured source checksums do not match the reviewed source inputs",
    )

    report = load_json(drill / "validation-report.json")
    checksums = report.get("canonical_sha256", {})
    require(
        checksums.get("requirements") == canonical_sha256(requirements)
        and checksums.get("failure_model") == canonical_sha256(failure_model),
        "validation report used different decision documents",
    )


def review_positive(
    drill: Path,
    requirements: dict[str, Any],
) -> None:
    report = load_json(drill / "validation-report.json")
    require(
        report.get("schema") == "pg36-ch20-validation-report-v1"
        and report.get("release") == "1.0-sandbox"
        and report.get("status") == "ok",
        "normal validation report identity drifted",
    )
    require(
        report.get("decision")
        == {
            "sandbox_planned_switchover": "accepted-with-exceptions",
            "production_ch20_gate": "pending",
            "unplanned_failure_drill": "not-run",
            "final_leader": "pg-test-1",
        },
        "validation decision crossed its interpretation boundary",
    )
    topology = report.get("topology", {})
    before = topology.get("before_timeline")
    forward = topology.get("forward_timeline")
    restored = topology.get("restored_timeline")
    require(
        isinstance(before, int)
        and isinstance(forward, int)
        and isinstance(restored, int)
        and before < forward < restored
        and topology.get("members") == 3
        and topology.get("system_identifier_relation")
        == "one unchanged identifier",
        "accepted topology or timeline relation drifted",
    )
    client = report.get("client", {})
    contract = requirements["client_probe"]
    require(
        client.get("attempts", 0) >= client.get("acknowledged", 0)
        >= contract["minimum_acknowledged_attempts"]
        and client.get("acknowledged_rows_missing") == 0
        and client.get("unknown_committed", 0)
        + client.get("unknown_absent", 0)
        == client.get("unknown", 0)
        and 0
        < client.get("conservative_write_gap_ms", 0)
        <= contract["maximum_observed_write_gap_ms"]
        and client.get("action_to_stable_ms", 0) > 0,
        "client continuity evidence drifted",
    )
    require(
        report.get("accepted_exception_ids") == EXPECTED_EXCEPTION_IDS,
        "accepted exception set drifted",
    )


def review_negative(drill: Path) -> None:
    report = load_json(drill / "negative-report.json")
    require(
        report.get("schema") == "pg36-ch20-negative-report-v1"
        and report.get("release") == "1.0-sandbox"
        and report.get("status") == "ok"
        and report.get("case_count") == len(EXPECTED_NEGATIVE_CODES),
        "negative report identity drifted",
    )
    actual = {
        str(row["id"]): str(row["actual_code"])
        for row in report.get("cases", [])
    }
    expected = {
        str(row["id"]): str(row["expected_code"])
        for row in report.get("cases", [])
    }
    require(
        actual == EXPECTED_NEGATIVE_CODES
        and expected == EXPECTED_NEGATIVE_CODES,
        "counterexamples did not fail with their intended policy codes",
    )


def phase_members(phase: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["member"]): row
        for row in phase["patroni"]["members"]
    }


def review_live_evidence(
    root: Path,
    drill: Path,
    requirements: dict[str, Any],
) -> None:
    phases = {
        name: load_json(drill / "phases" / f"{name}.json")
        for name in ("before", "pre-switch", "after-forward", "restored")
    }
    expected_leaders = {
        "before": "pg-test-1",
        "pre-switch": "pg-test-1",
        "after-forward": "pg-test-2",
        "restored": "pg-test-1",
    }
    system_ids: set[str] = set()
    timeline_by_phase: dict[str, int] = {}
    host_by_name = {
        name: str(row["address"])
        for name, row in requirements["members"].items()
    }
    for phase_name, phase in phases.items():
        members = phase_members(phase)
        require(
            set(members) == set(host_by_name),
            f"Patroni member set drifted in {phase_name}",
        )
        leader = expected_leaders[phase_name]
        leaders = [
            name
            for name, row in members.items()
            if row.get("role") == "primary"
        ]
        require(
            leaders == [leader],
            f"leader identity drifted in {phase_name}",
        )
        timelines = {int(row["timeline"]) for row in members.values()}
        require(
            len(timelines) == 1,
            f"Patroni timeline diverged in {phase_name}",
        )
        timeline = next(iter(timelines))
        timeline_by_phase[phase_name] = timeline
        postgres = phase["postgres"]
        for row in postgres.values():
            system_ids.add(str(row["system_identifier"]))
            checkpoint = row.get("checkpoint_timeline_id")
            require(
                isinstance(checkpoint, int) and checkpoint <= timeline,
                f"checkpoint timeline is invalid in {phase_name}",
            )
        primary = postgres[host_by_name[leader]]
        require(
            primary.get("in_recovery") is False
            and primary.get("current_wal_timeline_id") == timeline,
            f"primary SQL timeline drifted in {phase_name}",
        )
    require(
        len(system_ids) == 1
        and next(iter(system_ids)).isdigit()
        and timeline_by_phase["before"]
        == timeline_by_phase["pre-switch"]
        < timeline_by_phase["after-forward"]
        < timeline_by_phase["restored"],
        "lineage or timeline sequence drifted across the drill",
    )

    preflight = load_json(root / "preflight-ch19" / "validation-report.json")
    postflight = load_json(root / "postflight-ch19" / "validation-report.json")
    for label, report in (("preflight", preflight), ("postflight", postflight)):
        require(
            report.get("schema") == "pg36-ch19-validation-report-v1"
            and report.get("status") == "ok"
            and report.get("decision", {}).get("sandbox_l2")
            == "accepted-with-exceptions"
            and report.get("decision", {}).get("production_ch19_gate")
            == "pending",
            f"chapter-19 {label} did not pass its retained baseline",
        )
        require(
            str(
                report.get("facts", {})
                .get("system_identifiers", {})
                .get("pg-test")
            )
            in system_ids,
            f"chapter-19 {label} and chapter-20 lineage disagree",
        )


def review_actions_and_commit_evidence(drill: Path) -> None:
    forward = load_json(drill / "forward-action.json")
    restore = load_json(drill / "restore-action.json")
    require(
        forward.get("kind") == "planned-switchover"
        and forward.get("executor") == "patronictl"
        and forward.get("leader") == "pg-test-1"
        and forward.get("candidate") == "pg-test-2"
        and forward.get("return_code") == 0
        and restore.get("kind") == "planned-switchover"
        and restore.get("executor") == "patronictl"
        and restore.get("leader") == "pg-test-2"
        and restore.get("candidate") == "pg-test-1"
        and restore.get("return_code") == 0,
        "planned action identity drifted",
    )
    reconciliation = load_json(drill / "reconciliation.json")
    counts = reconciliation.get("counts", {})
    require(
        reconciliation.get("status") == "reconciled"
        and counts.get("acknowledged_rows_missing") == 0
        and counts.get("duplicate_tokens") == 0
        and counts.get("unreconciled_unknown_outcomes") == 0
        and counts.get("persisted_rows")
        == counts.get("acknowledged", 0) + counts.get("unknown_committed", 0)
        and not reconciliation.get("acknowledged_missing_tokens"),
        "commit-outcome reconciliation drifted",
    )
    require(
        not (drill / "client-probe.stderr")
        .read_text(encoding="utf-8")
        .strip(),
        "client probe wrote unexpected stderr",
    )


def review_reference_account(source: Path) -> None:
    account = load_json(source / "drill-run.json")
    require(
        account.get("schema") == "pg36-ch20-drill-run-v1"
        and account.get("release") == "1.0-sandbox"
        and account.get("target") == "pg36-l2-vagrant/pg-test"
        and account.get("action")
        == "planned-switchover-and-planned-baseline-restore"
        and account.get("production_approval") is False
        and account.get("unplanned_failure_injected") is False
        and account.get("secret_values_exported") == 0
        and account.get("decision", {}).get("sandbox_planned_switchover")
        == "accepted-with-exceptions"
        and account.get("decision", {}).get("production_ch20_gate")
        == "pending",
        "sanitized reference drill account drifted",
    )
    effort = load_json(source / "migration-effort.json")
    require(
        effort.get("schema") == "pg36-ch20-effort-v1"
        and effort.get("release") == "1.0-sandbox"
        and effort.get("human_authoring_seconds") is None
        and effort.get("human_authoring_measurement")
        == "not-instrumented-do-not-infer",
        "migration-effort account invents or loses its measurement boundary",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    drill = args.evidence / "drill"
    try:
        requirements = load_json(args.source_dir / "requirements.json")
        failure_model = load_json(args.source_dir / "failure-model.json")
        review_source_identity(
            drill,
            args.source_dir,
            requirements,
            failure_model,
        )
        review_positive(drill, requirements)
        review_negative(drill)
        review_live_evidence(args.evidence, drill, requirements)
        review_actions_and_commit_evidence(drill)
        review_reference_account(args.source_dir)
    except (ReviewError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"review failed: {error}\n")
        return 1
    print("status=ok")
    print("target=pg36-l2-vagrant/pg-test")
    print("postgresql=18.4")
    print("patroni=4.1.3")
    print("topology=one-primary-two-streaming-replicas-restored")
    print("action=planned-switchover-and-restore")
    print("counterexamples=10-rejected")
    print("acknowledged_commits=all-present")
    print("sandbox_planned_switchover=accepted-with-exceptions")
    print("unplanned_failure_drill=not-run")
    print("production_ch20_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
