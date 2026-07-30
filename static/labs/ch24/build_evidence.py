#!/usr/bin/env python3
"""Bind chapter 24 contracts to a current read-only chapter 19 gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate import SOURCE_NAMES, ValidationError, nested_get, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--ch19-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        ch19_validation_path = (
            args.ch19_evidence / "validation-report.json"
        )
        ch19_manifest_path = args.ch19_evidence / "capture-manifest.json"
        ch19_review_path = args.ch19_evidence / "review.txt"
        ch19_validation = read_json(ch19_validation_path)
        ch19_manifest = read_json(ch19_manifest_path)
        review_text = ch19_review_path.read_text(encoding="utf-8")
        decision = ch19_validation.get("decision", {})
        if (
            ch19_validation.get("status") != "ok"
            or decision.get("sandbox_l2")
            != "accepted-with-exceptions"
            or decision.get("production_ch19_gate") != "pending"
            or ch19_manifest.get("production_approval") is not False
            or "mutation=none" not in review_text
        ):
            raise ValidationError(
                "chapter-19 gate is not an accepted read-only sandbox result"
            )
        source_hashes: dict[str, str] = {}
        for name in SOURCE_NAMES:
            path = args.source_dir / name
            if not path.is_file():
                raise ValidationError(f"missing source artifact: {name}")
            source_hashes[name] = sha256(path)
        upstream: dict[str, dict[str, Any]] = {}
        for chapter, specification in sorted(
            requirements.get(
                "upstream_reference_contract",
                {},
            ).items()
        ):
            relative = str(specification.get("path", ""))
            path = args.upstream_root / relative
            value = read_json(path)
            gate = nested_get(
                value,
                str(specification.get("production_gate_field", "")),
            )
            upstream[chapter] = {
                "path": relative,
                "sha256": sha256(path),
                "schema": value.get("schema"),
                "run_id": value.get("run_id"),
                "production_gate": gate,
            }
        now = datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        report = {
            "schema": "pg36-ch24-governance-evidence-v1",
            "release": "1.0-sandbox",
            "run_id": str(uuid.uuid4()),
            "captured_at": now,
            "target": "pg36-l2-vagrant/pg-test",
            "service_id": "pg36_shop",
            "mode": "read-only-contract-and-live-baseline-binding",
            "mutation": "none",
            "production_approval": False,
            "chapter_19_live_gate": {
                "status": ch19_validation.get("status"),
                "sandbox_l2": decision.get("sandbox_l2"),
                "production_ch19_gate": decision.get(
                    "production_ch19_gate"
                ),
                "production_approval": ch19_manifest.get(
                    "production_approval"
                ),
                "mutation": "none",
                "captured_at": ch19_manifest.get("captured_at"),
                "pigsty_version": ch19_validation.get(
                    "facts",
                    {},
                ).get("pigsty_version"),
                "postgresql_major": ch19_validation.get(
                    "facts",
                    {},
                ).get("postgresql_major"),
                "host_count": ch19_validation.get(
                    "counts",
                    {},
                ).get("hosts"),
                "postgresql_members": ch19_validation.get(
                    "counts",
                    {},
                ).get("postgresql_members"),
                "accepted_exception_ids": ch19_validation.get(
                    "accepted_exception_ids",
                    [],
                ),
                "validation_sha256": sha256(ch19_validation_path),
                "manifest_sha256": sha256(ch19_manifest_path),
                "review_sha256": sha256(ch19_review_path),
            },
            "source_sha256": source_hashes,
            "upstream_references": upstream,
            "claims": {
                "governance_contract_machine_checkable": True,
                "current_sandbox_baseline_rechecked": True,
                "upstream_reference_identity_bound": True,
                "alert_rules_deployed": False,
                "real_pager_notified": False,
                "production_slo_measured": False,
                "production_ch24_approved": False,
            },
            "production_ch24_gate": "pending",
        }
        write_json(args.output, report)
    except (OSError, ValidationError) as exc:
        print(f"evidence build failed: {exc}", file=sys.stderr)
        return 1
    print("status=evidence-built")
    print(f"run_id={report['run_id']}")
    print("mutation=none")
    print("production_ch24_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
