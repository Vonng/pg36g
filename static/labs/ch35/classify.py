#!/usr/bin/env python3
"""Classify chapter 35 blind forensic evidence."""

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
        raise LabError(f"blind packet field {'.'.join(path)} is not integer")
    return current


def boolean_at(value: dict[str, Any], *path: str) -> bool:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise LabError(f"blind packet lacks {'.'.join(path)}")
        current = current[key]
    if not isinstance(current, bool):
        raise LabError(f"blind packet field {'.'.join(path)} is not boolean")
    return current


def classify(packet: dict[str, Any]) -> dict[str, Any]:
    enabled = boolean_at(packet, "checksum", "enabled")
    bad = integer_at(packet, "checksum", "offline_bad_checksums")
    mismatch = boolean_at(packet, "collation", "version_mismatch")
    amcheck = boolean_at(packet, "amcheck", "structural_check_passed")
    relation_kind = packet.get("relation", {}).get("kind")
    physical = (
        enabled
        and bad >= 1
        and relation_kind == "heap"
        and not mismatch
    )
    derived = (
        bad == 0
        and mismatch
        and amcheck
        and relation_kind == "index-derived"
    )
    evidence = [
        {"path": "checksum.enabled", "value": enabled},
        {"path": "checksum.offline_bad_checksums", "value": bad},
        {"path": "relation.kind", "value": relation_kind},
        {"path": "collation.version_mismatch", "value": mismatch},
        {"path": "amcheck.structural_check_passed", "value": amcheck},
    ]
    if physical and not derived:
        route = "RESTORE_FROM_KNOWN_GOOD_COPY"
        first_action = (
            "preserve the corrupted clone and create a new working copy "
            "from a verified source"
        )
    elif derived and not physical:
        route = "REINDEX_AND_REFRESH_COLLATION"
        first_action = (
            "on a working copy, reindex the exact dependent index before "
            "refreshing collation metadata"
        )
    else:
        route = "STOP_AND_ESCALATE"
        first_action = (
            "preserve original evidence, stop repeated experiments, and "
            "name the missing recovery facts"
        )
    return {
        "case_id": packet.get("case_id"),
        "route": route,
        "physical_predicate": physical,
        "derived_predicate": derived,
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
            != "pg36-ch35-classification-contract-v1"
        ):
            raise LabError("classification contract schema drifted")
        required = contract.get("required_packet_fields")
        if not isinstance(required, list) or len(required) != 7:
            raise LabError("classification field contract drifted")
        if not isinstance(packets, list) or len(packets) != 2:
            raise LabError("blind packet set must have exactly two cases")
        identities: set[str] = set()
        results = []
        forbidden = {"truth", "scenario", "expected_route", "hidden"}
        for packet in packets:
            if not isinstance(packet, dict):
                raise LabError("blind packet is not an object")
            if any(key not in packet for key in required):
                raise LabError("blind packet lacks required fields")
            if forbidden.intersection(packet):
                raise LabError("blind packet leaks hidden truth")
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
                "schema": "pg36-ch35-classification-v1",
                "classified_at": utc_now(),
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
