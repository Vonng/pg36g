#!/usr/bin/env python3
"""Validate chapter 24 governance contracts and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


ARTIFACT_NAMES = [
    "requirements.json",
    "service-card.json",
    "slo-policy.json",
    "observation-contract.json",
    "alert-candidates.json",
    "sop-catalog.json",
    "change-policy.json",
    "evidence-retention.json",
]

SOURCE_NAMES = [
    *ARTIFACT_NAMES,
    "negative-cases.json",
    "governance-adr.md",
    "lab-contract.md",
    "dependency-map.mmd",
    "build_evidence.py",
    "validate.py",
    "review.py",
    "task.sh",
]


class ValidationError(RuntimeError):
    """Raised when an input artifact cannot be interpreted."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--negative-cases", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail_if(
    failures: list[str],
    condition: bool,
    message: str,
) -> None:
    if condition:
        failures.append(message)


def index_by(
    rows: Any,
    key: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get(key), str):
            result[str(row[key])] = row
    return result


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nested_get(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValidationError(f"nested field does not exist: {path}")
        current = current[part]
    return current


def load_contracts(source_dir: Path) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for name in ARTIFACT_NAMES:
        value = read_json(source_dir / name)
        if not isinstance(value, dict):
            raise ValidationError(f"artifact is not an object: {name}")
        contracts[name] = value
    return contracts


def validate_requirements(
    failures: list[str],
    requirements: dict[str, Any],
) -> None:
    fail_if(
        failures,
        requirements.get("schema")
        != "pg36-ch24-governance-requirements-v1",
        "requirements schema drifted",
    )
    target = requirements.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("service_id") != "pg36_shop"
        or target.get("environment") != "l2-sandbox",
        "requirements target identity drifted",
    )
    fail_if(
        failures,
        target.get("production_data") is not False
        or target.get("production_traffic") is not False
        or target.get("production_slo_claimed") is not False,
        "requirements promoted sandbox scope to production",
    )
    required = set(requirements.get("required_artifacts", []))
    fail_if(
        failures,
        not {
            "service-card.json",
            "slo-policy.json",
            "observation-contract.json",
            "alert-candidates.json",
            "sop-catalog.json",
            "change-policy.json",
            "evidence-retention.json",
        }.issubset(required),
        "required artifact inventory is incomplete",
    )
    upstream = requirements.get("upstream_reference_contract", {})
    fail_if(
        failures,
        set(upstream) != {"ch20", "ch21", "ch22", "ch23"},
        "upstream reference set drifted",
    )
    fail_if(
        failures,
        len(requirements.get("hard_rejections", [])) < 10,
        "hard rejection policy is incomplete",
    )


def validate_service_card(
    failures: list[str],
    requirements: dict[str, Any],
    card: dict[str, Any],
) -> None:
    fail_if(
        failures,
        card.get("schema") != "pg36-ch24-service-card-v1",
        "service-card schema drifted",
    )
    fail_if(
        failures,
        card.get("service_id") != "pg36_shop"
        or card.get("environment") != "l2-sandbox",
        "service-card identity drifted",
    )
    scope = card.get("scope", {})
    fail_if(
        failures,
        scope.get("production_data") is not False
        or scope.get("production_traffic") is not False
        or scope.get("production_slo_claimed") is not False
        or scope.get("synthetic_only") is not True,
        "service card hid the nonproduction boundary",
    )
    owners = index_by(card.get("owner_functions"), "function")
    required_owners = set(
        requirements.get("required_owner_functions", [])
    )
    fail_if(
        failures,
        set(owners) != required_owners,
        "owner function set is incomplete or contains an unknown function",
    )
    role_ids: list[str] = []
    for owner_name in sorted(required_owners):
        owner = owners.get(owner_name, {})
        role_id = owner.get("role_id")
        if isinstance(role_id, str):
            role_ids.append(role_id)
        fail_if(
            failures,
            not nonempty_text(role_id)
            or not owner.get("accountable_for")
            or not nonempty_text(owner.get("on_call_route"))
            or owner.get("individual_name_recorded") is not False,
            f"owner contract is incomplete: {owner_name}",
        )
    fail_if(
        failures,
        len(role_ids) != len(set(role_ids)),
        "two owner functions share one role identity",
    )
    tier = card.get("service_tier", {})
    fail_if(
        failures,
        tier.get("production_tier") is not False
        or len(tier.get("obligations", {})) < 5,
        "service tier is a label rather than a bundle of obligations",
    )
    dependencies = index_by(card.get("dependencies"), "id")
    fail_if(
        failures,
        len(dependencies) < 6,
        "dependency map is incomplete",
    )
    for dependency_id, dependency in dependencies.items():
        fail_if(
            failures,
            dependency.get("owner_function") not in required_owners
            or not nonempty_text(dependency.get("relationship"))
            or not nonempty_text(dependency.get("failure_semantics")),
            f"dependency lacks semantics or owner: {dependency_id}",
        )
    layers = index_by(card.get("health_layers"), "id")
    required_layers = set(requirements.get("required_health_layers", []))
    fail_if(
        failures,
        set(layers) != required_layers,
        "service health layers drifted",
    )
    for layer_id, layer in layers.items():
        fail_if(
            failures,
            not nonempty_text(layer.get("question"))
            or not layer.get("evidence_examples")
            or layer.get("sufficient_for_service_health") is not False,
            f"one component layer was treated as sufficient health: {layer_id}",
        )
    fail_if(
        failures,
        card.get("service_health_requires_all_layers_and_user_contract")
        is not True,
        "service health does not require the complete user contract",
    )
    escalation = card.get("escalation_paths", [])
    fail_if(
        failures,
        {row.get("severity") for row in escalation}
        != {"SEV-1", "SEV-2", "ticket"},
        "escalation path set drifted",
    )
    fail_if(
        failures,
        len(card.get("known_production_gaps", [])) < 5,
        "production gaps were hidden",
    )


def validate_slo_policy(
    failures: list[str],
    requirements: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    fail_if(
        failures,
        policy.get("schema") != "pg36-ch24-slo-policy-v1",
        "SLO policy schema drifted",
    )
    fail_if(
        failures,
        policy.get("service_id") != "pg36_shop"
        or policy.get("production_approval") is not False,
        "SLO policy identity or production boundary drifted",
    )
    principles = policy.get("principles", {})
    fail_if(
        failures,
        principles.get("one_hundred_percent_ratio_target_allowed")
        is not False
        or principles.get("planned_maintenance_in_user_slo") is not True
        or principles.get("database_instance_health_is_user_sli")
        is not False
        or principles.get("missing_data_default")
        != "unknown-and-monitored"
        or principles.get("correctness_can_be_averaged_away")
        is not False
        or principles.get("backup_success_equals_restore_readiness")
        is not False,
        "core SLO principles drifted",
    )
    window = policy.get("window_policy", {})
    fail_if(
        failures,
        window.get("primary_window") != "rolling-28d"
        or window.get("duration_seconds") != 28 * 24 * 60 * 60
        or window.get("calendar_report_is_distinct") is not True
        or len(window.get("low_traffic_strategy", [])) < 3,
        "window or low-traffic policy drifted",
    )
    objectives = index_by(policy.get("objectives"), "id")
    required_ids = set(requirements.get("required_objective_ids", []))
    fail_if(
        failures,
        set(objectives) != required_ids,
        "objective set drifted",
    )
    for objective_id in (
        "SLO-AVAILABILITY",
        "SLO-LATENCY",
        "SLO-FRESHNESS",
    ):
        objective = objectives.get(objective_id, {})
        target = objective.get("target")
        fail_if(
            failures,
            objective.get("kind") != "ratio_slo"
            or not isinstance(target, (int, float))
            or isinstance(target, bool)
            or not 0 < float(target) < 1
            or not nonempty_text(objective.get("eligible_event"))
            or not nonempty_text(objective.get("good_event"))
            or not nonempty_text(objective.get("measurement_point"))
            or objective.get("component_health_proxy") is not False,
            f"ratio SLO is not a measurable user-event contract: {objective_id}",
        )
    availability = objectives.get("SLO-AVAILABILITY", {})
    expected_events = (
        availability.get("sample_event_volume", 0)
        * (1 - availability.get("target", 0))
    )
    expected_seconds = (
        window.get("duration_seconds", 0)
        * (1 - availability.get("target", 0))
    )
    fail_if(
        failures,
        not math.isclose(
            expected_events,
            availability.get("sample_error_budget_events", -1),
            rel_tol=0,
            abs_tol=1e-6,
        )
        or not math.isclose(
            expected_seconds,
            availability.get("equivalent_time_budget_seconds", -1),
            rel_tol=0,
            abs_tol=1e-6,
        )
        or not math.isclose(
            expected_seconds / 60,
            availability.get("equivalent_time_budget_minutes", -1),
            rel_tol=0,
            abs_tol=1e-6,
        ),
        "availability error-budget arithmetic drifted",
    )
    correctness = objectives.get("CTRL-CORRECTNESS", {})
    fail_if(
        failures,
        correctness.get("kind") != "control_objective"
        or correctness.get("ratio_target") is not None
        or "freeze" not in str(correctness.get("failure_action", "")).lower()
        or "zero" not in str(correctness.get("success_condition", "")).lower(),
        "correctness was weakened into an average ratio",
    )
    restore = objectives.get("CTRL-RESTORE-READINESS", {})
    fail_if(
        failures,
        restore.get("kind") != "control_objective"
        or restore.get("maximum_evidence_age_days") != 90
        or "isolated restore" not in str(
            restore.get("success_condition", "")
        ).lower(),
        "restore readiness no longer requires a recent isolated restore",
    )
    exclusions = policy.get("exclusion_policy", {})
    fail_if(
        failures,
        exclusions.get("planned_maintenance_excluded") is not False
        or exclusions.get("retroactive_exclusion_allowed") is not False
        or len(exclusions.get("exception_requirements", [])) < 6,
        "SLO exclusions can hide maintenance or be changed retroactively",
    )
    burn = policy.get("burn_rate_policy", {})
    expected_burn = {
        ("page", "1h", "5m", 14.4, 0.02),
        ("page", "6h", "30m", 6, 0.05),
        ("ticket", "3d", "6h", 1, 0.1),
    }
    observed_burn = {
        (
            row.get("route"),
            row.get("long_window"),
            row.get("short_window"),
            row.get("burn_rate"),
            row.get("budget_fraction"),
        )
        for row in burn.get("alerts", [])
    }
    fail_if(
        failures,
        burn.get("starting_points_require_tuning") is not True
        or observed_burn != expected_burn,
        "multiwindow burn-rate starting points drifted",
    )
    states = index_by(
        policy.get("error_budget_policy", {}).get("states"),
        "id",
    )
    fail_if(
        failures,
        set(states) != {"healthy", "watch", "constrained", "exhausted"},
        "error-budget state machine drifted",
    )
    for state_id, state in states.items():
        fail_if(
            failures,
            not state.get("actions"),
            f"error-budget state has no consequence: {state_id}",
        )
    fail_if(
        failures,
        len(
            policy.get("error_budget_policy", {}).get(
                "gaming_prohibited",
                [],
            )
        )
        < 4,
        "SLO gaming controls are incomplete",
    )


def validate_observation_contract(
    failures: list[str],
    requirements: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    fail_if(
        failures,
        contract.get("schema")
        != "pg36-ch24-observation-contract-v1",
        "observation contract schema drifted",
    )
    fail_if(
        failures,
        contract.get("service_id") != "pg36_shop"
        or contract.get("implementation_target") != "chapter-25",
        "observation contract identity or handoff drifted",
    )
    labels = contract.get("identity_labels", {})
    fail_if(
        failures,
        set(labels.get("pigsty_required", []))
        != {"cls", "ins", "ip"},
        "Pigsty identity label contract drifted",
    )
    fail_if(
        failures,
        not {
            "customer_id",
            "tenant_id",
            "order_id",
            "raw_sql",
            "error_message",
        }.issubset(set(labels.get("forbidden_unbounded_labels", []))),
        "unbounded or sensitive labels are not prohibited",
    )
    sources = index_by(contract.get("sli_sources"), "objective_id")
    required_ids = set(requirements.get("required_objective_ids", []))
    fail_if(
        failures,
        set(sources) != required_ids,
        "one or more objectives lack an observation source",
    )
    for objective_id, source in sources.items():
        missing = str(source.get("missing_semantics", "")).lower()
        fail_if(
            failures,
            not nonempty_text(source.get("source"))
            or not nonempty_text(source.get("metric_type"))
            or not source.get("dimensions")
            or not nonempty_text(source.get("query_template"))
            or not nonempty_text(source.get("fallback"))
            or not missing
            or missing.strip() == "healthy"
            or (
                "unknown" not in missing
                and "failure" not in missing
                and "failed" not in missing
            ),
            f"SLI source is incomplete or fail-open: {objective_id}",
        )
    components = index_by(
        contract.get("component_telemetry"),
        "id",
    )
    fail_if(
        failures,
        len(components) < 4
        or "PIGSTY-CORRELATION" not in components
        or set(
            components.get("PIGSTY-CORRELATION", {}).get(
                "required_labels",
                [],
            )
        )
        != {"cls", "ins", "ip"},
        "component telemetry or Pigsty correlation contract drifted",
    )
    meta = contract.get("metamonitoring", {})
    fail_if(
        failures,
        meta.get("required") is not True
        or meta.get("missing_is_healthy") is not False
        or len(meta.get("checks", [])) < 5,
        "monitoring path is not itself monitored",
    )


def validate_alerts(
    failures: list[str],
    requirements: dict[str, Any],
    alerts: dict[str, Any],
) -> None:
    fail_if(
        failures,
        alerts.get("schema") != "pg36-ch24-alert-candidates-v1",
        "alert candidate schema drifted",
    )
    accepted = index_by(alerts.get("accepted"), "id")
    fail_if(
        failures,
        len(accepted) != 7,
        "accepted alert inventory drifted",
    )
    objective_ids = set(requirements.get("required_objective_ids", []))
    for alert_id, alert in accepted.items():
        required_fields = (
            "user_impact",
            "owner_function",
            "runbook_id",
            "first_safe_action",
            "verification",
            "dashboard",
            "missing_semantics",
            "test_id",
        )
        fail_if(
            failures,
            alert.get("route") not in {"page", "ticket"}
            or any(
                not nonempty_text(alert.get(field))
                for field in required_fields
            ),
            f"accepted alert is not owned and actionable: {alert_id}",
        )
        fail_if(
            failures,
            alert.get("objective_id") is not None
            and alert.get("objective_id") not in objective_ids,
            f"alert references an unknown objective: {alert_id}",
        )
        fail_if(
            failures,
            alert.get("route") == "page"
            and alert.get("class") in {"cause", "capacity"},
            f"cause or capacity forecast pages directly: {alert_id}",
        )
        fail_if(
            failures,
            alert.get("class") == "capacity"
            and alert.get("route") != "ticket",
            f"capacity forecast is not a ticket: {alert_id}",
        )
    availability_burn = {
        (
            row.get("route"),
            row.get("long_window"),
            row.get("short_window"),
            row.get("burn_rate"),
        )
        for row in accepted.values()
        if row.get("objective_id") == "SLO-AVAILABILITY"
    }
    fail_if(
        failures,
        availability_burn
        != {
            ("page", "1h", "5m", 14.4),
            ("page", "6h", "30m", 6),
            ("ticket", "3d", "6h", 1),
        },
        "availability multiwindow alert set drifted",
    )
    diagnostic = alerts.get("diagnostic_only", [])
    fail_if(
        failures,
        len(diagnostic) < 3
        or any(row.get("route") == "page" for row in diagnostic),
        "diagnostic-only causes page directly",
    )
    rejected = alerts.get("rejected", [])
    fail_if(
        failures,
        len(rejected) != 1,
        "the actionless rejected candidate is missing",
    )
    if len(rejected) == 1:
        candidate = rejected[0]
        fail_if(
            failures,
            candidate.get("decision") != "rejected"
            or candidate.get("proposed_route") != "page"
            or candidate.get("user_impact") is not None
            or candidate.get("owner_function") is not None
            or candidate.get("runbook_id") is not None
            or candidate.get("first_safe_action") is not None
            or not nonempty_text(candidate.get("replacement")),
            "the actionless page was accepted or incompletely rejected",
        )


def validate_sops(
    failures: list[str],
    requirements: dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    fail_if(
        failures,
        catalog.get("schema") != "pg36-ch24-sop-catalog-v1",
        "SOP catalog schema drifted",
    )
    fail_if(
        failures,
        catalog.get("service_id") != "pg36_shop"
        or catalog.get("production_approval") is not False,
        "SOP catalog identity or production boundary drifted",
    )
    documents = index_by(catalog.get("documents"), "capability")
    required = set(requirements.get("required_sop_capabilities", []))
    fail_if(
        failures,
        set(documents) != required,
        "required SOP capability set drifted",
    )
    for capability, document in documents.items():
        fail_if(
            failures,
            document.get("risk_class") not in {"L2", "L3"}
            or document.get("owner_function")
            == document.get("approver_function")
            or not nonempty_text(document.get("trigger"))
            or document.get("exact_target_required") is not True
            or document.get("blast_radius_required") is not True
            or len(document.get("prerequisites", [])) < 4
            or len(document.get("procedure_phases", [])) < 5
            or len(document.get("stop_conditions", [])) < 3
            or len(document.get("verification", [])) < 3
            or not nonempty_text(
                document.get("rollback_or_roll_forward")
            )
            or len(document.get("evidence", [])) < 5
            or document.get("reference_is_production_proof") is not False,
            f"SOP is not executable or overclaims proof: {capability}",
        )
    restore = documents.get("backup_and_restore", {})
    restore_verification = " ".join(
        str(value) for value in restore.get("verification", [])
    ).lower()
    fail_if(
        failures,
        "target marker" not in restore_verification
        or "identity" not in restore_verification
        or "stopped" not in restore_verification,
        "restore SOP accepts backup completion without restore checks",
    )
    expected_references = {
        "backup_and_restore": (
            "ch21/restore-run.json",
            "run_20260729T201040Z_961665aa",
        ),
        "planned_switchover_and_failover": (
            "ch20/drill-run.json",
            "475e9b47-bc35-4687-87da-012f1d5ea455",
        ),
        "access_and_credential_rotation": (
            "ch23/security-run.json",
            "64b857a6-8d8f-46e2-9462-3f097a95a69f",
        ),
    }
    for capability, expected in expected_references.items():
        document = documents.get(capability, {})
        fail_if(
            failures,
            (
                document.get("reference_artifact"),
                document.get("reference_run_id"),
            )
            != expected,
            f"SOP upstream reference drifted: {capability}",
        )


def validate_change_policy(
    failures: list[str],
    policy: dict[str, Any],
) -> None:
    fail_if(
        failures,
        policy.get("schema") != "pg36-ch24-change-policy-v1",
        "change policy schema drifted",
    )
    fail_if(
        failures,
        policy.get("production_approval") is not False
        or len(policy.get("lifecycle", [])) < 10,
        "change lifecycle or production boundary drifted",
    )
    classes = index_by(policy.get("risk_classes"), "id")
    fail_if(
        failures,
        set(classes) != {"L0", "L1", "L2", "L3"},
        "change risk classes drifted",
    )
    for class_id in ("L2", "L3"):
        value = classes.get(class_id, {})
        fail_if(
            failures,
            value.get("independent_approval") is not True
            or value.get("exact_target") is not True
            or value.get("rollback_required") is not True,
            f"high-risk class lost authority or recovery controls: {class_id}",
        )
    control = policy.get("high_risk_control", {})
    must_be_true = (
        "requester_approver_executor_distinct",
        "independent_approver_qualified",
        "exact_target_and_blast_radius_required",
        "machine_enforced_preconditions",
        "human_confirmation_binds_target_action_and_window",
        "cooldown_or_delayed_confirmation_for_destructive_action",
        "stop_conditions_evaluated_during_execution",
    )
    fail_if(
        failures,
        any(control.get(field) is not True for field in must_be_true)
        or control.get("requester_may_approve") is not False
        or control.get("approver_may_execute") is not False
        or control.get("shared_accounts_allowed") is not False
        or control.get("credential_material_in_ticket") is not False,
        "high-risk authority separation drifted",
    )
    break_glass = control.get("break_glass", {})
    fail_if(
        failures,
        break_glass.get("may_skip_normal_wait") is not True
        or break_glass.get("may_skip_target_and_evidence") is not False
        or break_glass.get("time_bounded_identity") is not True
        or break_glass.get("independent_after_action_review") is not True
        or break_glass.get("credential_rotation_after_use") is not True,
        "break-glass became unbounded or unreviewed",
    )
    required_fields = set(policy.get("change_record_required_fields", []))
    fail_if(
        failures,
        not {
            "exact_target",
            "blast_radius",
            "requester_identity",
            "approver_identity",
            "executor_identity",
            "stop_conditions",
            "verification",
            "rollback_or_roll_forward",
            "evidence_manifest",
        }.issubset(required_fields),
        "change record cannot prove authority, target, or outcome",
    )
    gate = policy.get("error_budget_gate", {})
    fail_if(
        failures,
        set(gate)
        != {
            "healthy",
            "watch",
            "constrained",
            "exhausted",
            "emergency_exception_still_requires_evidence",
        }
        or gate.get("emergency_exception_still_requires_evidence")
        is not True,
        "error budget is not connected to change policy",
    )


def validate_retention(
    failures: list[str],
    requirements: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    fail_if(
        failures,
        policy.get("schema")
        != "pg36-ch24-evidence-retention-v1",
        "evidence-retention schema drifted",
    )
    fail_if(
        failures,
        policy.get("production_approval") is not False,
        "teaching retention policy was promoted to production",
    )
    principles = policy.get("principles", {})
    fail_if(
        failures,
        principles.get("evidence_is_not_a_secret_store") is not True
        or principles.get("minimum_necessary_collection") is not True
        or principles.get("immutable_manifest") is not True
        or principles.get("hash_algorithm") != "sha256"
        or principles.get("access_is_role_based") is not True
        or principles.get("deletion_is_audited") is not True,
        "evidence integrity, minimization, or access principles drifted",
    )
    categories = index_by(policy.get("categories"), "id")
    required = set(requirements.get("required_evidence_categories", []))
    fail_if(
        failures,
        set(categories) != required,
        "evidence category set drifted",
    )
    for category_id, category in categories.items():
        fail_if(
            failures,
            not isinstance(category.get("retention_days"), int)
            or category.get("retention_days", 0) <= 0
            or not category.get("access_roles")
            or category.get("secret_values_permitted") is not False
            or category.get("integrity_manifest_required") is not True,
            f"evidence category is unprotected or permits secrets: {category_id}",
        )
    forbidden = set(
        policy.get("redaction", {}).get("forbidden_material", [])
    )
    fail_if(
        failures,
        not {
            "cleartext password",
            "SCRAM verifier",
            "private key",
            "session token",
            "raw connection URI with credentials",
        }.issubset(forbidden),
        "secret-bearing evidence is not explicitly forbidden",
    )
    fail_if(
        failures,
        len(policy.get("chain_of_custody", [])) < 6
        or len(policy.get("production_decisions_pending", [])) < 5,
        "chain of custody or pending production decisions are incomplete",
    )


def validate_upstream_references(
    failures: list[str],
    requirements: dict[str, Any],
    upstream_root: Path,
) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for chapter, specification in sorted(
        requirements.get("upstream_reference_contract", {}).items()
    ):
        path = upstream_root / str(specification.get("path", ""))
        try:
            value = read_json(path)
            gate = nested_get(
                value,
                str(specification.get("production_gate_field", "")),
            )
        except ValidationError as exc:
            failures.append(f"{chapter}: {exc}")
            continue
        observed[chapter] = {
            "path": specification.get("path"),
            "sha256": sha256(path),
            "schema": value.get("schema"),
            "run_id": value.get("run_id"),
            "production_gate": gate,
        }
        fail_if(
            failures,
            value.get("schema") != specification.get("schema"),
            f"{chapter}: upstream schema drifted",
        )
        fail_if(
            failures,
            value.get("run_id") != specification.get("run_id"),
            f"{chapter}: upstream run id drifted",
        )
        fail_if(
            failures,
            gate != specification.get("production_gate_value")
            or gate != "pending",
            f"{chapter}: upstream production gate was hidden or passed",
        )
        if "production_approval" in value:
            fail_if(
                failures,
                value.get("production_approval") is not False,
                f"{chapter}: sandbox evidence claims production approval",
            )
    return observed


def validate_evidence(
    failures: list[str],
    source_dir: Path,
    upstream_observed: dict[str, dict[str, Any]],
    evidence_path: Path | None,
) -> None:
    if evidence_path is None:
        return
    evidence = read_json(evidence_path)
    fail_if(
        failures,
        evidence.get("schema") != "pg36-ch24-governance-evidence-v1",
        "governance evidence schema drifted",
    )
    fail_if(
        failures,
        evidence.get("target") != "pg36-l2-vagrant/pg-test"
        or evidence.get("service_id") != "pg36_shop"
        or evidence.get("mutation") != "none"
        or evidence.get("production_approval") is not False
        or evidence.get("production_ch24_gate") != "pending",
        "governance evidence target, mutation, or production gate drifted",
    )
    ch19 = evidence.get("chapter_19_live_gate", {})
    fail_if(
        failures,
        ch19.get("status") != "ok"
        or ch19.get("sandbox_l2") != "accepted-with-exceptions"
        or ch19.get("production_ch19_gate") != "pending"
        or ch19.get("production_approval") is not False
        or ch19.get("mutation") != "none"
        or ch19.get("host_count") != 4
        or ch19.get("postgresql_members") != 4,
        "chapter-19 live gate did not remain read-only and pending",
    )
    source_hashes = evidence.get("source_sha256", {})
    for name in SOURCE_NAMES:
        path = source_dir / name
        fail_if(
            failures,
            not path.is_file()
            or source_hashes.get(name) != sha256(path),
            f"evidence source hash drifted: {name}",
        )
    evidence_upstream = evidence.get("upstream_references", {})
    fail_if(
        failures,
        set(evidence_upstream) != set(upstream_observed),
        "evidence upstream reference set drifted",
    )
    for chapter, observed in upstream_observed.items():
        fail_if(
            failures,
            evidence_upstream.get(chapter) != observed,
            f"evidence upstream hash or identity drifted: {chapter}",
        )


def validate_contracts(
    contracts: dict[str, dict[str, Any]],
    source_dir: Path,
    upstream_root: Path,
    evidence_path: Path | None = None,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    failures: list[str] = []
    requirements = contracts["requirements.json"]
    validate_requirements(failures, requirements)
    validate_service_card(
        failures,
        requirements,
        contracts["service-card.json"],
    )
    validate_slo_policy(
        failures,
        requirements,
        contracts["slo-policy.json"],
    )
    validate_observation_contract(
        failures,
        requirements,
        contracts["observation-contract.json"],
    )
    validate_alerts(
        failures,
        requirements,
        contracts["alert-candidates.json"],
    )
    validate_sops(
        failures,
        requirements,
        contracts["sop-catalog.json"],
    )
    validate_change_policy(
        failures,
        contracts["change-policy.json"],
    )
    validate_retention(
        failures,
        requirements,
        contracts["evidence-retention.json"],
    )
    upstream = validate_upstream_references(
        failures,
        requirements,
        upstream_root,
    )
    validate_evidence(
        failures,
        source_dir,
        upstream,
        evidence_path,
    )
    return failures, upstream


def mutate_path(
    value: Any,
    path: list[Any],
    operation: str,
    replacement: Any,
) -> None:
    if not path:
        raise ValidationError("negative mutation path is empty")
    current = value
    for part in path[:-1]:
        if isinstance(part, int):
            if not isinstance(current, list):
                raise ValidationError(
                    f"negative path expects list at {part!r}"
                )
            current = current[part]
        else:
            if not isinstance(current, dict):
                raise ValidationError(
                    f"negative path expects object at {part!r}"
                )
            current = current[part]
    final = path[-1]
    if operation == "set":
        current[final] = replacement
    elif operation == "delete":
        if isinstance(current, list) and isinstance(final, int):
            del current[final]
        elif isinstance(current, dict) and isinstance(final, str):
            del current[final]
        else:
            raise ValidationError("negative delete target type mismatched")
    else:
        raise ValidationError(
            f"unknown negative mutation operation: {operation}"
        )


def validate_negative_cases(
    contracts: dict[str, dict[str, Any]],
    source_dir: Path,
    upstream_root: Path,
    specification: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    cases = specification.get("cases", [])
    if specification.get("schema") != "pg36-ch24-negative-cases-v1":
        return ["negative-case schema drifted"], results
    if len(cases) != 20:
        failures.append("negative-case count drifted")
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        artifact = case.get("artifact")
        if not isinstance(case_id, str) or case_id in seen:
            failures.append(f"invalid or duplicate negative case id: {case_id}")
            continue
        seen.add(case_id)
        if artifact not in contracts:
            failures.append(f"{case_id}: unknown artifact {artifact}")
            continue
        mutated = copy.deepcopy(contracts)
        try:
            mutate_path(
                mutated[artifact],
                case.get("path", []),
                str(case.get("operation", "")),
                case.get("value"),
            )
            case_failures, _ = validate_contracts(
                mutated,
                source_dir,
                upstream_root,
            )
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            failures.append(f"{case_id}: mutation could not run: {exc}")
            continue
        rejected = bool(case_failures)
        results.append(
            {
                "id": case_id,
                "artifact": artifact,
                "mutation": case.get("mutation"),
                "rejected": rejected,
                "rejection_reasons": case_failures[:5],
            }
        )
        if not rejected:
            failures.append(
                f"{case_id}: adversarial mutation was incorrectly accepted"
            )
    return failures, results


def main() -> int:
    args = parse_args()
    try:
        contracts = load_contracts(args.source_dir)
        positive_failures, upstream = validate_contracts(
            contracts,
            args.source_dir,
            args.upstream_root,
            args.evidence,
        )
        if args.negative_cases is None:
            report = {
                "schema": "pg36-ch24-validation-report-v1",
                "status": "ok" if not positive_failures else "failed",
                "passed": not positive_failures,
                "failure_count": len(positive_failures),
                "failures": positive_failures,
                "artifact_count": len(ARTIFACT_NAMES),
                "objective_count": len(
                    contracts["slo-policy.json"].get("objectives", [])
                ),
                "accepted_alert_count": len(
                    contracts["alert-candidates.json"].get(
                        "accepted",
                        [],
                    )
                ),
                "sop_count": len(
                    contracts["sop-catalog.json"].get("documents", [])
                ),
                "upstream_references": upstream,
                "production_ch24_gate": "pending",
            }
        else:
            if positive_failures:
                raise ValidationError(
                    "baseline contracts fail before negative validation: "
                    + "; ".join(positive_failures[:5])
                )
            specification = read_json(args.negative_cases)
            negative_failures, results = validate_negative_cases(
                contracts,
                args.source_dir,
                args.upstream_root,
                specification,
            )
            report = {
                "schema": "pg36-ch24-negative-report-v1",
                "status": "ok" if not negative_failures else "failed",
                "passed": not negative_failures,
                "failure_count": len(negative_failures),
                "failures": negative_failures,
                "case_count": len(results),
                "rejected_count": sum(
                    1 for row in results if row["rejected"]
                ),
                "cases": results,
                "production_ch24_gate": "pending",
            }
        write_json(args.output, report)
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    if report["passed"]:
        print("status=validation-ok")
        print(f"schema={report['schema']}")
        if args.negative_cases is not None:
            print(
                f"counterexamples={report['rejected_count']}-rejected"
            )
        print("production_ch24_gate=pending")
        return 0
    for failure in report["failures"]:
        print(f"validation failure: {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
