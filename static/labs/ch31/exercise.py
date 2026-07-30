#!/usr/bin/env python3
"""Draw chapter 31 tabletop cases and produce a contract-bound reference run."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExerciseError(RuntimeError):
    """Raised when a tabletop exercise cannot be constructed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExerciseError(f"cannot read JSON {path}: {exc}") from exc


def write_private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_scenarios(
    scenarios: list[dict[str, Any]],
    seed: str,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    shuffled = list(scenarios)
    rng.shuffle(shuffled)
    first = shuffled[0]
    second = next(
        row for row in shuffled[1:]
        if row["route"] != first["route"]
    )
    return [first, second]


def blind_packet(
    scenario: dict[str, Any],
    *,
    mode: str,
    incident_id: str,
) -> dict[str, Any]:
    return {
        "schema": "pg36-ch31-blind-packet-v1",
        "incident_id": incident_id,
        "scenario_id": scenario["id"],
        "mode": mode,
        "clock": {
            "start_minute": 0,
            "decision_deadline_minute": 15,
        },
        "initial_signal": scenario["initial_signal"],
        "reported_user_impact": scenario["user_impact"],
        "available_evidence_cards": [
            {
                "id": card["id"],
                "question": card["question"],
                "layer": card["layer"],
                "cost_minutes": card["cost_minutes"],
            }
            for card in scenario["evidence_cards"]
        ],
        "instructions": [
            "state impact, data risk, blast radius, trend, and recoverability",
            "request evidence by card id before choosing a technical route",
            "record facts, hypotheses, actions, expected results, stop lines, and rollback",
            "do not execute a destructive action in this tabletop",
            "issue one stakeholder update before minute 15"
        ],
    }


def reference_roles(mode: str) -> dict[str, str]:
    if mode == "solo":
        return {
            "incident_commander": "solo-oncall",
            "operator": "solo-oncall",
            "scribe": "solo-oncall",
            "business_liaison": "solo-oncall",
        }
    return {
        "incident_commander": "ic-alex",
        "operator": "db-operator-bo",
        "scribe": "scribe-chen",
        "business_liaison": "business-dana",
    }


def model_response(
    scenario: dict[str, Any],
    *,
    mode: str,
    incident_id: str,
) -> dict[str, Any]:
    roles = reference_roles(mode)
    cards = list(scenario["required_cards"])
    actions = []
    for minute, source in zip((1, 5, 10), scenario["safe_actions"]):
        actions.append(
            {
                "minute": minute,
                "action_id": source["id"],
                "risk_class": source["risk_class"],
                "owner": roles["operator"],
                "fact_ids": cards,
                "expected_result": source["expected_result"],
                "stop_condition": source["stop_condition"],
                "rollback": source["rollback"],
            }
        )

    decision_log = [
        {
            "minute": 0,
            "actor": roles["incident_commander"],
            "entry_type": "fact",
            "statement": scenario["initial_signal"],
            "evidence_ids": ["initial-signal"],
            "expected_result": "start scoped triage",
            "stop_condition": "none",
            "rollback": "none",
        },
        {
            "minute": 2,
            "actor": roles["scribe"],
            "entry_type": "fact",
            "statement": "live Pigsty and PostgreSQL identity snapshot bound",
            "evidence_ids": ["live-context"],
            "expected_result": "preserve time, topology, and recovery context",
            "stop_condition": "identity or provenance mismatch",
            "rollback": "none",
        },
        {
            "minute": 6,
            "actor": roles["operator"],
            "entry_type": "fact",
            "statement": "all route-critical evidence cards collected",
            "evidence_ids": cards,
            "expected_result": "route rests on multiple independent layers",
            "stop_condition": "a required card remains unknown",
            "rollback": "none",
        },
        {
            "minute": 8,
            "actor": roles["incident_commander"],
            "entry_type": "decision",
            "statement": (
                f"choose {scenario['route']} with objective "
                f"{scenario['objective']}"
            ),
            "evidence_ids": cards,
            "expected_result": "continue in the matching recovery chapter",
            "stop_condition": scenario["stop_line"],
            "rollback": "return to triage if new evidence contradicts route",
        },
        {
            "minute": 10,
            "actor": roles["operator"],
            "entry_type": "action",
            "statement": scenario["safe_actions"][0]["summary"],
            "evidence_ids": cards,
            "expected_result":
                scenario["safe_actions"][0]["expected_result"],
            "stop_condition":
                scenario["safe_actions"][0]["stop_condition"],
            "rollback": scenario["safe_actions"][0]["rollback"],
        },
        {
            "minute": 12,
            "actor": roles["incident_commander"],
            "entry_type": "decision",
            "statement": "hold every declared dangerous action",
            "evidence_ids": cards,
            "expected_result": "preserve recoverability and avoid escalation",
            "stop_condition": "explicit R3 authority and review are absent",
            "rollback": "none",
        },
        {
            "minute": 15,
            "actor": roles["scribe"],
            "entry_type": "result",
            "statement": "first-response packet complete; handoff recorded",
            "evidence_ids": cards,
            "expected_result": "next chapter owner can continue from evidence",
            "stop_condition": "timeline or owner is missing",
            "rollback": "none",
        },
    ]

    return {
        "schema": "pg36-ch31-response-v1",
        "incident_id": incident_id,
        "scenario_id": scenario["id"],
        "mode": mode,
        "severity": scenario["severity"],
        "severity_basis": scenario["severity_basis"],
        "roles": roles,
        "selected_evidence_cards": cards,
        "evidence_complete_minute": 6,
        "route_decision_minute": 8,
        "route": scenario["route"],
        "response_objective": scenario["objective"],
        "actions": actions,
        "decision_log": decision_log,
        "communications": [
            {
                "minute": 5,
                "audience": "incident stakeholders",
                "known": scenario["user_impact"],
                "unknown": "root cause and final recovery duration",
                "impact": scenario["severity_basis"]["user_impact"],
                "next_update_minute": 15,
            },
            {
                "minute": 15,
                "audience": "incident stakeholders",
                "known": (
                    f"route={scenario['route']}; "
                    f"objective={scenario['objective']}"
                ),
                "unknown": "final recovery result",
                "impact": scenario["severity_basis"]["user_impact"],
                "next_update_minute": 30,
            },
        ],
        "dangerous_actions_executed": [],
        "stop_line": scenario["stop_line"],
        "escalation": scenario["escalation"],
        "production_authorized": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preflight_path = args.evidence_dir / "preflight-evidence.json"
    preflight = read_json(preflight_path)
    scenario_doc = read_json(args.source_dir / "scenarios.json")
    requirements = read_json(args.source_dir / "requirements.json")
    selected = select_scenarios(scenario_doc["scenarios"], args.seed)
    modes = requirements["exercise"]["modes"]

    packets = []
    responses = []
    facilitator = []
    for scenario, mode in zip(selected, modes):
        incident_id = f"PG36-31-{uuid.uuid4().hex[:12].upper()}"
        packets.append(
            blind_packet(
                scenario,
                mode=mode,
                incident_id=incident_id,
            )
        )
        responses.append(
            model_response(
                scenario,
                mode=mode,
                incident_id=incident_id,
            )
        )
        facilitator.append(
            {
                "incident_id": incident_id,
                "mode": mode,
                "scenario": scenario,
            }
        )

    packet_document = {
        "schema": "pg36-ch31-blind-packets-v1",
        "generated_at": utc_now(),
        "preflight_run_id": preflight["run_id"],
        "packets": packets,
    }
    facilitator_document = {
        "schema": "pg36-ch31-facilitator-pack-v1",
        "generated_at": utc_now(),
        "preflight_run_id": preflight["run_id"],
        "cases": facilitator,
    }
    response_document = {
        "schema": "pg36-ch31-responses-v1",
        "generated_at": utc_now(),
        "preflight_run_id": preflight["run_id"],
        "responses": responses,
    }

    blind_path = args.evidence_dir / "blind-packets.json"
    facilitator_path = args.evidence_dir / "facilitator-pack.json"
    responses_path = args.evidence_dir / "responses.json"
    write_private_json(blind_path, packet_document)
    write_private_json(facilitator_path, facilitator_document)
    write_private_json(responses_path, response_document)

    evidence = {
        "schema": "pg36-ch31-exercise-evidence-v1",
        "run_id": str(uuid.uuid4()),
        "preflight_run_id": preflight["run_id"],
        "captured_at": utc_now(),
        "seed_sha256": hashlib.sha256(
            args.seed.encode("utf-8")
        ).hexdigest(),
        "selected_scenarios": [row["id"] for row in selected],
        "selected_routes": [row["route"] for row in selected],
        "modes": modes,
        "files": {
            "preflight_sha256": sha256_file(preflight_path),
            "blind_packets_sha256": sha256_file(blind_path),
            "facilitator_pack_sha256": sha256_file(facilitator_path),
            "responses_sha256": sha256_file(responses_path),
        },
        "online_mutation": "none",
        "real_incident_injected": False,
        "human_competency_claimed": False,
        "production_ch31_gate": "pending",
    }
    write_private_json(
        args.evidence_dir / "exercise-evidence.json",
        evidence,
    )
    print(
        json.dumps(
            {
                "run_id": evidence["run_id"],
                "modes": evidence["modes"],
                "routes": evidence["selected_routes"],
                "status": "exercise-ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
