#!/usr/bin/env python3
"""Validate ch09 index evidence by semantic relationships, not plan costs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class EvidenceError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON {path}: {exc}") from exc


def plan(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = load_json(path)
    if not isinstance(document, list) or len(document) != 1:
        raise EvidenceError(f"{path} is not one EXPLAIN JSON document")
    envelope = document[0]
    if not isinstance(envelope, dict) or not isinstance(
        envelope.get("Plan"), dict
    ):
        raise EvidenceError(f"{path} has no Plan object")
    return envelope, envelope["Plan"]


def walk(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        if isinstance(child, dict):
            yield from walk(child)


def index_names(path: Path) -> set[str]:
    _, root = plan(path)
    return {
        str(node["Index Name"])
        for node in walk(root)
        if node.get("Index Name")
    }


def node_types(path: Path) -> list[str]:
    _, root = plan(path)
    return [str(node.get("Node Type")) for node in walk(root)]


def actual_rows(path: Path) -> int:
    _, root = plan(path)
    value = root.get("Actual Rows")
    if not isinstance(value, (int, float)):
        raise EvidenceError(f"{path} root has no Actual Rows")
    return int(value)


def heap_fetches(path: Path) -> int:
    _, root = plan(path)
    return sum(
        int(node.get("Heap Fetches", 0))
        for node in walk(root)
        if node.get("Node Type") == "Index Only Scan"
    )


def root_wal_bytes(path: Path) -> int:
    _, root = plan(path)
    value = root.get("WAL Bytes")
    if not isinstance(value, (int, float)):
        raise EvidenceError(f"{path} root has no WAL Bytes")
    return int(value)


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise EvidenceError(f"cannot read CSV {path}: {exc}") from exc


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def canonical_checksum(path: Path) -> str:
    value = load_json(path)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analyze_order(evidence: Path) -> dict[str, Any]:
    candidate = "ch09_order_placed_cover_idx"
    before = evidence / "order-before.json"
    after = evidence / "order-after.json"
    custom = evidence / "order-custom.json"
    generic = evidence / "order-generic.json"

    if candidate in index_names(before):
        raise EvidenceError("order candidate unexpectedly exists before build")
    if candidate not in index_names(after):
        raise EvidenceError("literal order query did not use partial index")
    if "Index Only Scan" not in node_types(after):
        raise EvidenceError("order candidate did not support index-only scan")
    if heap_fetches(after) != 0:
        raise EvidenceError("order index-only scan still fetched heap tuples")
    if actual_rows(after) != 10:
        raise EvidenceError("order result cardinality drifted")
    if candidate not in index_names(custom):
        raise EvidenceError("custom placed parameter did not use partial index")
    if candidate in index_names(generic):
        raise EvidenceError(
            "generic status parameter incorrectly used partial index"
        )
    if actual_rows(custom) != 10 or actual_rows(generic) != 10:
        raise EvidenceError("custom/generic order results differ")

    return {
        "actual_rows": 10,
        "literal_index": candidate,
        "index_only_heap_fetches": 0,
        "custom_uses_partial": True,
        "generic_uses_partial": False,
        "before_node_types": node_types(before),
        "after_node_types": node_types(after),
    }


def analyze_inventory(evidence: Path) -> dict[str, Any]:
    candidate = "ch09_inventory_sku_cover_idx"
    before = evidence / "inventory-before.json"
    after = evidence / "inventory-after.json"
    if candidate in index_names(before):
        raise EvidenceError("inventory candidate exists before build")
    if candidate not in index_names(after):
        raise EvidenceError("SKU lookup did not use reverse inventory index")
    if "Index Only Scan" not in node_types(after):
        raise EvidenceError("inventory candidate is not covering")
    if heap_fetches(after) != 0:
        raise EvidenceError("inventory index-only scan fetched heap tuples")
    if actual_rows(after) != 30:
        raise EvidenceError("inventory SKU result cardinality drifted")
    return {
        "actual_rows": 30,
        "candidate_index": candidate,
        "heap_fetches": 0,
        "before_node_types": node_types(before),
        "after_node_types": node_types(after),
        "before_may_use_pg18_skip_scan": True,
    }


def analyze_search(evidence: Path) -> dict[str, Any]:
    candidate = "ch09_search_document_gin_idx"
    before = evidence / "search-before.json"
    after = evidence / "search-after.json"
    if candidate in index_names(before):
        raise EvidenceError("search candidate exists before build")
    if candidate not in index_names(after):
        raise EvidenceError("full-text query did not use GIN candidate")
    if actual_rows(after) != 100:
        raise EvidenceError("search target cardinality drifted")
    return {
        "actual_rows": 100,
        "candidate_index": candidate,
        "before_node_types": node_types(before),
        "after_node_types": node_types(after),
    }


def analyze_event(evidence: Path) -> dict[str, Any]:
    brin_name = "ch09_event_occurred_brin_idx"
    btree_name = "ch09_event_occurred_btree_idx"
    before = evidence / "event-before.json"
    brin = evidence / "event-brin.json"
    btree = evidence / "event-btree.json"
    if brin_name in index_names(before) or btree_name in index_names(before):
        raise EvidenceError("event candidates exist before build")
    if brin_name not in index_names(brin):
        raise EvidenceError("event range did not use BRIN")
    if btree_name not in index_names(btree):
        raise EvidenceError("event range did not use B-tree comparison")
    if {actual_rows(before), actual_rows(brin), actual_rows(btree)} != {600}:
        raise EvidenceError("event result cardinality drifted")

    catalog = read_csv(evidence / "catalog-before-rejection.csv")
    sizes = {
        row["index_name"]: int(row["index_bytes"])
        for row in catalog
        if row["index_name"] in {brin_name, btree_name}
    }
    if set(sizes) != {brin_name, btree_name}:
        raise EvidenceError("event index sizes are missing")
    if sizes[brin_name] * 10 >= sizes[btree_name]:
        raise EvidenceError(
            "BRIN is not at least an order of magnitude smaller"
        )

    final_names = {
        row["index_name"] for row in read_csv(evidence / "catalog-final.csv")
    }
    if brin_name not in final_names or btree_name in final_names:
        raise EvidenceError("event retain/reject final catalog is wrong")
    return {
        "actual_rows": 600,
        "brin_bytes": sizes[brin_name],
        "btree_bytes": sizes[btree_name],
        "brin_size_fraction": round(
            sizes[brin_name] / sizes[btree_name], 6
        ),
        "brin_retained": True,
        "btree_rejected_and_removed": True,
    }


def analyze_write(evidence: Path) -> dict[str, Any]:
    rows = {
        row["relname"]: row
        for row in read_csv(evidence / "write-stats.csv")
    }
    expected = {"ch09_write_base", "ch09_write_indexed"}
    if set(rows) != expected:
        raise EvidenceError("write stats do not contain both twin tables")
    base_updates = int(rows["ch09_write_base"]["n_tup_upd"])
    base_hot = int(rows["ch09_write_base"]["n_tup_hot_upd"])
    indexed_updates = int(rows["ch09_write_indexed"]["n_tup_upd"])
    indexed_hot = int(rows["ch09_write_indexed"]["n_tup_hot_upd"])
    if base_updates != 50000 or indexed_updates != 50000:
        raise EvidenceError("write update counts drifted")
    if base_hot / base_updates < 0.8:
        raise EvidenceError("unindexed counter did not preserve HOT")
    if indexed_hot != 0:
        raise EvidenceError("indexed counter unexpectedly allowed HOT")

    base_wal = root_wal_bytes(evidence / "write-base.json")
    indexed_wal = root_wal_bytes(evidence / "write-indexed.json")
    if indexed_wal <= base_wal:
        raise EvidenceError("volatile index did not increase statement WAL")
    return {
        "base_updates": base_updates,
        "base_hot_updates": base_hot,
        "base_hot_ratio": round(base_hot / base_updates, 4),
        "indexed_updates": indexed_updates,
        "indexed_hot_updates": indexed_hot,
        "indexed_hot_ratio": 0.0,
        "base_wal_bytes": base_wal,
        "indexed_wal_bytes": indexed_wal,
        "indexed_wal_gt_base": True,
    }


def analyze_concurrent(evidence: Path) -> dict[str, Any]:
    summary = read_kv(evidence / "concurrent-failure/summary.txt")
    required = {
        "status": "ok",
        "create_expected_exit": "3",
        "create_sqlstate": "23505",
        "invalid_index_observed": "true",
        "exact_drop": "true",
        "remaining_failed_indexes": "0",
    }
    if any(summary.get(key) != value for key, value in required.items()):
        raise EvidenceError("concurrent failure/recovery summary drifted")
    rows = read_csv(
        evidence / "concurrent-failure/invalid-index.csv"
    )
    if len(rows) != 1 or rows[0].get("indisvalid") != "f":
        raise EvidenceError("invalid index catalog evidence is missing")
    return {
        "sqlstate": "23505",
        "invalid_observed": True,
        "exact_drop": True,
        "remaining": 0,
    }


def validate_decisions(evidence: Path, repo_root: Path) -> dict[str, int]:
    path = repo_root / "static/labs/ch09/index-decisions.json"
    document = load_json(path)
    decisions = document.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 8:
        raise EvidenceError("index decision ledger must contain 8 entries")
    counts = {"retain": 0, "reject": 0}
    for decision in decisions:
        outcome = decision.get("decision")
        if outcome not in counts:
            raise EvidenceError("decision must be retain or reject")
        counts[outcome] += 1
        for artifact in decision.get("evidence", []):
            if not (evidence / artifact).is_file():
                raise EvidenceError(
                    f"decision evidence is missing: {artifact}"
                )
    if counts != {"retain": 4, "reject": 4}:
        raise EvidenceError(f"unexpected decision balance: {counts}")
    return counts


def validate_proposal(repo_root: Path) -> dict[str, str]:
    baseline = repo_root / "static/labs/ch06/baseline-v0.1.json"
    dependencies = [
        repo_root / "static/labs/ch07/baseline-v0.2-proposal.json",
        repo_root / "static/labs/ch08/baseline-v0.3-proposal.json",
    ]
    proposal_path = (
        repo_root / "static/labs/ch09/baseline-v0.4-proposal.json"
    )
    proposal = load_json(proposal_path)
    if proposal.get("base_checksum") != canonical_checksum(baseline):
        raise EvidenceError("v0.4 base checksum drifted")
    declared = proposal.get("depends_on_candidates")
    if not isinstance(declared, list) or len(declared) != 2:
        raise EvidenceError("v0.4 must declare v0.2 and v0.3 dependencies")
    actual_dependency_checksums = [
        canonical_checksum(path) for path in dependencies
    ]
    declared_checksums = [
        item.get("proposal_checksum") for item in declared
    ]
    if declared_checksums != actual_dependency_checksums:
        raise EvidenceError("v0.4 dependency checksum drifted")
    if proposal.get("rule_id") != "PREF-PLAN-005":
        raise EvidenceError("v0.4 proposal must update PREF-PLAN-005")
    for item in proposal.get("evidence", []):
        public_path = item.get("artifact", "")
        if not public_path.startswith("/labs/ch09/"):
            raise EvidenceError("v0.4 evidence path is outside ch09")
        local_path = repo_root / "static" / public_path.removeprefix("/")
        if not local_path.is_file():
            raise EvidenceError(f"missing proposal artifact: {public_path}")
    return {
        "base_baseline": str(proposal.get("base_baseline")),
        "candidate_baseline": str(proposal.get("candidate_baseline")),
        "rule_id": str(proposal.get("rule_id")),
    }


def validate_final(evidence: Path) -> dict[str, Any]:
    text = (evidence / "verify.txt").read_text(encoding="utf-8")
    checksum = "f8a7bfae59c6d16cd323abecfefe1014"
    if f"relation_checksum={checksum}" not in text:
        raise EvidenceError("ch04-v1 checksum drifted")
    if "rejected_or_failed_indexes=0" not in text:
        raise EvidenceError("final rejected-index cleanup did not pass")
    if "active_lab_workers=0" not in text:
        raise EvidenceError("final worker cleanup did not pass")
    return {
        "relation_checksum": checksum,
        "rejected_or_failed_indexes": 0,
        "active_lab_workers": 0,
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
        "order": analyze_order(evidence),
        "inventory": analyze_inventory(evidence),
        "search": analyze_search(evidence),
        "event": analyze_event(evidence),
        "write": analyze_write(evidence),
        "concurrent_failure": analyze_concurrent(evidence),
        "decisions": validate_decisions(evidence, repo_root),
        "proposal": validate_proposal(repo_root),
        "final": validate_final(evidence),
    }
    output = evidence / "index-summary.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("status=ok")
    print(
        "order=partial-covering/index-only/"
        "custom:true/generic:false/rows:10"
    )
    print("inventory=reverse-covering/heap-fetches:0/rows:30")
    print("search=gin/rows:100")
    print(
        "event=brin-retained/btree-rejected/"
        f"size-fraction:{result['event']['brin_size_fraction']}"
    )
    print(
        "write="
        f"hot:{result['write']['base_hot_ratio']}"
        f"->0/wal:{result['write']['base_wal_bytes']}"
        f"->{result['write']['indexed_wal_bytes']}"
    )
    print("concurrent=23505/invalid-observed/exact-drop/remaining:0")
    print("decisions=retain:4/reject:4")
    print(
        "proposal=0.1.0->0.4.0/"
        "PREF-PLAN-005/depends-on-v0.2+v0.3"
    )
    print(
        "final=workers:0/rejected:0/"
        "checksum:f8a7bfae59c6d16cd323abecfefe1014"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
