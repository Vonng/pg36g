#!/usr/bin/env python3
"""Compile chapters 32-35 public evidence into a chapter 36 closure bundle."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Any

from common import (
    ContractError,
    json_pointer,
    load_json,
    phase_for_due_day,
    require,
    sha256_file,
    utc_now,
    write_json,
)


def load_contracts(source_dir: Path) -> tuple[dict[str, Any], ...]:
    requirements = load_json(source_dir / "requirements.json")
    catalog = load_json(source_dir / "incident-catalog.json")
    backlog = load_json(source_dir / "control-backlog.json")
    capability = load_json(source_dir / "capability-map.json")
    require(
        requirements.get("schema") == "pg36-ch36-closure-requirements-v1",
        "unexpected requirements schema",
    )
    require(
        catalog.get("schema") == "pg36-ch36-incident-catalog-v1",
        "unexpected incident catalog schema",
    )
    require(
        backlog.get("schema") == "pg36-ch36-control-backlog-v1",
        "unexpected backlog schema",
    )
    require(
        capability.get("schema") == "pg36-ch36-capability-map-v1",
        "unexpected capability map schema",
    )
    return requirements, catalog, backlog, capability


def compile_incidents(
    source_dir: Path, catalog: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    compiled: list[dict[str, Any]] = []
    input_manifest: list[dict[str, Any]] = []
    for spec in catalog["incidents"]:
        source_path = (source_dir / spec["source"]).resolve()
        require(source_path.is_file(), f"incident source does not exist: {source_path}")
        source = load_json(source_path)
        require(
            source.get("schema") == spec["source_schema"],
            f"{spec['id']} source schema mismatch",
        )
        facts = []
        for fact_spec in spec["facts"]:
            actual = json_pointer(source, fact_spec["source_pointer"])
            require(
                actual == fact_spec["expected"],
                f"{spec['id']} fact {fact_spec['id']} drifted: "
                f"expected {fact_spec['expected']!r}, got {actual!r}",
            )
            facts.append({**fact_spec, "actual": actual, "matches_source": True})

        compiled.append(
            {
                "id": spec["id"],
                "chapter": spec["chapter"],
                "source": spec["source"],
                "source_schema": spec["source_schema"],
                "source_sha256": sha256_file(source_path),
                "exercise_scope": spec["exercise_scope"],
                "impact": spec["impact"],
                "facts": facts,
                "decision": spec["decision"],
                "timeline": spec["timeline"],
                "control_theme_ids": spec["control_theme_ids"],
                "claims_not_made": spec["claims_not_made"],
            }
        )
        input_manifest.append(
            {
                "chapter": spec["chapter"],
                "incident_id": spec["id"],
                "path": spec["source"],
                "schema": spec["source_schema"],
                "sha256": sha256_file(source_path),
            }
        )
    return compiled, input_manifest


def compile_source_manifest(
    source_dir: Path, requirements: dict[str, Any]
) -> list[dict[str, Any]]:
    manifest = []
    for name in requirements["source_manifest"]["files"]:
        path = source_dir / name
        require(path.is_file(), f"declared source file does not exist: {name}")
        manifest.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return manifest


def compile_roadmap(
    actions: list[dict[str, Any]], phases: list[str]
) -> list[dict[str, Any]]:
    roadmap = []
    for phase in phases:
        phase_actions = [item["id"] for item in actions if item["phase"] == phase]
        roadmap.append(
            {
                "phase": phase,
                "action_ids": phase_actions,
                "action_count": len(phase_actions),
                "latest_due_day": max(
                    item["due_day"] for item in actions if item["phase"] == phase
                ),
            }
        )
    return roadmap


def compile_bundle(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    requirements, catalog, backlog, capability = load_contracts(source_dir)
    incidents, input_manifest = compile_incidents(source_dir, catalog)
    source_manifest = compile_source_manifest(source_dir, requirements)
    actions = backlog["actions"]
    for action in actions:
        require(
            phase_for_due_day(action["due_day"]) == action["phase"],
            f"{action['id']} phase does not match due day",
        )
    phases = requirements["acceptance"]["roadmap_phases"]
    roadmap = compile_roadmap(actions, phases)
    run_id = str(uuid.uuid4())
    generated_at = utc_now()

    report: dict[str, Any] = {
        "schema": "pg36-ch36-closure-report-v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "input_kind": requirements["input"]["kind"],
        "incidents": incidents,
        "cross_incident_themes": catalog["cross_incident_themes"],
        "actions": actions,
        "roadmap": roadmap,
        "capability": capability,
        "manifests": {
            "inputs": input_manifest,
            "sources": source_manifest,
        },
        "evidence": {
            "incident_count": len(incidents),
            "cross_incident_theme_count": len(catalog["cross_incident_themes"]),
            "action_count": len(actions),
            "declared_counterexamples": len(
                load_json(source_dir / "negative-cases.json")["cases"]
            ),
            "input_evidence_files_hash_bound": len(input_manifest),
            "source_files_hash_bound": len(source_manifest),
        },
        "decision": {
            "production_approval": None,
            "production_ch36_gate": "pending",
            "roadmap_status": "reference-proposal-requires-local-approval",
        },
        "learner_assessment": {
            "status": capability["assessment_policy"]["status"],
            "automatic_certification": False,
            "assessment_required": True,
        },
        "safety": {
            "database_connections": 0,
            "ssh_connections": 0,
            "external_dispatch_count": 0,
            "production_mutations": 0,
            "source_evidence_overwritten": False,
            "backlog_actions_executed": 0,
            "personal_data_exported": False,
            "secret_values_exported": 0,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "closure-report.json", report)
    write_json(
        output_dir / "postmortem-portfolio.json",
        {
            "schema": "pg36-ch36-postmortem-portfolio-v1",
            "run_id": run_id,
            "incidents": incidents,
            "cross_incident_themes": catalog["cross_incident_themes"],
        },
    )
    write_json(
        output_dir / "roadmap-90d.json",
        {
            "schema": "pg36-ch36-roadmap-v1",
            "run_id": run_id,
            "policy": backlog["policy"],
            "roadmap": roadmap,
            "actions": actions,
        },
    )
    write_json(
        output_dir / "capability-assessment.json",
        {
            "schema": "pg36-ch36-capability-assessment-v1",
            "run_id": run_id,
            "assessment_policy": capability["assessment_policy"],
            "domains": capability["domains"],
        },
    )
    write_json(
        output_dir / "input-manifest.json",
        {
            "schema": "pg36-ch36-input-manifest-v1",
            "run_id": run_id,
            "files": input_manifest,
        },
    )
    write_json(
        output_dir / "source-manifest.json",
        {
            "schema": "pg36-ch36-source-manifest-v1",
            "run_id": run_id,
            "files": source_manifest,
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    try:
        report = compile_bundle(source_dir, output_dir)
    except ContractError as exc:
        parser.error(str(exc))
    print(f"status=compile-ok")
    print(f"run_id={report['run_id']}")
    print(f"incidents={report['evidence']['incident_count']}")
    print(f"actions={report['evidence']['action_count']}")
    print(f"evidence={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
