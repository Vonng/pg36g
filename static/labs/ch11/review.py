#!/usr/bin/env python3
"""Review ch11 evidence by state relationships, not timing thresholds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


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


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        document = path.read_text(encoding="utf-8")
        document = "\n".join(
            line
            for line in document.splitlines()
            if not line.startswith("[context] ")
        )
        return list(csv.DictReader(document.splitlines()))
    except OSError as exc:
        raise ReviewError(f"cannot read CSV {path}: {exc}") from exc


def canonical_checksum(path: Path) -> str:
    value = load_json(path)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_defaults(evidence: Path) -> dict[str, int]:
    rows = read_csv(evidence / "default-catalog.csv")
    require(len(rows) == 1, "default catalog must have one row")
    row = rows[0]
    before = int(row["before_filenode"])
    fast = int(row["fast_filenode"])
    volatile = int(row["volatile_filenode"])
    fast_wal = int(row["fast_wal_bytes"])
    volatile_wal = int(row["volatile_wal_bytes"])
    require(
        before == fast
        and fast != volatile
        and row["fast_has_missing"] == "t"
        and row["fast_missing_value"] == "{7}"
        and row["volatile_has_missing"] == "f"
        and int(row["row_count"]) == 50000,
        "default fast/rewrite catalog relationship drifted",
    )
    require(
        volatile_wal > fast_wal >= 0,
        "volatile default did not generate more WAL than fast path",
    )
    return {
        "fast_wal_bytes": fast_wal,
        "volatile_wal_bytes": volatile_wal,
    }


def review_lock(evidence: Path) -> None:
    result = load_json(evidence / "lock-summary.json")
    require(
        result
        == {
            "schema": "pg36-ch11-lock-result-v1",
            "status": "ok",
            "sqlstate": "55P03",
            "waiter": "pg36-ch11-lock-waiter",
            "blocker": "pg36-ch11-lock-holder",
            "requested_mode": "AccessExclusiveLock",
            "blocker_edges": 1,
            "column_absent_after_failure": True,
            "holder_released_by": "COMMIT",
        },
        "lock result drifted",
    )
    rows = read_csv(evidence / "lock-graph.csv")
    require(
        len(rows) == 1
        and rows[0]["waiter_application"]
        == "pg36-ch11-lock-waiter"
        and rows[0]["blocker_application"]
        == "pg36-ch11-lock-holder"
        and rows[0]["wait_event_type"] == "Lock"
        and rows[0]["requested_mode"] == "AccessExclusiveLock"
        and rows[0]["granted"] == "f",
        "raw lock edge drifted",
    )
    stderr = (evidence / "lock-attempt.stderr").read_text(
        encoding="utf-8"
    )
    require(
        re.search(r"\b55P03\b", stderr) is not None,
        "55P03 is missing from raw lock stderr",
    )


def constraint_map(
    path: Path,
) -> dict[str, dict[str, str]]:
    return {
        row["constraint_name"]: row
        for row in read_csv(path)
    }


def review_constraints(evidence: Path) -> str:
    before = constraint_map(evidence / "constraint-before.csv")
    after = constraint_map(evidence / "constraint-after.csv")
    require(
        before["ch11_order_shipping_pair_consistent"][
            "convalidated"
        ]
        == "f"
        and before["pg_attribute.shipping_code"][
            "convalidated"
        ]
        == "f",
        "expand constraint state drifted",
    )
    require(
        after["ch11_order_shipping_pair_consistent"][
            "convalidated"
        ]
        == "t"
        and after["ch11_order_shipping_code_nn"][
            "convalidated"
        ]
        == "t"
        and after["pg_attribute.shipping_code"][
            "convalidated"
        ]
        == "t",
        "validated constraint state drifted",
    )
    pg18_not_null = [
        row
        for row in after.values()
        if row["constraint_type"] == "n"
    ]
    manifest = (evidence / "manifest.txt").read_text(encoding="utf-8")
    match = re.search(r"server_version=(\d+)\.", manifest)
    require(match is not None, "server version missing from manifest")
    major = int(match.group(1))
    if major >= 18:
        require(
            len(pg18_not_null) == 1
            and pg18_not_null[0]["convalidated"] == "t",
            "PG18 relation NOT NULL constraint is missing",
        )
        return "pg18-pg_constraint+pg_attribute"
    require(
        not pg18_not_null,
        "pre-PG18 unexpectedly has a relation NOT NULL constraint",
    )
    return "pg14-17-pg_attribute"


def review_backfill(evidence: Path) -> None:
    interrupted = load_json(
        evidence / "backfill-interrupted.json"
    )
    resumed = load_json(evidence / "backfill-resumed.json")
    require(
        interrupted["schema"]
        == "pg36-ch11-backfill-result-v1"
        and interrupted["status"] == "interrupted"
        and interrupted["exit_code"] == 75
        and interrupted["batches_run"] == 2
        and interrupted["start"]["phase"] == "expanded"
        and interrupted["end"]["phase"] == "backfilling"
        and interrupted["end"]["rows_migrated"] == 10000
        and interrupted["end"]["remaining_nulls"] == 39999
        and interrupted["committed_batches_preserved"] is True,
        "interrupted backfill relationship drifted",
    )
    require(
        resumed["schema"] == "pg36-ch11-backfill-result-v1"
        and resumed["status"] == "complete"
        and resumed["exit_code"] == 0
        and resumed["resumed"] is True
        and resumed["start"]["last_order_id"]
        == interrupted["end"]["last_order_id"]
        and resumed["end"]["phase"] == "migrated"
        and resumed["end"]["target_rows"] == 49999
        and resumed["end"]["rows_migrated"] == 49999
        and resumed["end"]["batches"] == 10
        and resumed["end"]["last_order_id"] == 50000
        and resumed["end"]["remaining_nulls"] == 0
        and resumed["end"]["mismatches"] == 0,
        "resumed backfill relationship drifted",
    )


def review_contract(evidence: Path) -> None:
    exit_text = (evidence / "contract-gate.exit").read_text(
        encoding="utf-8"
    )
    stderr = (evidence / "contract-gate.stderr").read_text(
        encoding="utf-8"
    )
    verify = (evidence / "verify.txt").read_text(encoding="utf-8")
    require(
        exit_text.strip() == "exit=3"
        and re.search(r"\bP3612\b", stderr) is not None
        and "release=switched/contract:not-executed" in verify
        and "legacy-column+bridge-retained" in verify,
        "contract refusal or rollback-window state drifted",
    )


def review_partition(evidence: Path) -> dict[str, Any]:
    result = load_json(evidence / "partition-summary.json")
    require(
        result["schema"] == "pg36-ch11-partition-result-v1"
        and result["status"] == "ok"
        and result["validated_check_present_before_attach"] is True
        and result[
            "filenode_preserved_across_attach_detach"
        ]
        is True
        and result["data_retained_after_detach"] is True
        and result["reattached_for_final_state"] is True,
        "partition result flags drifted",
    )
    locks = {
        (row["relation_name"], row["mode"])
        for row in result["attach_locks"]
        if row["granted"] is True
    }
    require(
        (
            "shop_private.ch11_event",
            "ShareUpdateExclusiveLock",
        )
        in locks
        and (
            "shop_private.ch11_event_2025q1",
            "AccessExclusiveLock",
        )
        in locks,
        "ATTACH lock modes drifted",
    )
    before = result["before"]
    attached = result["after_attach"]
    detached = result["after_detach"]
    final = result["final"]
    require(
        before["is_partition"] is False
        and attached["is_partition"] is True
        and detached["is_partition"] is False
        and final["is_partition"] is True
        and {
            before["child_filenode"],
            attached["child_filenode"],
            detached["child_filenode"],
            final["child_filenode"],
        }
        == {before["child_filenode"]}
        and detached["child_rows"] == 20000
        and final["parent_rows"] == 20000
        and result["detach"]["server_version_num"] >= 140000
        and result["detach"]["outside_transaction_block"] is True,
        "partition lifecycle relationship drifted",
    )
    return result["detach"]


def review_proposal(repo_root: Path) -> str:
    baseline = repo_root / "static/labs/ch06/baseline-v0.1.json"
    dependency = (
        repo_root / "static/labs/ch10/baseline-v0.5-proposal.json"
    )
    proposal_path = (
        repo_root / "static/labs/ch11/baseline-v0.6-proposal.json"
    )
    proposal = load_json(proposal_path)
    require(
        proposal["base_checksum"] == canonical_checksum(baseline),
        "v0.6 base checksum drifted",
    )
    require(
        len(proposal["depends_on_candidates"]) == 1
        and proposal["depends_on_candidates"][0][
            "proposal_checksum"
        ]
        == canonical_checksum(dependency),
        "v0.6 dependency checksum drifted",
    )
    changes = proposal["rule_changes"]
    require(
        {change["rule_id"] for change in changes}
        == {"SAFE-MIGR-006", "DEFAULT-VERS-010"}
        and proposal["candidate_baseline"] == "0.6.0"
        and proposal["status"] == "candidate",
        "v0.6 rule changes drifted",
    )
    return canonical_checksum(proposal_path)


def review_model(evidence: Path) -> str:
    text = (evidence / "model-verify-after.txt").read_text(
        encoding="utf-8"
    )
    match = re.search(r"relation_checksum=([0-9a-f]{32})", text)
    require(match is not None, "business checksum missing")
    checksum = match.group(1)
    require(
        checksum == "f8a7bfae59c6d16cd323abecfefe1014",
        "business checksum drifted",
    )
    return checksum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    args = parser.parse_args()

    try:
        evidence = args.evidence_dir.resolve()
        defaults = review_defaults(evidence)
        review_lock(evidence)
        catalog_mode = review_constraints(evidence)
        review_backfill(evidence)
        review_contract(evidence)
        detach = review_partition(evidence)
        proposal_checksum = review_proposal(args.repo_root.resolve())
        business_checksum = review_model(evidence)

        print("status=ok")
        print(
            "risk=lock:55P03/schema-unchanged/"
            "default:metadata-vs-rewrite"
        )
        print(
            "wal=fast:"
            f"{defaults['fast_wal_bytes']}/"
            f"volatile:{defaults['volatile_wal_bytes']}"
        )
        print(
            "compatibility=old+new/mismatch:23514/"
            "contract:P3612"
        )
        print(
            "backfill=interrupt:2x5000/"
            "resume:49999-in-10/remaining:0"
        )
        print(
            "constraints=not-valid->valid->not-null/"
            f"catalog:{catalog_mode}"
        )
        print(
            "partition=attach:SUE+AX/"
            f"detach-concurrently:{detach['server_version_num']}/"
            "retained:20000"
        )
        print(
            "proposal=0.1.0->0.6.0/"
            "SAFE-MIGR-006+DEFAULT-VERS-010/"
            "depends-on-v0.5"
        )
        print(f"proposal_checksum={proposal_checksum}")
        print(
            "final=switched/contract:not-executed/"
            f"checksum:{business_checksum}"
        )
        return 0
    except (KeyError, OSError, ReviewError, TypeError, ValueError) as exc:
        print(f"ch11 review failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
