#!/usr/bin/env python3
"""Validate ch07 machine-readable plans without freezing dynamic costs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class PlanError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read valid JSON from {path}: {exc}") from exc


def plan_root(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = load_json(path)
    if not isinstance(document, list) or len(document) != 1:
        raise PlanError(f"{path} must contain one EXPLAIN JSON document")
    envelope = document[0]
    if not isinstance(envelope, dict) or not isinstance(
        envelope.get("Plan"), dict
    ):
        raise PlanError(f"{path} has no Plan object")
    return envelope, envelope["Plan"]


def walk(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        if isinstance(child, dict):
            yield from walk(child)


def relation_node(path: Path, relation: str) -> dict[str, Any]:
    _, root = plan_root(path)
    matches = [
        node
        for node in walk(root)
        if node.get("Relation Name") == relation
    ]
    if len(matches) != 1:
        raise PlanError(
            f"{path} expected one node for {relation}, found {len(matches)}"
        )
    return matches[0]


def numeric(node: dict[str, Any], key: str) -> float:
    value = node.get(key)
    if not isinstance(value, (int, float)):
        raise PlanError(f"plan node has no numeric {key}")
    return float(value)


def error_ratio(estimate: float, actual: float) -> float:
    if estimate <= 0 or actual <= 0:
        raise PlanError("error ratio requires positive values")
    return max(estimate / actual, actual / estimate)


def analyze_stats(evidence: Path) -> dict[str, Any]:
    before_present = relation_node(
        evidence / "stats-before-present.json", "ch07_plan_probe"
    )
    after_present = relation_node(
        evidence / "stats-after-present.json", "ch07_plan_probe"
    )
    before_impossible = relation_node(
        evidence / "stats-before-impossible.json", "ch07_plan_probe"
    )
    after_impossible = relation_node(
        evidence / "stats-after-impossible.json", "ch07_plan_probe"
    )

    before_present_est = numeric(before_present, "Plan Rows")
    after_present_est = numeric(after_present, "Plan Rows")
    present_actual = numeric(after_present, "Actual Rows")
    before_impossible_est = numeric(before_impossible, "Plan Rows")
    after_impossible_est = numeric(after_impossible, "Plan Rows")
    impossible_actual = numeric(after_impossible, "Actual Rows")

    before_ratio = error_ratio(before_present_est, present_actual)
    after_ratio = error_ratio(after_present_est, present_actual)

    if present_actual != 25000:
        raise PlanError(
            f"correlated pair actual rows drifted: {present_actual:g}"
        )
    if before_ratio < 2:
        raise PlanError(
            f"single-column estimate is not observably biased: {before_ratio:g}"
        )
    if after_ratio > 1.5 or after_ratio >= before_ratio:
        raise PlanError(
            "extended statistics did not improve correlated estimate"
        )
    if impossible_actual != 0:
        raise PlanError("impossible pair unexpectedly returned rows")
    if before_impossible_est < 1000:
        raise PlanError("pre-fix impossible estimate is unexpectedly small")
    if after_impossible_est > max(10, before_impossible_est / 10):
        raise PlanError(
            "extended statistics did not reduce impossible-pair estimate"
        )

    return {
        "present_actual_rows": int(present_actual),
        "present_estimate_before": int(before_present_est),
        "present_estimate_after": int(after_present_est),
        "present_error_ratio_before": round(before_ratio, 3),
        "present_error_ratio_after": round(after_ratio, 3),
        "impossible_actual_rows": int(impossible_actual),
        "impossible_estimate_before": int(before_impossible_est),
        "impossible_estimate_after": int(after_impossible_est),
    }


def analyze_parameters(evidence: Path) -> dict[str, Any]:
    paths = {
        "custom_hot": evidence / "parameter-custom-hot.json",
        "custom_cold": evidence / "parameter-custom-cold.json",
        "generic_hot": evidence / "parameter-generic-hot.json",
        "generic_cold": evidence / "parameter-generic-cold.json",
    }
    nodes = {
        name: relation_node(path, "ch07_plan_probe")
        for name, path in paths.items()
    }
    values = {
        name: {
            "node_type": node.get("Node Type"),
            "estimate": int(numeric(node, "Plan Rows")),
            "actual": int(numeric(node, "Actual Rows")),
        }
        for name, node in nodes.items()
    }

    if values["custom_hot"]["actual"] != 90000:
        raise PlanError("hot tenant actual rows drifted")
    if values["custom_cold"]["actual"] != 10:
        raise PlanError("cold tenant actual rows drifted")
    if error_ratio(
        values["custom_hot"]["estimate"],
        values["custom_hot"]["actual"],
    ) > 1.5:
        raise PlanError("custom hot estimate is not parameter-sensitive")
    if error_ratio(
        values["custom_cold"]["estimate"],
        values["custom_cold"]["actual"],
    ) > 3:
        raise PlanError("custom cold estimate is not parameter-sensitive")
    if (
        values["generic_hot"]["estimate"]
        != values["generic_cold"]["estimate"]
    ):
        raise PlanError("forced generic estimates differ by parameter")
    if error_ratio(
        values["generic_hot"]["estimate"],
        values["generic_hot"]["actual"],
    ) < 100:
        raise PlanError("generic hot estimate did not expose skew")
    if (
        values["generic_hot"]["node_type"]
        != values["generic_cold"]["node_type"]
    ):
        raise PlanError("forced generic plans did not retain one node type")

    return values


def partition_relations(path: Path) -> list[str]:
    _, root = plan_root(path)
    return sorted(
        {
            str(node["Relation Name"])
            for node in walk(root)
            if str(node.get("Relation Name", "")).startswith(
                "ch07_event_probe_2025q"
            )
        }
    )


def subplans_removed(path: Path) -> int:
    _, root = plan_root(path)
    return sum(
        int(node.get("Subplans Removed", 0))
        for node in walk(root)
        if isinstance(node.get("Subplans Removed", 0), int)
    )


def read_single_int(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise PlanError(f"{path} must contain one integer") from exc


def analyze_partition(evidence: Path) -> dict[str, Any]:
    constant = partition_relations(evidence / "partition-constant.json")
    wrapped = partition_relations(evidence / "partition-wrapped.json")
    generic = partition_relations(evidence / "partition-generic.json")
    removed = subplans_removed(evidence / "partition-generic.json")
    stats_before = read_single_int(
        evidence / "partition-parent-stats-before.txt"
    )
    stats_after = read_single_int(
        evidence / "partition-parent-stats-after.txt"
    )

    if len(constant) != 1:
        raise PlanError(
            f"constant pruning expected one partition, got {constant}"
        )
    if len(wrapped) != 4:
        raise PlanError(
            f"wrapped predicate expected four partitions, got {wrapped}"
        )
    if len(generic) != 1 or removed < 3:
        raise PlanError(
            "generic parameter did not expose execution-time pruning"
        )
    if stats_before != 0 or stats_after <= 0:
        raise PlanError(
            f"parent statistics transition drifted: {stats_before}->{stats_after}"
        )

    return {
        "constant_partition_count": len(constant),
        "wrapped_partition_count": len(wrapped),
        "generic_executed_partition_count": len(generic),
        "generic_subplans_removed": removed,
        "parent_stats_before": stats_before,
        "parent_stats_after": stats_after,
    }


def validate_proposal(repo_root: Path) -> dict[str, str]:
    registry_path = repo_root / "static/labs/ch06/baseline-v0.1.json"
    proposal_path = repo_root / "static/labs/ch07/baseline-v0.2-proposal.json"
    registry = load_json(registry_path)
    proposal = load_json(proposal_path)
    canonical = json.dumps(
        registry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    checksum = hashlib.sha256(canonical).hexdigest()
    if proposal.get("base_checksum") != checksum:
        raise PlanError("v0.2 proposal base checksum disagrees with v0.1")
    if proposal.get("rule_id") != "PREF-PLAN-005":
        raise PlanError("v0.2 proposal must update PREF-PLAN-005")
    for item in proposal.get("evidence", []):
        public_path = item.get("artifact", "")
        if not public_path.startswith("/labs/ch07/"):
            raise PlanError("proposal evidence must use /labs/ch07 paths")
        local_path = repo_root / "static" / public_path.removeprefix("/")
        if not local_path.is_file():
            raise PlanError(f"proposal artifact is missing: {public_path}")
    return {
        "base_baseline": str(proposal.get("base_baseline")),
        "candidate_baseline": str(proposal.get("candidate_baseline")),
        "rule_id": str(proposal.get("rule_id")),
        "base_checksum": checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument(
        "--scope",
        choices=("stats", "parameters", "partition", "all"),
        default="all",
    )
    args = parser.parse_args()

    result: dict[str, Any] = {
        "status": "ok",
        "scope": args.scope,
        "proposal": validate_proposal(args.repo_root.resolve()),
    }
    if args.scope in {"stats", "all"}:
        result["statistics"] = analyze_stats(args.evidence_dir)
    if args.scope in {"parameters", "all"}:
        result["parameters"] = analyze_parameters(args.evidence_dir)
    if args.scope in {"partition", "all"}:
        result["partition"] = analyze_partition(args.evidence_dir)

    summary_path = args.evidence_dir / f"plan-summary-{args.scope}.json"
    summary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("status=ok")
    print(f"scope={args.scope}")
    if "statistics" in result:
        stats = result["statistics"]
        print(
            "correlated_estimate="
            f"{stats['present_estimate_before']}"
            f"->{stats['present_estimate_after']}"
            f"/actual={stats['present_actual_rows']}"
        )
        print(
            "impossible_estimate="
            f"{stats['impossible_estimate_before']}"
            f"->{stats['impossible_estimate_after']}"
            f"/actual={stats['impossible_actual_rows']}"
        )
    if "parameters" in result:
        params = result["parameters"]
        print(
            "custom_hot="
            f"{params['custom_hot']['node_type']}"
            f"/estimate={params['custom_hot']['estimate']}"
            f"/actual={params['custom_hot']['actual']}"
        )
        print(
            "custom_cold="
            f"{params['custom_cold']['node_type']}"
            f"/estimate={params['custom_cold']['estimate']}"
            f"/actual={params['custom_cold']['actual']}"
        )
        print(
            "generic_estimate="
            f"{params['generic_hot']['estimate']}"
            f"/hot_actual={params['generic_hot']['actual']}"
            f"/cold_actual={params['generic_cold']['actual']}"
        )
    if "partition" in result:
        part = result["partition"]
        print(
            "partition_counts="
            f"constant:{part['constant_partition_count']},"
            f"wrapped:{part['wrapped_partition_count']},"
            f"generic:{part['generic_executed_partition_count']}"
        )
        print(
            "partition_parent_stats="
            f"{part['parent_stats_before']}->{part['parent_stats_after']}"
        )
    print(
        "proposal="
        f"{result['proposal']['base_baseline']}"
        f"->{result['proposal']['candidate_baseline']}"
        f"/{result['proposal']['rule_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
