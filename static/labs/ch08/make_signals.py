#!/usr/bin/env python3
"""Normalize ch08 case evidence into a root-cause-neutral signal record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def plan_root(path: Path) -> dict[str, Any]:
    doc = load_json(path)
    if not isinstance(doc, list) or len(doc) != 1:
        raise ValueError(f"{path} is not one EXPLAIN JSON document")
    return doc[0]["Plan"]


def walk(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        yield from walk(child)


def relation_node(path: Path, relation: str) -> dict[str, Any]:
    matches = [
        node
        for node in walk(plan_root(path))
        if node.get("Relation Name") == relation
    ]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one {relation} node")
    return matches[0]


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def estimate_signals(evidence: Path) -> dict[str, Any]:
    generic = relation_node(
        evidence / "generic-hot.json", "ch07_plan_probe"
    )
    custom = relation_node(
        evidence / "custom-hot.json", "ch07_plan_probe"
    )
    return {
        "state": "completed",
        "wait_event_type": None,
        "wait_event": None,
        "blocking_pid_count": 0,
        "plan": {
            "generic_node_type": generic["Node Type"],
            "generic_estimate": int(generic["Plan Rows"]),
            "generic_actual": int(generic["Actual Rows"]),
            "custom_node_type": custom["Node Type"],
            "custom_estimate": int(custom["Plan Rows"]),
            "custom_actual": int(custom["Actual Rows"]),
        },
        "state_restored": True,
        "remaining_workers": 0,
    }


def lock_signals(evidence: Path) -> dict[str, Any]:
    raw = read_kv(evidence / "raw/summary.txt")
    return {
        "state": "active",
        "wait_event_type": raw.get("waiter_wait_event_type"),
        "wait_event": raw.get("waiter_wait_event"),
        "blocking_pid_count": (
            1 if raw.get("waiter_blocked_by", "").isdigit() else 0
        ),
        "plan": None,
        "state_restored": raw.get("state_restored") == "true",
        "remaining_workers": int(raw.get("remaining_workers", "-1")),
    }


def client_signals(evidence: Path) -> dict[str, Any]:
    raw = read_kv(evidence / "raw/summary.txt")
    return {
        "state": raw.get("state"),
        "wait_event_type": raw.get("wait_event_type"),
        "wait_event": raw.get("wait_event"),
        "blocking_pid_count": int(
            raw.get("blocking_pid_count", "-1")
        ),
        "plan": None,
        "state_restored": True,
        "remaining_workers": int(raw.get("remaining_workers", "-1")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("estimate", "lock", "client"), required=True
    )
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()

    builders = {
        "estimate": estimate_signals,
        "lock": lock_signals,
        "client": client_signals,
    }
    signals = builders[args.mode](args.evidence_dir)
    if not signals["state_restored"] or signals["remaining_workers"] != 0:
        raise RuntimeError("case did not restore state or workers")

    output = args.evidence_dir / "signals.json"
    output.write_text(
        json.dumps(signals, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"status=ok signals={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
