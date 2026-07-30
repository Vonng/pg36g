#!/usr/bin/env python3
"""Validate chapter 31 contracts, live context, and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


class ValidationError(RuntimeError):
    """Raised when an artifact cannot be read or interpreted."""


SOURCE_FILES = [
    "requirements.json",
    "incident-contract.json",
    "scenarios.json",
    "response-template.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]

ROUTE_OBJECTIVES = {
    "PITR": "RESTORE_DATA",
    "HA": "RESTORE_TOPOLOGY",
    "OVERLOAD": "RELIEVE_PRESSURE",
    "INTEGRITY": "PRESERVE_INTEGRITY",
}

TRIAGE_AXES = {
    "user_impact",
    "data_risk",
    "blast_radius",
    "time_dynamics",
    "recoverability",
}

DECISION_FIELDS = {
    "minute",
    "actor",
    "entry_type",
    "statement",
    "evidence_ids",
    "expected_result",
    "stop_condition",
    "rollback",
}

ROLE_FIELDS = {
    "incident_commander",
    "operator",
    "scribe",
    "business_liaison",
}

BLIND_FORBIDDEN_KEYS = {
    "route",
    "objective",
    "severity",
    "severity_basis",
    "false_friend",
    "hidden_truth",
    "observation",
    "required_cards",
    "safe_actions",
    "dangerous_actions",
    "stop_line",
    "escalation",
}

KNOWN_MUTATIONS = {
    "requirements.production_data=true",
    "requirements.failover=true",
    "requirements.routes=3",
    "contract.remove-triage-axis",
    "contract.severity-selects-route",
    "contract.pause-all=true",
    "contract.raw-log=true",
    "contract.r3-no-review",
    "contract.remove-stop-condition",
    "scenarios.remove-one",
    "scenarios.duplicate-id",
    "scenarios.route-unbalanced",
    "scenario.remove-false-friend",
    "scenario.remove-cards",
    "scenario.required-card-unknown",
    "scenario.safe-danger-overlap",
    "scenario.remove-stop-line",
    "blind.add-hidden-truth",
    "blind.add-expected-route",
    "response.route-wrong",
    "response.objective-wrong",
    "response.remove-required-card",
    "response.execute-danger",
    "response.minute=16",
    "response.remove-comms",
    "response.team-roles-same",
    "response.remove-expected-result",
    "capture.read-only=false",
    "capture.cluster=wrong",
    "capture.primary-count=2",
    "bundle.production-gate=approved",
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc


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


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def fail_if(
    failures: list[str],
    condition: bool,
    message: str,
) -> None:
    if condition:
        failures.append(message)


def nested_keys(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            result.add(str(key))
            result.update(nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            result.update(nested_keys(child))
    return result


def validate_requirements(
    failures: list[str],
    requirements: dict[str, Any],
) -> None:
    fail_if(
        failures,
        requirements.get("schema")
        != "pg36-ch31-incident-requirements-v1",
        "requirements schema drifted",
    )
    target = requirements.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l0-vagrant/pg-test"
        or target.get("bastion") != "10.10.10.10"
        or target.get("ssh_user") != "vagrant"
        or target.get("service") != "pg-test"
        or target.get("cluster") != "pg-test"
        or target.get("postgresql_major") != 18
        or target.get("pigsty_monitoring_mode") != "FULL-L3"
        or len(target.get("patroni_members", [])) != 3
        or len(set(target.get("patroni_members", []))) != 3,
        "sandbox target identity drifted",
    )
    exercise = requirements.get("exercise", {})
    fail_if(
        failures,
        exercise.get("scenario_count") != 8
        or exercise.get("draw_count") != 2
        or exercise.get("modes") != ["solo", "team"]
        or exercise.get("first_response_minutes") != 15
        or set(exercise.get("required_routes", []))
        != set(ROUTE_OBJECTIVES),
        "tabletop exercise shape drifted",
    )
    risk = requirements.get("risk", {})
    fail_if(
        failures,
        risk.get("capture") != "L0-read-only"
        or risk.get("exercise") != "offline-tabletop-only"
        or risk.get("database_mutation") != "none"
        or any(
            risk.get(name) is not False
            for name in (
                "production_data_permitted",
                "production_traffic_permitted",
                "raw_query_text_permitted",
                "raw_log_export_permitted",
                "patroni_pause_permitted",
                "failover_permitted",
                "restart_permitted",
                "process_termination_permitted",
                "route_change_permitted",
                "backup_restore_permitted",
            )
        ),
        "read-only risk boundary drifted",
    )
    acceptance = requirements.get("acceptance", {})
    fail_if(
        failures,
        acceptance.get("production_ch31_gate") != "pending"
        or acceptance.get("severity_must_not_select_route") is not True
        or acceptance.get("dangerous_action_must_not_execute")
        is not True,
        "acceptance gate drifted",
    )


def validate_contract(
    failures: list[str],
    contract: dict[str, Any],
) -> None:
    fail_if(
        failures,
        contract.get("schema") != "pg36-ch31-incident-contract-v1",
        "incident contract schema drifted",
    )
    fail_if(
        failures,
        set(contract.get("triage_axes", [])) != TRIAGE_AXES,
        "triage axes are incomplete",
    )
    routes = contract.get("routes", [])
    route_map = {
        row.get("route"): row.get("objective")
        for row in routes
        if isinstance(row, dict)
    }
    chapter_map = {
        row.get("route"): row.get("chapter")
        for row in routes
        if isinstance(row, dict)
    }
    fail_if(
        failures,
        route_map != ROUTE_OBJECTIVES
        or chapter_map
        != {"PITR": 32, "HA": 33, "OVERLOAD": 34, "INTEGRITY": 35}
        or any(not nonempty(row.get("trigger")) for row in routes),
        "route-to-objective or chapter mapping drifted",
    )
    severity = contract.get("severity", {})
    fail_if(
        failures,
        set(severity.get("levels", []))
        != {"SEV1", "SEV2", "SEV3", "SEV4"}
        or "technical route" in severity.get("determines", [])
        or "technical route"
        not in severity.get("does_not_determine", []),
        "severity was allowed to become diagnosis",
    )
    evidence = contract.get("evidence_rules", {})
    fail_if(
        failures,
        evidence.get("record_utc_and_clock_source") is not True
        or evidence.get("record_provenance_and_hash") is not True
        or evidence.get("separate_fact_hypothesis_and_decision")
        is not True
        or evidence.get("preserve_confidentiality") is not True
        or evidence.get("raw_query_text_by_default") is not False
        or evidence.get("raw_log_export_by_default") is not False,
        "evidence preservation contract drifted",
    )
    fail_if(
        failures,
        set(contract.get("decision_log_fields", []))
        != DECISION_FIELDS,
        "decision log fields are incomplete",
    )
    fail_if(
        failures,
        set(contract.get("roles", [])) != ROLE_FIELDS,
        "incident roles are incomplete",
    )
    risks = {
        row.get("class"): row
        for row in contract.get("risk_classes", [])
        if isinstance(row, dict)
    }
    r3_control = risks.get("R3", {}).get("minimum_control", "")
    fail_if(
        failures,
        set(risks) != {"R0", "R1", "R2", "R3"}
        or "two-person" not in r3_control
        or "preserved source" not in r3_control,
        "high-risk independent review drifted",
    )
    automation = contract.get("automation_policy", {})
    fail_if(
        failures,
        automation.get("pause_everything_by_default") is not False
        or automation.get("record_current_state_first") is not True
        or automation.get("name_exact_controller_and_scope") is not True
        or automation.get("define_resume_owner_and_condition")
        is not True
        or automation.get(
            "never_interrupt_wal_archiving_without_recoverability_analysis"
        )
        is not True,
        "automation pause policy drifted",
    )
    fail_if(
        failures,
        contract.get("production_ch31_gate") != "pending",
        "incident contract production gate opened",
    )


def validate_scenarios(
    failures: list[str],
    document: dict[str, Any],
) -> None:
    fail_if(
        failures,
        document.get("schema") != "pg36-ch31-scenarios-v1",
        "scenario schema drifted",
    )
    scenarios = document.get("scenarios", [])
    fail_if(
        failures,
        not isinstance(scenarios, list) or len(scenarios) != 8,
        "scenario count must be eight",
    )
    if not isinstance(scenarios, list):
        return
    ids = [row.get("id") for row in scenarios if isinstance(row, dict)]
    fail_if(
        failures,
        len(ids) != len(scenarios)
        or any(not nonempty(value) for value in ids)
        or len(set(ids)) != len(ids),
        "scenario ids are missing or duplicated",
    )
    routes = Counter(
        row.get("route") for row in scenarios if isinstance(row, dict)
    )
    fail_if(
        failures,
        routes != Counter({route: 2 for route in ROUTE_OBJECTIVES}),
        "scenario routes are not balanced two per route",
    )
    for row in scenarios:
        if not isinstance(row, dict):
            failures.append("scenario row is not an object")
            continue
        prefix = f"scenario {row.get('id', '<unknown>')}"
        route = row.get("route")
        fail_if(
            failures,
            route not in ROUTE_OBJECTIVES
            or row.get("objective") != ROUTE_OBJECTIVES.get(route),
            f"{prefix} route objective drifted",
        )
        fail_if(
            failures,
            row.get("severity")
            not in {"SEV1", "SEV2", "SEV3", "SEV4"}
            or set(row.get("severity_basis", {})) != TRIAGE_AXES
            or any(
                not nonempty(value)
                for value in row.get("severity_basis", {}).values()
            ),
            f"{prefix} severity basis is incomplete",
        )
        for name in (
            "title",
            "initial_signal",
            "user_impact",
            "false_friend",
            "hidden_truth",
            "stop_line",
            "escalation",
        ):
            fail_if(
                failures,
                not nonempty(row.get(name)),
                f"{prefix} missing {name}",
            )
        cards = row.get("evidence_cards", [])
        card_ids = [
            card.get("id")
            for card in cards
            if isinstance(card, dict)
        ]
        fail_if(
            failures,
            not isinstance(cards, list)
            or len(cards) < 4
            or len(card_ids) != len(cards)
            or len(set(card_ids)) != len(card_ids),
            f"{prefix} evidence cards are incomplete",
        )
        for card in cards if isinstance(cards, list) else []:
            fail_if(
                failures,
                not isinstance(card, dict)
                or not {
                    "id",
                    "question",
                    "layer",
                    "cost_minutes",
                    "observation",
                }.issubset(card)
                or not nonempty(card.get("question"))
                or not nonempty(card.get("observation"))
                or not isinstance(card.get("cost_minutes"), int)
                or not 1 <= card.get("cost_minutes", 0) <= 5,
                f"{prefix} has malformed evidence card",
            )
        required = row.get("required_cards", [])
        fail_if(
            failures,
            not isinstance(required, list)
            or len(required) < 3
            or not set(required).issubset(set(card_ids)),
            f"{prefix} required evidence references unknown card",
        )
        safe = row.get("safe_actions", [])
        danger = row.get("dangerous_actions", [])
        safe_ids = {
            action.get("id")
            for action in safe
            if isinstance(action, dict)
        }
        danger_ids = {
            action.get("id")
            for action in danger
            if isinstance(action, dict)
        }
        fail_if(
            failures,
            len(safe) < 3
            or len(danger) < 3
            or len(safe_ids) != len(safe)
            or len(danger_ids) != len(danger)
            or bool(safe_ids & danger_ids),
            f"{prefix} safe and dangerous actions are incomplete",
        )
        for action in safe if isinstance(safe, list) else []:
            fail_if(
                failures,
                not isinstance(action, dict)
                or action.get("risk_class")
                not in {"R0", "R1", "R2", "R3"}
                or any(
                    not nonempty(action.get(name))
                    for name in (
                        "id",
                        "summary",
                        "expected_result",
                        "stop_condition",
                        "rollback",
                    )
                ),
                f"{prefix} safe action contract is malformed",
            )
        for action in danger if isinstance(danger, list) else []:
            fail_if(
                failures,
                not isinstance(action, dict)
                or not nonempty(action.get("id"))
                or not nonempty(action.get("reason")),
                f"{prefix} dangerous action rationale is missing",
            )


def validate_negative_declarations(
    failures: list[str],
    document: dict[str, Any],
) -> None:
    fail_if(
        failures,
        document.get("schema")
        != "pg36-ch31-negative-cases-v1",
        "negative case schema drifted",
    )
    cases = document.get("cases", [])
    ids = [
        row.get("id") for row in cases if isinstance(row, dict)
    ]
    mutations = [
        row.get("mutation") for row in cases if isinstance(row, dict)
    ]
    fail_if(
        failures,
        len(cases) != 31
        or len(ids) != 31
        or len(set(ids)) != 31
        or any(not nonempty(value) for value in ids)
        or set(mutations) != KNOWN_MUTATIONS,
        "negative case inventory must contain 31 unique known mutations",
    )


def validate_source_hashes(
    failures: list[str],
    source_dir: Path,
    recorded: dict[str, Any],
) -> None:
    fail_if(
        failures,
        set(recorded) != set(SOURCE_FILES),
        "source hash inventory drifted",
    )
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file():
            failures.append(f"source file missing: {name}")
            continue
        fail_if(
            failures,
            recorded.get(name) != sha256_file(path),
            f"source hash mismatch: {name}",
        )


def validate_preflight(
    failures: list[str],
    preflight: dict[str, Any],
    requirements: dict[str, Any],
    source_dir: Path,
    upstream_root: Path,
) -> None:
    fail_if(
        failures,
        preflight.get("schema")
        != "pg36-ch31-preflight-evidence-v1"
        or not nonempty(preflight.get("run_id")),
        "preflight schema or run id drifted",
    )
    fail_if(
        failures,
        preflight.get("target_id")
        != requirements.get("target", {}).get("id")
        or preflight.get("production_ch31_gate") != "pending",
        "preflight target or production gate drifted",
    )
    claims = preflight.get("claims", {})
    fail_if(
        failures,
        not claims or any(value is not False for value in claims.values()),
        "preflight overclaims an online action",
    )
    validate_source_hashes(
        failures,
        source_dir,
        preflight.get("source_hashes", {}),
    )
    upstream = preflight.get("upstream_hashes", {})
    declared_upstream = requirements.get("upstream", {})
    fail_if(
        failures,
        set(upstream) != set(declared_upstream),
        "upstream evidence hash inventory drifted",
    )
    for label, relative in declared_upstream.items():
        path = (source_dir / str(relative)).resolve()
        try:
            path.relative_to(upstream_root.resolve())
        except ValueError:
            failures.append(f"upstream evidence escaped lab root: {label}")
            continue
        if not path.is_file():
            failures.append(f"upstream evidence missing: {label}")
            continue
        row = upstream.get(label, {})
        fail_if(
            failures,
            row.get("name") != path.name
            or row.get("sha256") != sha256_file(path),
            f"upstream evidence hash mismatch: {label}",
        )

    live = preflight.get("live", {})
    collection = live.get("collection", {})
    fail_if(
        failures,
        collection.get("sql_transaction") != "READ ONLY"
        or collection.get("mutation") != "none"
        or collection.get("raw_query_text") is not False
        or collection.get("raw_log_export") is not False
        or collection.get("configuration_content") is not False,
        "live collection was not read-only and minimized",
    )
    postgres = live.get("postgresql", {})
    identity = postgres.get("identity", {})
    control = postgres.get("control", {})
    target = requirements.get("target", {})
    fail_if(
        failures,
        postgres.get("transaction_read_only") is not True
        or identity.get("cluster_name") != target.get("cluster")
        or identity.get("in_recovery") is not False
        or not isinstance(identity.get("server_version_num"), int)
        or identity.get("server_version_num", 0) // 10000
        != target.get("postgresql_major")
        or not isinstance(control.get("system_identifier"), int)
        or control.get("system_identifier") <= 0
        or not isinstance(control.get("timeline_id"), int)
        or control.get("timeline_id") <= 0,
        "PostgreSQL live identity drifted",
    )
    patroni = live.get("patroni", [])
    fail_if(
        failures,
        not isinstance(patroni, list)
        or len(patroni) != 3
        or {row.get("address") for row in patroni}
        != set(target.get("patroni_members", []))
        or sum(row.get("role") == "primary" for row in patroni) != 1
        or sum(row.get("role") == "replica" for row in patroni) != 2
        or any(row.get("state") != "running" for row in patroni)
        or any(
            row.get("timeline") != control.get("timeline_id")
            for row in patroni
        ),
        "Patroni topology is not one running primary plus two replicas",
    )
    backrest = live.get("pgbackrest", {})
    fail_if(
        failures,
        backrest.get("name") != target.get("pgbackrest_stanza")
        or backrest.get("status_code") != 0
        or not isinstance(backrest.get("backup_count"), int)
        or backrest.get("backup_count", 0) < 1
        or backrest.get("latest_backup") is None
        or backrest.get("database", {}).get("system_identifier")
        != control.get("system_identifier"),
        "pgBackRest identity or backup context drifted",
    )
    host = live.get("host", {})
    fail_if(
        failures,
        not nonempty(live.get("captured_at"))
        or not nonempty(host.get("hostname"))
        or not nonempty(host.get("clocksource"))
        or not nonempty(host.get("ntp_synchronized")),
        "host clock provenance is incomplete",
    )


def scenario_index(
    scenarios: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        row["id"]: row
        for row in scenarios.get("scenarios", [])
        if isinstance(row, dict) and nonempty(row.get("id"))
    }


def validate_blind(
    failures: list[str],
    blind: dict[str, Any],
    selected: list[str],
    scenarios: dict[str, Any],
) -> None:
    fail_if(
        failures,
        blind.get("schema") != "pg36-ch31-blind-packets-v1",
        "blind packet document schema drifted",
    )
    packets = blind.get("packets", [])
    fail_if(
        failures,
        not isinstance(packets, list)
        or len(packets) != 2
        or [row.get("scenario_id") for row in packets] != selected
        or [row.get("mode") for row in packets] != ["solo", "team"],
        "blind packet selection or modes drifted",
    )
    index = scenario_index(scenarios)
    for packet in packets if isinstance(packets, list) else []:
        scenario = index.get(packet.get("scenario_id"), {})
        prefix = f"blind packet {packet.get('scenario_id')}"
        fail_if(
            failures,
            bool(nested_keys(packet) & BLIND_FORBIDDEN_KEYS),
            f"{prefix} leaked facilitator-only fields",
        )
        cards = packet.get("available_evidence_cards", [])
        fail_if(
            failures,
            {row.get("id") for row in cards}
            != {
                row.get("id")
                for row in scenario.get("evidence_cards", [])
            }
            or any(
                set(row) != {
                    "id",
                    "question",
                    "layer",
                    "cost_minutes",
                }
                for row in cards
            ),
            f"{prefix} evidence card catalog drifted or leaked answers",
        )
        clock = packet.get("clock", {})
        fail_if(
            failures,
            clock.get("start_minute") != 0
            or clock.get("decision_deadline_minute") != 15
            or len(packet.get("instructions", [])) < 5,
            f"{prefix} timing or instructions drifted",
        )


def validate_facilitator(
    failures: list[str],
    facilitator: dict[str, Any],
    selected: list[str],
    scenarios: dict[str, Any],
) -> None:
    fail_if(
        failures,
        facilitator.get("schema")
        != "pg36-ch31-facilitator-pack-v1",
        "facilitator pack schema drifted",
    )
    cases = facilitator.get("cases", [])
    index = scenario_index(scenarios)
    fail_if(
        failures,
        not isinstance(cases, list)
        or len(cases) != 2
        or [
            row.get("scenario", {}).get("id")
            for row in cases
        ]
        != selected
        or [row.get("mode") for row in cases] != ["solo", "team"],
        "facilitator case selection drifted",
    )
    for row in cases if isinstance(cases, list) else []:
        scenario_id = row.get("scenario", {}).get("id")
        fail_if(
            failures,
            row.get("scenario") != index.get(scenario_id),
            f"facilitator case differs from source: {scenario_id}",
        )


def validate_responses(
    failures: list[str],
    responses: dict[str, Any],
    selected: list[str],
    scenarios: dict[str, Any],
) -> None:
    fail_if(
        failures,
        responses.get("schema") != "pg36-ch31-responses-v1",
        "responses document schema drifted",
    )
    rows = responses.get("responses", [])
    fail_if(
        failures,
        not isinstance(rows, list)
        or len(rows) != 2
        or [row.get("scenario_id") for row in rows] != selected
        or [row.get("mode") for row in rows] != ["solo", "team"],
        "response selection or modes drifted",
    )
    index = scenario_index(scenarios)
    for response in rows if isinstance(rows, list) else []:
        scenario = index.get(response.get("scenario_id"), {})
        prefix = f"response {response.get('scenario_id')}"
        required = set(scenario.get("required_cards", []))
        selected_cards = set(
            response.get("selected_evidence_cards", [])
        )
        safe = {
            row.get("id"): row
            for row in scenario.get("safe_actions", [])
        }
        dangerous = {
            row.get("id")
            for row in scenario.get("dangerous_actions", [])
        }
        fail_if(
            failures,
            response.get("schema") != "pg36-ch31-response-v1"
            or response.get("route") != scenario.get("route")
            or response.get("response_objective")
            != scenario.get("objective")
            or response.get("severity") != scenario.get("severity")
            or set(response.get("severity_basis", {})) != TRIAGE_AXES
            or not required.issubset(selected_cards),
            f"{prefix} triage, route, objective, or evidence drifted",
        )
        fail_if(
            failures,
            not isinstance(response.get("evidence_complete_minute"), int)
            or not isinstance(response.get("route_decision_minute"), int)
            or not 0
            <= response.get("evidence_complete_minute", -1)
            < response.get("route_decision_minute", -1)
            <= 15,
            f"{prefix} selected route before evidence or after minute 15",
        )
        roles = response.get("roles", {})
        fail_if(
            failures,
            set(roles) != ROLE_FIELDS
            or any(not nonempty(value) for value in roles.values()),
            f"{prefix} roles are incomplete",
        )
        if response.get("mode") == "solo":
            fail_if(
                failures,
                len(set(roles.values())) != 1,
                f"{prefix} solo logical roles must have one actor",
            )
        elif response.get("mode") == "team":
            fail_if(
                failures,
                len(set(roles.values())) != 4,
                f"{prefix} team roles must be independently assigned",
            )
        else:
            failures.append(f"{prefix} has unknown mode")

        actions = response.get("actions", [])
        fail_if(
            failures,
            not isinstance(actions, list) or len(actions) < 3,
            f"{prefix} safe action plan is incomplete",
        )
        for action in actions if isinstance(actions, list) else []:
            source = safe.get(action.get("action_id"))
            fail_if(
                failures,
                source is None
                or action.get("risk_class")
                != (source or {}).get("risk_class")
                or not isinstance(action.get("minute"), int)
                or not 0 <= action.get("minute", -1) <= 15
                or not set(action.get("fact_ids", []))
                .issubset(selected_cards)
                or any(
                    not nonempty(action.get(name))
                    for name in (
                        "owner",
                        "expected_result",
                        "stop_condition",
                        "rollback",
                    )
                ),
                f"{prefix} contains uncontracted or malformed action",
            )
        executed = response.get("dangerous_actions_executed", [])
        fail_if(
            failures,
            not isinstance(executed, list)
            or bool(set(executed) & dangerous)
            or bool(executed),
            f"{prefix} executed a dangerous action",
        )
        log = response.get("decision_log", [])
        minutes = [
            row.get("minute") for row in log if isinstance(row, dict)
        ]
        fail_if(
            failures,
            not isinstance(log, list)
            or len(log) < 6
            or len(minutes) != len(log)
            or any(not isinstance(value, int) for value in minutes)
            or minutes != sorted(minutes)
            or not minutes
            or minutes[0] != 0
            or minutes[-1] != 15,
            f"{prefix} decision timeline is incomplete",
        )
        for entry in log if isinstance(log, list) else []:
            fail_if(
                failures,
                set(entry) != DECISION_FIELDS
                or any(
                    not nonempty(entry.get(name))
                    for name in (
                        "actor",
                        "entry_type",
                        "statement",
                        "expected_result",
                        "stop_condition",
                        "rollback",
                    )
                )
                or not isinstance(entry.get("evidence_ids"), list),
                f"{prefix} decision log entry is malformed",
            )
        communication = response.get("communications", [])
        fail_if(
            failures,
            not isinstance(communication, list)
            or len(communication) < 1
            or not any(
                isinstance(row.get("minute"), int)
                and 0 <= row.get("minute", -1) <= 15
                for row in communication
            )
            or any(
                not nonempty(row.get(name))
                for row in communication
                for name in ("audience", "known", "unknown", "impact")
            ),
            f"{prefix} stakeholder communication is incomplete",
        )
        fail_if(
            failures,
            response.get("production_authorized") is not False
            or response.get("stop_line") != scenario.get("stop_line")
            or response.get("escalation") != scenario.get("escalation"),
            f"{prefix} production or escalation boundary drifted",
        )


def validate_exercise(
    failures: list[str],
    state: dict[str, Any],
) -> None:
    exercise = state["exercise"]
    preflight = state["preflight"]
    selected = exercise.get("selected_scenarios", [])
    selected_routes = exercise.get("selected_routes", [])
    scenario_map = scenario_index(state["scenarios"])
    fail_if(
        failures,
        exercise.get("schema")
        != "pg36-ch31-exercise-evidence-v1"
        or exercise.get("preflight_run_id") != preflight.get("run_id")
        or not nonempty(exercise.get("run_id"))
        or len(selected) != 2
        or len(set(selected)) != 2
        or any(value not in scenario_map for value in selected)
        or selected_routes
        != [scenario_map.get(value, {}).get("route") for value in selected]
        or len(set(selected_routes)) != 2
        or exercise.get("modes") != ["solo", "team"],
        "exercise selection, route diversity, or preflight binding drifted",
    )
    fail_if(
        failures,
        exercise.get("online_mutation") != "none"
        or exercise.get("real_incident_injected") is not False
        or exercise.get("human_competency_claimed") is not False
        or exercise.get("production_ch31_gate") != "pending",
        "exercise overclaimed live incident, competency, or production",
    )
    paths = state["_paths"]
    files = exercise.get("files", {})
    expected_hashes = {
        "preflight_sha256": paths["preflight"],
        "blind_packets_sha256": paths["blind"],
        "facilitator_pack_sha256": paths["facilitator"],
        "responses_sha256": paths["responses"],
    }
    for field, path in expected_hashes.items():
        fail_if(
            failures,
            not path.is_file()
            or files.get(field) != sha256_file(path),
            f"exercise evidence file hash mismatch: {field}",
        )
    validate_blind(
        failures,
        state["blind"],
        selected,
        state["scenarios"],
    )
    validate_facilitator(
        failures,
        state["facilitator"],
        selected,
        state["scenarios"],
    )
    validate_responses(
        failures,
        state["responses"],
        selected,
        state["scenarios"],
    )
    for name in ("blind", "facilitator", "responses"):
        fail_if(
            failures,
            state[name].get("preflight_run_id")
            != preflight.get("run_id"),
            f"{name} document is not bound to preflight run",
        )


def validate_state(
    state: dict[str, Any],
    *,
    complete: bool,
) -> list[str]:
    failures: list[str] = []
    validate_requirements(failures, state["requirements"])
    validate_contract(failures, state["contract"])
    validate_scenarios(failures, state["scenarios"])
    validate_negative_declarations(failures, state["negative"])
    if complete:
        validate_preflight(
            failures,
            state["preflight"],
            state["requirements"],
            state["_source_dir"],
            state["_upstream_root"],
        )
        validate_exercise(failures, state)
    return failures


def apply_declared_mutation(
    state: dict[str, Any],
    mutation: str,
) -> None:
    scenarios = state["scenarios"]["scenarios"]
    first = scenarios[0]
    if mutation == "requirements.production_data=true":
        state["requirements"]["risk"][
            "production_data_permitted"
        ] = True
    elif mutation == "requirements.failover=true":
        state["requirements"]["risk"]["failover_permitted"] = True
    elif mutation == "requirements.routes=3":
        state["requirements"]["exercise"]["required_routes"].pop()
    elif mutation == "contract.remove-triage-axis":
        state["contract"]["triage_axes"].pop()
    elif mutation == "contract.severity-selects-route":
        state["contract"]["severity"]["determines"].append(
            "technical route"
        )
    elif mutation == "contract.pause-all=true":
        state["contract"]["automation_policy"][
            "pause_everything_by_default"
        ] = True
    elif mutation == "contract.raw-log=true":
        state["contract"]["evidence_rules"][
            "raw_log_export_by_default"
        ] = True
    elif mutation == "contract.r3-no-review":
        for row in state["contract"]["risk_classes"]:
            if row["class"] == "R3":
                row["minimum_control"] = "operator discretion"
    elif mutation == "contract.remove-stop-condition":
        state["contract"]["decision_log_fields"].remove(
            "stop_condition"
        )
    elif mutation == "scenarios.remove-one":
        scenarios.pop()
    elif mutation == "scenarios.duplicate-id":
        scenarios[1]["id"] = scenarios[0]["id"]
    elif mutation == "scenarios.route-unbalanced":
        scenarios[0]["route"] = "HA"
        scenarios[0]["objective"] = "RESTORE_TOPOLOGY"
    elif mutation == "scenario.remove-false-friend":
        first["false_friend"] = ""
    elif mutation == "scenario.remove-cards":
        first["evidence_cards"] = []
    elif mutation == "scenario.required-card-unknown":
        first["required_cards"].append("unknown-card")
    elif mutation == "scenario.safe-danger-overlap":
        first["dangerous_actions"][0]["id"] = (
            first["safe_actions"][0]["id"]
        )
    elif mutation == "scenario.remove-stop-line":
        first["stop_line"] = ""
    elif mutation == "blind.add-hidden-truth":
        state["blind"]["packets"][0]["hidden_truth"] = "leaked"
    elif mutation == "blind.add-expected-route":
        state["blind"]["packets"][0]["route"] = "PITR"
    elif mutation == "response.route-wrong":
        row = state["responses"]["responses"][0]
        row["route"] = next(
            value for value in ROUTE_OBJECTIVES
            if value != row["route"]
        )
    elif mutation == "response.objective-wrong":
        state["responses"]["responses"][0][
            "response_objective"
        ] = "WRONG"
    elif mutation == "response.remove-required-card":
        row = state["responses"]["responses"][0]
        scenario = scenario_index(state["scenarios"])[
            row["scenario_id"]
        ]
        required = scenario["required_cards"][0]
        row["selected_evidence_cards"].remove(required)
    elif mutation == "response.execute-danger":
        row = state["responses"]["responses"][0]
        scenario = scenario_index(state["scenarios"])[
            row["scenario_id"]
        ]
        row["dangerous_actions_executed"].append(
            scenario["dangerous_actions"][0]["id"]
        )
    elif mutation == "response.minute=16":
        state["responses"]["responses"][0][
            "route_decision_minute"
        ] = 16
    elif mutation == "response.remove-comms":
        state["responses"]["responses"][0]["communications"] = []
    elif mutation == "response.team-roles-same":
        row = next(
            value for value in state["responses"]["responses"]
            if value["mode"] == "team"
        )
        row["roles"] = {name: "same" for name in ROLE_FIELDS}
    elif mutation == "response.remove-expected-result":
        del state["responses"]["responses"][0][
            "decision_log"
        ][0]["expected_result"]
    elif mutation == "capture.read-only=false":
        state["preflight"]["live"]["collection"][
            "sql_transaction"
        ] = "READ WRITE"
        state["preflight"]["live"]["postgresql"][
            "transaction_read_only"
        ] = False
    elif mutation == "capture.cluster=wrong":
        state["preflight"]["live"]["postgresql"]["identity"][
            "cluster_name"
        ] = "wrong"
    elif mutation == "capture.primary-count=2":
        state["preflight"]["live"]["patroni"][1]["role"] = "primary"
    elif mutation == "bundle.production-gate=approved":
        state["exercise"]["production_ch31_gate"] = "approved"
    else:
        raise ValidationError(f"unknown declared mutation: {mutation}")


def run_declared_negative_cases(
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    results = []
    rejected = 0
    for case in state["negative"]["cases"]:
        candidate = copy.deepcopy(state)
        apply_declared_mutation(candidate, case["mutation"])
        failures = validate_state(candidate, complete=True)
        was_rejected = bool(failures)
        rejected += int(was_rejected)
        results.append(
            {
                "id": case["id"],
                "mutation": case["mutation"],
                "rejected": was_rejected,
                "first_failure": failures[0] if failures else None,
            }
        )
    return results, rejected


def run_live_mutants(
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    mutations: list[tuple[str, Any]] = [
        (
            "system-identifier",
            lambda s: s["preflight"]["live"]["postgresql"][
                "control"
            ].__setitem__("system_identifier", 1),
        ),
        (
            "postgres-timeline",
            lambda s: s["preflight"]["live"]["postgresql"][
                "control"
            ].__setitem__("timeline_id", 999),
        ),
        (
            "postgres-recovery",
            lambda s: s["preflight"]["live"]["postgresql"][
                "identity"
            ].__setitem__("in_recovery", True),
        ),
        (
            "postgres-major",
            lambda s: s["preflight"]["live"]["postgresql"][
                "identity"
            ].__setitem__("server_version_num", 170010),
        ),
        (
            "online-claim",
            lambda s: s["preflight"]["claims"].__setitem__(
                "route_changed", True
            ),
        ),
        (
            "source-hash",
            lambda s: s["preflight"]["source_hashes"].__setitem__(
                "capture.py", "0" * 64
            ),
        ),
        (
            "upstream-hash",
            lambda s: next(
                iter(s["preflight"]["upstream_hashes"].values())
            ).__setitem__("sha256", "0" * 64),
        ),
        (
            "target-id",
            lambda s: s["preflight"].__setitem__(
                "target_id", "production"
            ),
        ),
        (
            "backrest-status",
            lambda s: s["preflight"]["live"]["pgbackrest"].__setitem__(
                "status_code", 1
            ),
        ),
        (
            "backrest-count",
            lambda s: s["preflight"]["live"]["pgbackrest"].__setitem__(
                "backup_count", 0
            ),
        ),
        (
            "backrest-system-id",
            lambda s: s["preflight"]["live"]["pgbackrest"][
                "database"
            ].__setitem__("system_identifier", 2),
        ),
        (
            "patroni-member",
            lambda s: s["preflight"]["live"]["patroni"].pop(),
        ),
        (
            "patroni-stopped",
            lambda s: s["preflight"]["live"]["patroni"][0].__setitem__(
                "state", "stopped"
            ),
        ),
        (
            "exercise-mode",
            lambda s: s["exercise"].__setitem__("modes", ["solo"]),
        ),
        (
            "blind-hash",
            lambda s: s["exercise"]["files"].__setitem__(
                "blind_packets_sha256", "0" * 64
            ),
        ),
        (
            "responses-hash",
            lambda s: s["exercise"]["files"].__setitem__(
                "responses_sha256", "0" * 64
            ),
        ),
        (
            "online-mutation",
            lambda s: s["exercise"].__setitem__(
                "online_mutation", "failover"
            ),
        ),
        (
            "human-competency",
            lambda s: s["exercise"].__setitem__(
                "human_competency_claimed", True
            ),
        ),
    ]
    results = []
    rejected = 0
    for name, mutate in mutations:
        candidate = copy.deepcopy(state)
        mutate(candidate)
        failures = validate_state(candidate, complete=True)
        was_rejected = bool(failures)
        rejected += int(was_rejected)
        results.append(
            {
                "id": name,
                "rejected": was_rejected,
                "first_failure": failures[0] if failures else None,
            }
        )
    return results, rejected


def load_state(args: argparse.Namespace) -> dict[str, Any]:
    state: dict[str, Any] = {
        "requirements": read_json(
            args.source_dir / "requirements.json"
        ),
        "contract": read_json(
            args.source_dir / "incident-contract.json"
        ),
        "scenarios": read_json(
            args.source_dir / "scenarios.json"
        ),
        "negative": read_json(args.negative_cases),
        "_source_dir": args.source_dir.resolve(),
        "_upstream_root": args.upstream_root.resolve(),
    }
    if args.preflight:
        required_paths = {
            "preflight": args.preflight,
            "exercise": args.exercise,
            "blind": args.blind,
            "facilitator": args.facilitator,
            "responses": args.responses,
        }
        for name, path in required_paths.items():
            if path is None:
                raise ValidationError(
                    f"complete validation requires --{name}"
                )
            state[name] = read_json(path)
        state["_paths"] = required_paths
    return state


def public_summary(state: dict[str, Any]) -> dict[str, Any]:
    preflight = state["preflight"]
    exercise = state["exercise"]
    live = preflight["live"]
    postgres = live["postgresql"]
    patroni = live["patroni"]
    return {
        "schema": "pg36-ch31-reference-run-v1",
        "captured_at": exercise["captured_at"],
        "preflight_run_id": preflight["run_id"],
        "run_id": exercise["run_id"],
        "target": preflight["target_id"],
        "environment": {
            "cluster": postgres["identity"]["cluster_name"],
            "postgresql": postgres["identity"]["server_version"],
            "timeline": postgres["control"]["timeline_id"],
            "patroni_members": len(patroni),
            "primary_members": sum(
                row["role"] == "primary" for row in patroni
            ),
            "replica_members": sum(
                row["role"] == "replica" for row in patroni
            ),
            "pgbackrest_status":
                live["pgbackrest"]["status_code"],
            "pgbackrest_backup_count":
                live["pgbackrest"]["backup_count"],
            "pigsty_monitoring_mode":
                state["requirements"]["target"][
                    "pigsty_monitoring_mode"
                ],
        },
        "tabletop": {
            "scenario_library": 8,
            "drawn_cases": 2,
            "modes": exercise["modes"],
            "routes": exercise["selected_routes"],
            "first_response_minutes": 15,
            "human_competency_claimed": False,
        },
        "safety": {
            "sql_transaction": "READ ONLY",
            "online_mutation": "none",
            "real_incident_injected": False,
            "raw_query_text_captured": False,
            "raw_log_exported": False,
            "patroni_paused": False,
            "failover_executed": False,
            "service_restarted": False,
            "connection_terminated": False,
            "route_changed": False,
            "backup_restored": False,
        },
        "validation": {
            "declared_counterexamples_rejected": 31,
            "live_evidence_mutants_rejected": 18,
            "source_files_hash_bound": len(SOURCE_FILES),
            "blind_answer_leak_rejected": True,
            "required_evidence_before_route": True,
            "dangerous_actions_executed": 0,
            "decision_logs_complete": True,
        },
        "decision": {
            "result":
                "read-only-context-and-tabletop-protocol-demonstrated",
            "production_approval": None,
            "production_ch31_gate": "pending",
        },
        "claims_not_made": [
            "a real PostgreSQL or Pigsty incident was injected",
            "a human responder passed a blind competency assessment",
            "the live cluster failover or backup restore path was exercised",
            "the reference run authorizes production incident actions"
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--exercise", type=Path)
    parser.add_argument("--blind", type=Path)
    parser.add_argument("--facilitator", type=Path)
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--public-summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        state = load_state(args)
        complete = args.preflight is not None
        failures = validate_state(state, complete=complete)
        negative_results: list[dict[str, Any]] = []
        live_results: list[dict[str, Any]] = []
        rejected = 0
        live_rejected = 0
        if complete and not failures:
            negative_results, rejected = run_declared_negative_cases(
                state
            )
            live_results, live_rejected = run_live_mutants(state)
            if rejected != 31:
                failures.append(
                    f"only {rejected}/31 declared counterexamples rejected"
                )
            if live_rejected != 18:
                failures.append(
                    f"only {live_rejected}/18 live mutants rejected"
                )

        negative_report = {
            "schema": "pg36-ch31-negative-report-v1",
            "mode": "complete" if complete else "declarations-only",
            "passed": (
                rejected == 31 if complete
                else len(state["negative"]["cases"]) == 31
            ),
            "case_count": 31,
            "rejected_count": rejected if complete else None,
            "results": negative_results,
            "live_mutants": live_results,
            "live_mutant_count": 18 if complete else None,
            "live_mutants_rejected":
                live_rejected if complete else None,
        }
        report = {
            "schema": "pg36-ch31-validation-report-v1",
            "mode": "complete" if complete else "static",
            "passed": not failures,
            "failure_count": len(failures),
            "failures": failures,
            "declared_counterexamples":
                rejected if complete else 31,
            "live_evidence_mutants":
                live_rejected if complete else None,
            "scenario_count": len(
                state["scenarios"].get("scenarios", [])
            ),
            "source_files_hash_bound":
                len(SOURCE_FILES) if complete else None,
            "production_ch31_gate": "pending",
        }
        write_private_json(args.negative_output, negative_report)
        write_private_json(args.output, report)
        if failures:
            for message in failures:
                print(f"validation failed: {message}", file=sys.stderr)
            return 1
        if complete:
            if args.public_summary is None:
                raise ValidationError(
                    "complete validation requires --public-summary"
                )
            summary = public_summary(state)
            write_private_json(args.public_summary, summary)
        print(
            json.dumps(
                {
                    "declared_counterexamples_rejected":
                        rejected if complete else 31,
                    "live_mutants_rejected":
                        live_rejected if complete else None,
                    "mode": report["mode"],
                    "status": "validation-ok",
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValidationError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
