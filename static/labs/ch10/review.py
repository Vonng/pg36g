#!/usr/bin/env python3
"""Review ch10 evidence by concurrency semantics, not dynamic IDs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def canonical_checksum(path: Path) -> str:
    value = load_json(path)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ReviewError(f"cannot read CSV {path}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def review_result(evidence: Path) -> dict[str, Any]:
    result = load_json(evidence / "concurrency-result.json")
    require(
        result.get("schema") == "pg36-ch10-concurrency-result-v1",
        "result schema drifted",
    )
    require(result.get("status") == "ok", "result status is not ok")

    lost = result["lost_update"]
    require(lost["both_observed"] == 100, "lost workers did not read 100")
    require(lost["serial_expected"] == 70, "lost serial oracle drifted")
    require(lost["actual"] in [80, 90], "lost-update outcome drifted")
    require(lost["lost_update_observed"] is True, "lost update missing")

    atomic = result["atomic_update"]
    require(
        atomic
        == {
            "successful_writes": 2,
            "actual": 70,
            "version": 2,
            "invariant_preserved": True,
        },
        "atomic update relationship drifted",
    )

    optimistic = result["optimistic_update"]
    require(
        optimistic["first_attempt_successes"] == 1
        and optimistic["first_attempt_conflicts"] == 1
        and optimistic["retry_successes"] == 1
        and optimistic["actual"] == 70
        and optimistic["version"] == 2,
        "optimistic retry relationship drifted",
    )

    rr = result["repeatable_read_write_conflict"]
    require(
        rr["successes"] == 1
        and rr["sqlstate_40001"] == 1
        and rr["actual_after_one_commit"] in [80, 90]
        and rr["silent_overwrite"] is False,
        "Repeatable Read conflict relationship drifted",
    )

    skew = result["repeatable_read_write_skew"]
    serial = result["serializable_write_skew"]
    require(
        skew["commits"] == 2
        and skew["observed_on_call_each"] == 2
        and skew["final_on_call"] == 0
        and skew["invariant_violated"] is True,
        "Repeatable Read write skew drifted",
    )
    require(
        serial["commits"] == 1
        and serial["sqlstate_40001"] == 1
        and serial["siread_locks_observed"] >= 2
        and serial["final_on_call"] == 1
        and serial["invariant_preserved"] is True,
        "Serializable SSI relationship drifted",
    )

    require(
        result["nowait"]["sqlstate_55P03"] == 1,
        "NOWAIT SQLSTATE drifted",
    )
    skip = result["skip_locked"]
    require(
        sorted(skip["claimed_each"]) == [3, 3]
        and skip["distinct_jobs"] == 6
        and skip["duplicate_claims"] == 0,
        "SKIP LOCKED relationship drifted",
    )
    deadlock = result["deadlock"]
    require(
        deadlock["sqlstate_40P01"] == 1
        and deadlock["commits"] == 1
        and deadlock["row_values"] == [1, 1]
        and deadlock["state_consistent"] is True,
        "deadlock relationship drifted",
    )
    advisory = result["advisory_lifecycle"]
    require(
        advisory["session_lock_survived_rollback"] is True
        and advisory["transaction_lock_released_at_end"] is True,
        "advisory lifecycle drifted",
    )
    row_lock = result["row_lock"]
    require(
        row_lock["blocker_edges"] == 1
        and row_lock["wait_event_type"] == "Lock"
        and row_lock["waiter_saw_after_holder"] == 90
        and row_lock["final_available"] == 70,
        "row-lock serialization drifted",
    )

    payment = result["payment_idempotency"]
    require(
        payment["concurrent_requests"] == 2
        and payment["inserted"] == 1
        and payment["reused"] == 1
        and payment["distinct_responses"] == 1
        and payment["payment_rows"] == 1
        and payment["outbox_rows"] == 1
        and payment["mismatch_sqlstate_P0001"] == 1
        and payment["external_call_inside_transaction"] is False,
        "payment idempotency relationship drifted",
    )
    cleanup = result["cleanup"]
    require(
        cleanup == {"active_workers": 0, "advisory_locks": 0},
        "worker/advisory cleanup drifted",
    )
    return result


def review_raw(evidence: Path) -> dict[str, Any]:
    required = [
        "lost-waiting.csv",
        "serializable-siread.csv",
        "row-lock-graph.csv",
        "deadlock-before-release.csv",
        "lost-a.stdout",
        "lost-b.stdout",
        "payment-a.stdout",
        "payment-b.stdout",
    ]
    missing = [name for name in required if not (evidence / name).is_file()]
    require(not missing, f"raw evidence missing: {missing}")

    waiting = read_csv(evidence / "lost-waiting.csv")
    require(
        len(waiting) == 2
        and all(row["wait_event"] == "advisory" for row in waiting),
        "lost-update barrier evidence drifted",
    )

    siread = read_csv(evidence / "serializable-siread.csv")
    require(
        len(siread) >= 2
        and {row["application_name"] for row in siread}
        == {
            "pg36-ch10-write-skew-ser-a",
            "pg36-ch10-write-skew-ser-b",
        }
        and all(row["mode"] == "SIReadLock" for row in siread),
        "SIReadLock raw evidence drifted",
    )

    graph = read_csv(evidence / "row-lock-graph.csv")
    require(len(graph) == 1, "row-lock graph must have one edge")
    edge = graph[0]
    require(
        edge["waiter_application"] == "pg36-ch10-row-lock-waiter"
        and edge["blocker_application"] == "pg36-ch10-row-lock-holder"
        and edge["wait_event_type"] == "Lock"
        and edge["wait_event"] in {"transactionid", "tuple"},
        "row-lock edge identity drifted",
    )

    states: list[str] = []
    for path in sorted(evidence.glob("*.stderr")):
        text = path.read_text(encoding="utf-8")
        states.extend(
            re.findall(r"ERROR:\s+([0-9A-Z]{5}):", text)
        )
    counts = Counter(states)
    require(
        counts
        == Counter(
            {
                "40001": 2,
                "55P03": 1,
                "40P01": 1,
                "P0001": 1,
            }
        ),
        f"expected SQLSTATE multiset drifted: {dict(counts)}",
    )
    return {
        "siread_rows": len(siread),
        "blocker_edges": len(graph),
        "sqlstates": dict(sorted(counts.items())),
    }


def review_proposal(repo_root: Path) -> dict[str, str]:
    baseline = repo_root / "static/labs/ch06/baseline-v0.1.json"
    dependency = (
        repo_root / "static/labs/ch09/baseline-v0.4-proposal.json"
    )
    proposal_path = (
        repo_root / "static/labs/ch10/baseline-v0.5-proposal.json"
    )
    proposal = load_json(proposal_path)
    require(
        proposal.get("base_checksum") == canonical_checksum(baseline),
        "v0.5 base checksum drifted",
    )
    dependencies = proposal.get("depends_on_candidates")
    require(
        isinstance(dependencies, list) and len(dependencies) == 1,
        "v0.5 dependency declaration drifted",
    )
    require(
        dependencies[0].get("proposal_checksum")
        == canonical_checksum(dependency),
        "v0.5 dependency checksum drifted",
    )
    require(
        proposal.get("candidate_baseline") == "0.5.0"
        and proposal.get("status") == "candidate"
        and proposal.get("rule_id") == "DEFAULT-TXNN-007",
        "v0.5 candidate identity drifted",
    )
    for item in proposal.get("evidence", []):
        public_path = item.get("artifact", "")
        require(
            isinstance(public_path, str)
            and public_path.startswith("/labs/ch10/"),
            "v0.5 evidence path escaped ch10",
        )
        local = repo_root / "static" / public_path.removeprefix("/")
        require(local.is_file(), f"v0.5 artifact missing: {public_path}")
    return {
        "base": str(proposal.get("base_baseline")),
        "candidate": str(proposal.get("candidate_baseline")),
        "rule_id": str(proposal.get("rule_id")),
    }


def review_final(evidence: Path) -> dict[str, Any]:
    try:
        text = (evidence / "verify.txt").read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError("verify.txt is missing") from exc
    checksum = "f8a7bfae59c6d16cd323abecfefe1014"
    require(
        f"relation_checksum={checksum}" in text,
        "ch04-v1 checksum drifted",
    )
    for marker in [
        "fixture=ch10-concurrency-v1",
        "inventory=70/version:2",
        "doctors_on_call=1",
        "jobs_running=6/duplicate_claims:0",
        "payments=1/outbox=1",
        "active_lab_workers=0",
        "remaining_advisory_barriers=0",
    ]:
        require(marker in text, f"final verify marker missing: {marker}")
    return {
        "relation_checksum": checksum,
        "workers": 0,
        "advisory_barriers": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    repo_root = args.repo_root.resolve()

    result = {
        "status": "ok",
        "relationships": review_result(evidence),
        "raw": review_raw(evidence),
        "proposal": review_proposal(repo_root),
        "final": review_final(evidence),
    }
    (evidence / "review.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lost = result["relationships"]["lost_update"]
    print(
        "lost="
        f"observed:100+100/expected:70/actual:{lost['actual']}"
    )
    print("safe=atomic:70/optimistic:1-conflict+1-retry->70")
    print("isolation=rr-update:40001/rr-skew:0/serializable:40001->1")
    print("locks=55P03/40P01/blocker-edge:1/skip-locked:6-distinct")
    print("advisory=session-survives-rollback/xact-released")
    print("idempotency=requests:2/payment:1/outbox:1/mismatch:P0001")
    print("proposal=0.1.0->0.5.0/DEFAULT-TXNN-007/depends-on-v0.4")
    print(
        "final=workers:0/advisory:0/"
        "checksum:f8a7bfae59c6d16cd323abecfefe1014"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReviewError, KeyError, TypeError, ValueError) as exc:
        print(f"status=error error={exc}", file=sys.stderr)
        raise SystemExit(1)
