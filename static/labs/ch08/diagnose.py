#!/usr/bin/env python3
"""Classify a ch08 mystery case without reading its answer artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ratio(estimate: int, actual: int) -> float:
    if estimate <= 0 or actual <= 0:
        return float("inf")
    return max(estimate / actual, actual / estimate)


def classify(signals: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    wait_type = signals.get("wait_event_type")
    wait_event = signals.get("wait_event")
    blockers = signals.get("blocking_pid_count")
    plan = signals.get("plan")

    if wait_type == "Lock" and isinstance(blockers, int) and blockers > 0:
        return (
            "lock-wait",
            [
                "backend is active but waiting on a Lock event",
                "at least one direct blocking PID is present",
            ],
            [
                "not client backpressure: wait type is not Client",
                "not primarily planner bias: executor is blocked before progress",
            ],
        )

    if (
        wait_type == "Client"
        and wait_event == "ClientWrite"
        and blockers == 0
    ):
        return (
            "client-slow-consumer",
            [
                "backend is active at Client/ClientWrite",
                "pg_blocking_pids is empty",
            ],
            [
                "not a database lock chain: no blocker edge exists",
                "not proven I/O/CPU slowness: server is waiting on its client",
            ],
        )

    if isinstance(plan, dict) and wait_type is None and blockers == 0:
        generic_error = ratio(
            int(plan["generic_estimate"]),
            int(plan["generic_actual"]),
        )
        custom_error = ratio(
            int(plan["custom_estimate"]),
            int(plan["custom_actual"]),
        )
        if generic_error >= 100 and custom_error <= 2:
            return (
                "estimate-plan",
                [
                    f"generic cardinality error is {generic_error:.1f}x",
                    f"custom cardinality error is {custom_error:.1f}x",
                    "no Lock or ClientWrite wait was observed",
                ],
                [
                    "not lock-bound: no blocker edge exists",
                    "not slow consumption: no ClientWrite wait exists",
                ],
            )

    raise RuntimeError("signals do not match one unambiguous ch08 class")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    signals = json.loads(args.signals.read_text(encoding="utf-8"))
    diagnosis, evidence, rejected = classify(signals)
    result = {
        "status": "ok",
        "diagnosis": diagnosis,
        "evidence": evidence,
        "rejected_alternatives": rejected,
        "answer_artifact_read": False,
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"status=ok diagnosis={diagnosis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
