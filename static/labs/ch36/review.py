#!/usr/bin/env python3
"""Render a concise machine-checkable review of a chapter 36 bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ContractError, load_json, require


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    bundle = args.bundle_dir.resolve()
    report = load_json(bundle / "closure-report.json")
    validation = load_json(bundle / "validation-report.json")
    negative = load_json(bundle / "negative-report.json")
    public = load_json(bundle / "public-summary.json")
    try:
        require(validation.get("status") == "passed", "validation did not pass")
        require(negative.get("status") == "passed", "negative validation did not pass")
        require(
            validation.get("run_id") == report.get("run_id") == public.get("run_id"),
            "run IDs do not match",
        )
        require(
            validation.get("live_mutants_rejected") == 36,
            "all 36 live mutants must be rejected",
        )
        require(
            public.get("decision", {}).get("production_ch36_gate") == "pending",
            "production gate must remain pending",
        )
        require(
            public.get("learner_assessment", {}).get("status") == "not-assessed",
            "the lab cannot auto-certify a learner",
        )
    except ContractError as exc:
        parser.error(str(exc))

    summary = {
        "status": "review-ok",
        "run_id": report["run_id"],
        "incident_chapters": [item["chapter"] for item in report["incidents"]],
        "cross_incident_themes": len(report["cross_incident_themes"]),
        "proposed_actions": len(report["actions"]),
        "roadmap_phases": [item["phase"] for item in report["roadmap"]],
        "live_mutants_rejected": validation["live_mutants_rejected"],
        "input_evidence_files_hash_bound": len(report["manifests"]["inputs"]),
        "source_files_hash_bound": len(report["manifests"]["sources"]),
        "database_connections": report["safety"]["database_connections"],
        "external_dispatch_count": report["safety"]["external_dispatch_count"],
        "production_ch36_gate": report["decision"]["production_ch36_gate"],
        "learner_assessment": report["learner_assessment"]["status"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
