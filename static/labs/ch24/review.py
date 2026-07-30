#!/usr/bin/env python3
"""Review a validated chapter 24 governance evidence bundle."""

from __future__ import annotations

import argparse
import re
import stat
import sys
from pathlib import Path
from typing import Any

from validate import ValidationError, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def require_private(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValidationError(
            f"evidence is group/world accessible: {path} ({mode:04o})"
        )


def scan_secret_material(root: Path) -> None:
    patterns = {
        "SCRAM verifier": re.compile(rb"SCRAM-SHA-256\$"),
        "private key": re.compile(
            rb"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----"
        ),
        "clear password JSON field": re.compile(
            rb'"password"\s*:\s*"(?!REDACTED|REPLACE_)',
            re.IGNORECASE,
        ),
        "credential-bearing URI": re.compile(
            rb"(?:postgres|postgresql)://[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
    }
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        require_private(path)
        data = path.read_bytes()
        for label, pattern in patterns.items():
            if pattern.search(data):
                raise ValidationError(
                    f"{label} found in evidence: {path}"
                )


def main() -> int:
    args = parse_args()
    try:
        positive = read_json(
            args.evidence_root / "validation-report.json"
        )
        negative = read_json(
            args.evidence_root / "negative-report.json"
        )
        evidence = read_json(
            args.evidence_root / "governance-evidence.json"
        )
        if (
            positive.get("passed") is not True
            or positive.get("failure_count") != 0
            or positive.get("artifact_count") != 8
            or positive.get("objective_count") != 5
            or positive.get("accepted_alert_count") != 7
            or positive.get("sop_count") != 4
        ):
            raise ValidationError("positive governance validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 20
            or negative.get("rejected_count") != 20
        ):
            raise ValidationError(
                "adversarial governance validation failed"
            )
        if (
            evidence.get("mutation") != "none"
            or evidence.get("production_approval") is not False
            or evidence.get("production_ch24_gate") != "pending"
        ):
            raise ValidationError(
                "evidence hid mutation or production boundary"
            )
        live = evidence.get("chapter_19_live_gate", {})
        if (
            live.get("status") != "ok"
            or live.get("sandbox_l2")
            != "accepted-with-exceptions"
            or live.get("production_ch19_gate") != "pending"
            or live.get("mutation") != "none"
        ):
            raise ValidationError(
                "chapter-19 live gate is not retained"
            )
        claims = evidence.get("claims", {})
        forbidden_true = (
            "alert_rules_deployed",
            "real_pager_notified",
            "production_slo_measured",
            "production_ch24_approved",
        )
        if any(claims.get(field) is not False for field in forbidden_true):
            raise ValidationError("sandbox evidence overclaims delivery")
        if set(evidence.get("upstream_references", {})) != {
            "ch20",
            "ch21",
            "ch22",
            "ch23",
        }:
            raise ValidationError("upstream reference set drifted")
        scan_secret_material(args.evidence_root)
        contract_text = (
            args.source_dir / "lab-contract.md"
        ).read_text(encoding="utf-8")
        for token in (
            "不会创建数据库对象",
            "production",
            "二十个对抗性变体",
            "PG36_CH19_INVENTORY",
        ):
            if token not in contract_text:
                raise ValidationError(
                    f"lab safety contract token missing: {token}"
                )
    except (OSError, ValidationError) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1
    print("status=review-ok")
    print(f"run_id={evidence['run_id']}")
    print("service_card=complete")
    print("objectives=3-ratio+2-control")
    print("accepted_alerts=7")
    print("actionless_alerts=1-rejected")
    print("sops=4")
    print("counterexamples=20-rejected")
    print("ch19_live_gate=accepted-with-exceptions")
    print("upstream_runs=4-bound-by-hash")
    print("mutation=none")
    print("production_ch24_gate=pending")
    print("secret_material=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
