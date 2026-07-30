#!/usr/bin/env python3
"""Classify blind chapter 34 evidence without reading hidden answers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import LabError, read_json, utc_now, write_json


def integer_at(value: dict[str, Any], *path: str) -> int:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise LabError(f"blind packet lacks {'.'.join(path)}")
        current = current[key]
    if isinstance(current, bool) or not isinstance(current, int):
        raise LabError(f"blind packet field {'.'.join(path)} is not an integer")
    return current


def classify(packet: dict[str, Any]) -> dict[str, Any]:
    sessions = integer_at(packet, "connection", "observed_sessions")
    rejections = integer_at(
        packet,
        "connection",
        "connection_rejections",
    )
    waiters = integer_at(packet, "connection", "lock_waiters")
    inactive_slots = integer_at(
        packet,
        "retention",
        "inactive_physical_slots",
    )
    retained = integer_at(packet, "retention", "retained_wal_bytes")

    flow = (
        sessions >= 18
        and rejections >= 1
        and waiters >= 1
        and inactive_slots == 0
    )
    retention = (
        inactive_slots == 1
        and retained >= 33_554_432
        and rejections == 0
    )
    evidence = [
        {
            "path": "connection.observed_sessions",
            "value": sessions,
        },
        {
            "path": "connection.connection_rejections",
            "value": rejections,
        },
        {
            "path": "connection.lock_waiters",
            "value": waiters,
        },
        {
            "path": "retention.inactive_physical_slots",
            "value": inactive_slots,
        },
        {
            "path": "retention.retained_wal_bytes",
            "value": retained,
        },
    ]
    if flow and not retention:
        route = "RELIEVE_FLOW_PRESSURE"
        first_action = (
            "cancel exact fixture sessions, then reduce admission and retry pressure"
        )
    elif retention and not flow:
        route = "PRESERVE_RETENTION_EVIDENCE"
        first_action = (
            "identify the retention owner, preserve evidence, and do not delete pg_wal"
        )
    else:
        route = "STOP_AND_INVESTIGATE"
        first_action = (
            "stop destructive cleanup, preserve evidence, and name unresolved facts"
        )
    return {
        "case_id": packet.get("case_id"),
        "route": route,
        "flow_predicate": flow,
        "retention_predicate": retention,
        "evidence": evidence,
        "first_action": first_action,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        contract = read_json(args.contract)
        packets = read_json(args.packets)
        if (
            contract.get("schema")
            != "pg36-ch34-classification-contract-v1"
        ):
            raise LabError("classification contract schema drifted")
        required = contract.get("required_packet_fields")
        if not isinstance(required, list) or len(required) != 6:
            raise LabError("classification contract fields drifted")
        if not isinstance(packets, list) or len(packets) != 2:
            raise LabError("blind packet set must contain exactly two cases")
        results: list[dict[str, Any]] = []
        identities: set[str] = set()
        forbidden = {"truth", "scenario", "expected_route", "hidden"}
        for packet in packets:
            if not isinstance(packet, dict):
                raise LabError("blind packet is not an object")
            missing = [key for key in required if key not in packet]
            if missing:
                raise LabError(
                    f"blind packet lacks fields: {', '.join(missing)}"
                )
            if forbidden.intersection(packet):
                raise LabError("blind packet leaks hidden truth or route")
            case_id = packet.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise LabError("blind case identity is invalid")
            if case_id in identities:
                raise LabError("blind case identity is duplicated")
            identities.add(case_id)
            results.append(classify(packet))
        write_json(
            args.output,
            {
                "schema": "pg36-ch34-classification-v1",
                "classified_at": utc_now(),
                "common_alert": contract["common_alert"],
                "input_case_count": len(packets),
                "results": results,
                "classifier_inputs": [
                    "classification-contract.json",
                    "blind-packets.json",
                ],
                "hidden_answers_read": False,
            },
        )
    except (KeyError, TypeError, LabError) as exc:
        print(f"classification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
