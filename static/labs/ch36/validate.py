#!/usr/bin/env python3
"""Validate a chapter 36 closure bundle and reject semantic mutants."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Callable

from common import (
    ContractError,
    json_pointer,
    load_json,
    phase_for_due_day,
    require,
    sha256_file,
    write_json,
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OWNER_ROLE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    require(value.get("schema") == expected, f"{label} schema mismatch")


def validate_report(
    report: dict[str, Any],
    source_dir: Path,
    requirements: dict[str, Any],
    catalog: dict[str, Any],
    backlog: dict[str, Any],
    capability_contract: dict[str, Any],
) -> None:
    acceptance = requirements["acceptance"]
    require_schema(report, "pg36-ch36-closure-report-v1", "closure report")
    require(report.get("input_kind") == "frozen-public-evidence", "input kind changed")

    incidents = report.get("incidents")
    require(isinstance(incidents, list), "incidents must be a list")
    require(len(incidents) == acceptance["incident_count"], "incident count mismatch")
    chapters = [item.get("chapter") for item in incidents]
    require(
        sorted(chapters) == acceptance["required_chapters"],
        "incident chapters are missing or duplicated",
    )
    incident_by_id = {item.get("id"): item for item in incidents}
    require(len(incident_by_id) == len(incidents), "incident IDs must be unique")

    for spec in catalog["incidents"]:
        incident = incident_by_id.get(spec["id"])
        require(incident is not None, f"missing incident {spec['id']}")
        source_path = (source_dir / spec["source"]).resolve()
        source = load_json(source_path)
        require(
            incident.get("source_schema") == spec["source_schema"],
            f"{spec['id']} compiled schema changed",
        )
        require(
            incident.get("source_sha256") == sha256_file(source_path),
            f"{spec['id']} input hash mismatch",
        )
        require(
            incident.get("exercise_scope") == spec["exercise_scope"],
            f"{spec['id']} scope changed",
        )
        impact = incident.get("impact", {})
        require(
            impact.get("kind") in {"simulated", "observed-sandbox"},
            f"{spec['id']} impact overclaims production",
        )
        require(
            impact == spec["impact"],
            f"{spec['id']} impact statement or evidence binding changed",
        )
        require(
            isinstance(incident.get("claims_not_made"), list)
            and len(incident["claims_not_made"]) >= 3,
            f"{spec['id']} needs explicit claim boundaries",
        )
        require(
            incident["claims_not_made"] == spec["claims_not_made"],
            f"{spec['id']} claim boundaries changed",
        )
        timeline = incident.get("timeline")
        require(
            isinstance(timeline, list) and len(timeline) >= 4,
            f"{spec['id']} timeline is incomplete",
        )
        require(
            [event.get("sequence") for event in timeline] == list(range(1, len(timeline) + 1)),
            f"{spec['id']} timeline sequence is invalid",
        )
        require(timeline == spec["timeline"], f"{spec['id']} timeline changed")

        fact_by_id = {fact.get("id"): fact for fact in incident.get("facts", [])}
        require(
            len(fact_by_id) == len(spec["facts"]),
            f"{spec['id']} fact count or IDs changed",
        )
        for fact_spec in spec["facts"]:
            fact = fact_by_id.get(fact_spec["id"])
            require(fact is not None, f"{spec['id']} missing fact {fact_spec['id']}")
            actual_source_value = json_pointer(source, fact_spec["source_pointer"])
            require(
                fact.get("source_pointer") == fact_spec["source_pointer"],
                f"{fact_spec['id']} source pointer changed",
            )
            require(
                fact.get("expected") == fact_spec["expected"]
                and fact.get("actual") == actual_source_value
                and fact.get("matches_source") is True,
                f"{fact_spec['id']} no longer matches source evidence",
            )
            require(
                fact.get("knowledge_stage")
                in {"before-action", "during-response", "after-validation"},
                f"{fact_spec['id']} has invalid knowledge stage",
            )
            require(
                fact.get("knowledge_stage") == fact_spec["knowledge_stage"],
                f"{fact_spec['id']} knowledge stage was rewritten",
            )
        basis_ids = incident.get("decision", {}).get("basis_fact_ids", [])
        require(
            basis_ids and set(basis_ids).issubset(fact_by_id),
            f"{spec['id']} decision lacks valid fact basis",
        )

    themes = report.get("cross_incident_themes")
    require(isinstance(themes, list), "cross-incident themes must be a list")
    require(
        len(themes) >= acceptance["minimum_cross_incident_themes"],
        "too few cross-incident themes",
    )
    theme_by_id = {item.get("id"): item for item in themes}
    require(len(theme_by_id) == len(themes), "theme IDs must be unique")
    catalog_theme_by_id = {item["id"]: item for item in catalog["cross_incident_themes"]}
    require(set(theme_by_id) == set(catalog_theme_by_id), "theme set changed")
    for theme_id, expected_theme in catalog_theme_by_id.items():
        theme = theme_by_id[theme_id]
        require(theme == expected_theme, f"theme {theme_id} changed")
        require(
            theme.get("status") == "production-assessment-required",
            f"theme {theme_id} overclaims a confirmed production gap",
        )
        members = theme.get("incident_ids", [])
        require(
            len(members) >= acceptance["minimum_incidents_per_theme"],
            f"theme {theme_id} is not cross-incident",
        )
        require(
            set(members).issubset(incident_by_id),
            f"theme {theme_id} references unknown incident",
        )
        for incident_id in members:
            require(
                theme_id in incident_by_id[incident_id]["control_theme_ids"],
                f"theme {theme_id} membership is inconsistent for {incident_id}",
            )

    actions = report.get("actions")
    require(isinstance(actions, list), "actions must be a list")
    require(len(actions) >= acceptance["minimum_actions"], "too few control actions")
    action_by_id = {item.get("id"): item for item in actions}
    require(len(action_by_id) == len(actions), "action IDs must be unique")
    require(
        set(action_by_id) == {item["id"] for item in backlog["actions"]},
        "action set changed",
    )
    forbidden = [phrase.casefold() for phrase in acceptance["forbidden_action_phrases"]]
    control_types: set[str] = set()
    covered_themes: set[str] = set()
    for action in actions:
        action_id = action.get("id", "<unknown>")
        for field in acceptance["required_action_fields"]:
            require(field in action, f"{action_id} missing action field {field}")
        require(
            OWNER_ROLE_RE.fullmatch(str(action.get("owner_role", ""))) is not None,
            f"{action_id} owner must be a stable role, not a person",
        )
        require(action.get("priority") in {"P0", "P1"}, f"{action_id} priority invalid")
        due_day = action.get("due_day")
        require(
            isinstance(due_day, int)
            and phase_for_due_day(due_day) == action.get("phase"),
            f"{action_id} due day and phase mismatch",
        )
        require(action.get("status") == "proposed", f"{action_id} was closed without evidence")
        require(
            action.get("production_execution_approved") is False,
            f"{action_id} auto-approved production execution",
        )
        text = json.dumps(action, ensure_ascii=False).casefold()
        require(
            all(phrase not in text for phrase in forbidden),
            f"{action_id} contains a forbidden vague action phrase",
        )
        themes_for_action = action.get("source_themes", [])
        require(
            themes_for_action
            and set(themes_for_action).issubset(theme_by_id),
            f"{action_id} references an unknown or empty theme",
        )
        covered_themes.update(themes_for_action)
        control_type = action.get("control_type")
        require(
            control_type in acceptance["required_control_types"],
            f"{action_id} control type invalid",
        )
        control_types.add(control_type)
        verification = action.get("verification")
        require(isinstance(verification, dict), f"{action_id} verification missing")
        for field in acceptance["required_verification_fields"]:
            require(field in verification, f"{action_id} verification missing {field}")
        require(
            len(str(verification.get("procedure", ""))) >= 24
            and str(verification.get("procedure", "")).casefold() != "review it",
            f"{action_id} verification procedure is not executable",
        )
        require(
            len(str(verification.get("pass_condition", ""))) >= 24
            and str(verification.get("pass_condition", "")).casefold() != "looks good",
            f"{action_id} pass condition is not measurable",
        )
        require(
            len(str(verification.get("evidence_to_close", ""))) >= 16,
            f"{action_id} closure evidence is missing",
        )
        require(
            isinstance(verification.get("revalidation_days"), int)
            and verification["revalidation_days"] > 0,
            f"{action_id} revalidation interval is invalid",
        )
        require(
            len(str(action.get("failure_condition", ""))) >= 24,
            f"{action_id} failure condition is missing",
        )
    require(
        control_types == set(acceptance["required_control_types"]),
        "prevent, detect, mitigate and recover controls are all required",
    )
    require(set(theme_by_id).issubset(covered_themes), "some themes have no action")

    roadmap = report.get("roadmap")
    require(isinstance(roadmap, list), "roadmap must be a list")
    roadmap_by_phase = {item.get("phase"): item for item in roadmap}
    require(
        set(roadmap_by_phase) == set(acceptance["roadmap_phases"]),
        "roadmap phases changed",
    )
    for phase in acceptance["roadmap_phases"]:
        entry = roadmap_by_phase[phase]
        expected_ids = [item["id"] for item in actions if item["phase"] == phase]
        require(entry.get("action_ids") == expected_ids, f"{phase} action order changed")
        require(
            entry.get("action_count") == len(expected_ids),
            f"{phase} action count mismatch",
        )
        require(expected_ids, f"{phase} has no actions")

    capability = report.get("capability")
    require(isinstance(capability, dict), "capability map missing")
    require(
        capability.get("assessment_policy", {}).get("status")
        == acceptance["learner_assessment_status"],
        "capability policy auto-certified the learner",
    )
    domains = capability.get("domains", [])
    require(domains == capability_contract["domains"], "capability domains changed")
    all_chapters = [chapter for domain in domains for chapter in domain.get("chapters", [])]
    expected_chapters = list(
        range(
            acceptance["capability_chapter_min"],
            acceptance["capability_chapter_max"] + 1,
        )
    )
    require(
        sorted(all_chapters) == expected_chapters and len(all_chapters) == len(set(all_chapters)),
        "capability map must cover chapters 1..36 exactly once",
    )
    learner = report.get("learner_assessment", {})
    require(
        learner.get("status") == "not-assessed"
        and learner.get("automatic_certification") is False
        and learner.get("assessment_required") is True,
        "learner was auto-certified",
    )

    manifests = report.get("manifests", {})
    input_manifest = manifests.get("inputs")
    source_manifest = manifests.get("sources")
    require(
        isinstance(input_manifest, list)
        and len(input_manifest) == acceptance["incident_count"],
        "input manifest is incomplete",
    )
    for entry in input_manifest:
        incident = next(item for item in incidents if item["chapter"] == entry.get("chapter"))
        source_path = (source_dir / incident["source"]).resolve()
        require(
            SHA256_RE.fullmatch(str(entry.get("sha256", ""))) is not None
            and entry["sha256"] == sha256_file(source_path)
            and entry.get("schema") == incident["source_schema"],
            f"input manifest mismatch for chapter {entry.get('chapter')}",
        )
    declared_sources = requirements["source_manifest"]["files"]
    require(
        isinstance(source_manifest, list)
        and [item.get("path") for item in source_manifest] == declared_sources,
        "source manifest is missing or reordered",
    )
    for entry in source_manifest:
        path = source_dir / entry["path"]
        require(
            SHA256_RE.fullmatch(str(entry.get("sha256", ""))) is not None
            and entry["sha256"] == sha256_file(path)
            and entry.get("bytes") == path.stat().st_size,
            f"source manifest mismatch for {entry['path']}",
        )

    require(
        report.get("decision")
        == {
            "production_approval": None,
            "production_ch36_gate": acceptance["production_ch36_gate"],
            "roadmap_status": "reference-proposal-requires-local-approval",
        },
        "production decision boundary changed",
    )
    require(
        report.get("safety")
        == {
            "database_connections": 0,
            "ssh_connections": 0,
            "external_dispatch_count": 0,
            "production_mutations": 0,
            "source_evidence_overwritten": False,
            "backlog_actions_executed": 0,
            "personal_data_exported": False,
            "secret_values_exported": 0,
        },
        "offline safety boundary changed",
    )


def mutate(report: dict[str, Any], mutation: str) -> None:
    incidents = report["incidents"]
    themes = report["cross_incident_themes"]
    actions = report["actions"]
    roadmap = report["roadmap"]
    operations: dict[str, Callable[[], None]] = {
        "drop-one-incident": lambda: incidents.pop(),
        "duplicate-incident-chapter": lambda: incidents[-1].__setitem__("chapter", 32),
        "corrupt-input-hash": lambda: incidents[0].__setitem__("source_sha256", "0" * 64),
        "corrupt-input-schema": lambda: incidents[0].__setitem__("source_schema", "wrong"),
        "change-observed-fact": lambda: incidents[0]["facts"][0].__setitem__("actual", -1),
        "break-source-pointer": lambda: incidents[0]["facts"][0].__setitem__(
            "source_pointer", "/missing"
        ),
        "claim-production-impact": lambda: incidents[0]["impact"].__setitem__(
            "kind", "production"
        ),
        "claim-real-users": lambda: incidents[1]["impact"].__setitem__("kind", "real-users"),
        "approve-source-production-gate": lambda: next(
            fact for fact in incidents[0]["facts"] if fact["id"] == "F32-GATE"
        ).__setitem__("actual", "approved"),
        "remove-claim-boundary": lambda: incidents[0].__setitem__("claims_not_made", []),
        "remove-timeline": lambda: incidents[0].__setitem__("timeline", []),
        "invalid-knowledge-stage": lambda: incidents[0]["facts"][0].__setitem__(
            "knowledge_stage", "always-known"
        ),
        "drop-cross-incident-theme": lambda: themes.pop(),
        "make-theme-single-incident": lambda: themes[0].__setitem__(
            "incident_ids", themes[0]["incident_ids"][:1]
        ),
        "reference-unknown-incident": lambda: themes[0]["incident_ids"].append("INC-UNKNOWN"),
        "drop-action": lambda: actions.pop(),
        "remove-owner-role": lambda: actions[0].pop("owner_role"),
        "replace-role-with-person": lambda: actions[0].__setitem__("owner_role", "Alice Smith"),
        "move-due-day-past-90": lambda: actions[0].__setitem__("due_day", 91),
        "mismatch-phase-and-due-day": lambda: actions[0].__setitem__("phase", "day-61-90"),
        "remove-verification": lambda: actions[0].pop("verification"),
        "use-vague-procedure": lambda: actions[0]["verification"].__setitem__(
            "procedure", "review it"
        ),
        "use-vague-pass-condition": lambda: actions[0]["verification"].__setitem__(
            "pass_condition", "looks good"
        ),
        "remove-failure-condition": lambda: actions[0].__setitem__("failure_condition", ""),
        "remove-closure-evidence": lambda: actions[0]["verification"].pop(
            "evidence_to_close"
        ),
        "disable-revalidation": lambda: actions[0]["verification"].__setitem__(
            "revalidation_days", 0
        ),
        "action-references-unknown-theme": lambda: actions[0].__setitem__(
            "source_themes", ["T36-UNKNOWN"]
        ),
        "remove-detect-control-type": lambda: [
            action.__setitem__("control_type", "prevent")
            for action in actions
            if action["control_type"] == "detect"
        ],
        "mark-proposed-action-closed": lambda: actions[0].__setitem__("status", "closed"),
        "auto-approve-production-action": lambda: actions[0].__setitem__(
            "production_execution_approved", True
        ),
        "drop-source-manifest": lambda: report["manifests"].__setitem__("sources", []),
        "malform-source-hash": lambda: report["manifests"]["sources"][0].__setitem__(
            "sha256", "bad"
        ),
        "drop-roadmap-phase": lambda: roadmap.pop(),
        "change-roadmap-count": lambda: roadmap[0].__setitem__(
            "action_count", roadmap[0]["action_count"] + 1
        ),
        "duplicate-capability-chapter": lambda: report["capability"]["domains"][1][
            "chapters"
        ].append(1),
        "auto-certify-learner": lambda: report["learner_assessment"].update(
            {"status": "passed", "automatic_certification": True}
        ),
    }
    require(mutation in operations, f"unknown negative mutation: {mutation}")
    operations[mutation]()


def validate_negative_cases(
    report: dict[str, Any],
    source_dir: Path,
    requirements: dict[str, Any],
    catalog: dict[str, Any],
    backlog: dict[str, Any],
    capability: dict[str, Any],
    negative: dict[str, Any],
) -> list[dict[str, Any]]:
    require_schema(negative, "pg36-ch36-negative-cases-v1", "negative cases")
    cases = negative.get("cases", [])
    require(len(cases) == 36, "exactly 36 negative cases are required")
    require(len({case.get("id") for case in cases}) == 36, "negative IDs must be unique")
    results = []
    for case in cases:
        require(case.get("must_reject") is True, f"{case.get('id')} must reject")
        candidate = copy.deepcopy(report)
        mutate(candidate, case["mutation"])
        rejected = False
        reason = ""
        try:
            validate_report(
                candidate, source_dir, requirements, catalog, backlog, capability
            )
        except (ContractError, KeyError, StopIteration, TypeError, ValueError) as exc:
            rejected = True
            reason = str(exc)
        require(rejected, f"{case['id']} was not rejected")
        results.append(
            {
                "id": case["id"],
                "mutation": case["mutation"],
                "rejected": True,
                "reason": reason,
            }
        )
    return results


def public_summary(
    report: dict[str, Any], negative_results: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema": "pg36-ch36-public-summary-v1",
        "status": "completed",
        "run_id": report["run_id"],
        "generated_at": report["generated_at"],
        "input": {
            "chapters": [item["chapter"] for item in report["incidents"]],
            "kind": report["input_kind"],
            "incident_count": len(report["incidents"]),
        },
        "portfolio": {
            "cross_incident_themes": len(report["cross_incident_themes"]),
            "proposed_actions": len(report["actions"]),
            "roadmap_phases": [item["phase"] for item in report["roadmap"]],
            "production_gaps_confirmed": 0,
        },
        "evidence": {
            "declared_counterexamples": len(negative_results),
            "live_mutants_rejected": sum(
                1 for item in negative_results if item["rejected"]
            ),
            "input_evidence_files_hash_bound": len(report["manifests"]["inputs"]),
            "source_files_hash_bound": len(report["manifests"]["sources"]),
            "capability_chapters_covered": 36,
        },
        "decision": report["decision"],
        "learner_assessment": report["learner_assessment"],
        "safety": report["safety"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--negative-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    bundle_dir = args.bundle_dir.resolve()
    report = load_json(bundle_dir / "closure-report.json")
    portfolio = load_json(bundle_dir / "postmortem-portfolio.json")
    roadmap_artifact = load_json(bundle_dir / "roadmap-90d.json")
    capability_artifact = load_json(bundle_dir / "capability-assessment.json")
    input_manifest_artifact = load_json(bundle_dir / "input-manifest.json")
    source_manifest_artifact = load_json(bundle_dir / "source-manifest.json")
    requirements = load_json(source_dir / "requirements.json")
    catalog = load_json(source_dir / "incident-catalog.json")
    backlog = load_json(source_dir / "control-backlog.json")
    capability = load_json(source_dir / "capability-map.json")
    negative = load_json(args.negative_cases)
    try:
        require_schema(
            portfolio, "pg36-ch36-postmortem-portfolio-v1", "postmortem portfolio"
        )
        require_schema(roadmap_artifact, "pg36-ch36-roadmap-v1", "roadmap artifact")
        require_schema(
            capability_artifact,
            "pg36-ch36-capability-assessment-v1",
            "capability artifact",
        )
        require_schema(
            input_manifest_artifact,
            "pg36-ch36-input-manifest-v1",
            "input manifest artifact",
        )
        require_schema(
            source_manifest_artifact,
            "pg36-ch36-source-manifest-v1",
            "source manifest artifact",
        )
        artifact_run_ids = {
            portfolio.get("run_id"),
            roadmap_artifact.get("run_id"),
            capability_artifact.get("run_id"),
            input_manifest_artifact.get("run_id"),
            source_manifest_artifact.get("run_id"),
        }
        require(
            artifact_run_ids == {report.get("run_id")},
            "bundle artifacts do not share one run ID",
        )
        require(
            portfolio.get("incidents") == report.get("incidents")
            and portfolio.get("cross_incident_themes")
            == report.get("cross_incident_themes"),
            "postmortem portfolio differs from closure report",
        )
        require(
            roadmap_artifact.get("actions") == report.get("actions")
            and roadmap_artifact.get("roadmap") == report.get("roadmap"),
            "roadmap artifact differs from closure report",
        )
        require(
            capability_artifact.get("assessment_policy")
            == report.get("capability", {}).get("assessment_policy")
            and capability_artifact.get("domains")
            == report.get("capability", {}).get("domains"),
            "capability artifact differs from closure report",
        )
        require(
            input_manifest_artifact.get("files")
            == report.get("manifests", {}).get("inputs")
            and source_manifest_artifact.get("files")
            == report.get("manifests", {}).get("sources"),
            "standalone manifests differ from closure report",
        )
        validate_report(report, source_dir, requirements, catalog, backlog, capability)
        negative_results = validate_negative_cases(
            report,
            source_dir,
            requirements,
            catalog,
            backlog,
            capability,
            negative,
        )
    except ContractError as exc:
        parser.error(str(exc))

    result = {
        "schema": "pg36-ch36-validation-report-v1",
        "status": "passed",
        "run_id": report["run_id"],
        "incidents_validated": len(report["incidents"]),
        "themes_validated": len(report["cross_incident_themes"]),
        "actions_validated": len(report["actions"]),
        "live_mutants_rejected": len(negative_results),
        "production_ch36_gate": "pending",
        "learner_assessment": "not-assessed",
    }
    write_json(args.output, result)
    write_json(
        args.negative_output,
        {
            "schema": "pg36-ch36-negative-report-v1",
            "status": "passed",
            "run_id": report["run_id"],
            "results": negative_results,
        },
    )
    write_json(args.public_summary, public_summary(report, negative_results))
    print("status=verify-ok")
    print(f"incidents={len(report['incidents'])}")
    print(f"actions={len(report['actions'])}")
    print(f"counterexamples={len(negative_results)}-rejected")
    print("production_ch36_gate=pending")
    print("learner_assessment=not-assessed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
