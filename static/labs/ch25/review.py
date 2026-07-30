#!/usr/bin/env python3
"""Review a complete chapter 25 observability evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    """Raised when a completed evidence bundle is unsafe or incomplete."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def require_private(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ReviewError(
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
            rb"(?:postgres|postgresql|https?)://"
            rb"[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
        "authorization header": re.compile(
            rb"authorization\s*:\s*(?:basic|bearer)\s+\S+",
            re.IGNORECASE,
        ),
        "SQL text field": re.compile(
            rb'"(?:query|raw_sql|sql_text)"\s*:\s*"',
            re.IGNORECASE,
        ),
    }
    require_private(root)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        require_private(path)
        data = path.read_bytes()
        for label, pattern in patterns.items():
            if pattern.search(data):
                raise ReviewError(
                    f"{label} found in private evidence: {path}"
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
            args.evidence_root / "observability-evidence.json"
        )
        isolated = (
            args.evidence_root / "isolated-exercise.txt"
        ).read_text(encoding="utf-8")
        if (
            positive.get("passed") is not True
            or positive.get("failure_count") != 0
            or positive.get("accepted_alert_count") != 7
            or positive.get("proposed_alert_count") != 6
            or positive.get("alert_rule_count") != 13
            or positive.get("recording_rule_count") != 18
            or positive.get("route_test_count") != 8
            or positive.get("inhibition_test_count") != 5
            or positive.get("coverage_row_count") != 14
            or positive.get("live_evidence_checked") is not True
            or positive.get("isolated_exercise_checked") is not True
        ):
            raise ReviewError("positive observability validation failed")
        if (
            negative.get("passed") is not True
            or negative.get("case_count") != 25
            or negative.get("rejected_count") != 25
        ):
            raise ReviewError(
                "adversarial observability validation failed"
            )
        for token in (
            "vmalert_dry_run=ok",
            "vmalert_unit_tests=ok",
            "alertmanager_config=ok",
            "route_tests=8-ok",
            "inhibition_tests=5-ok",
            "real_receiver=false",
            "live_alertmanager_used=false",
            "remote_cleanup=ok",
        ):
            if token not in isolated:
                raise ReviewError(
                    f"isolated exercise token missing: {token}"
                )
        claims = evidence.get("claims", {})
        if (
            any(value is not False for value in claims.values())
            or evidence.get("mutation") != "none"
            or evidence.get("production_ch25_gate") != "pending"
            or evidence.get("production_approval") is not False
        ):
            raise ReviewError(
                "evidence overclaims mutation, deployment, or production"
            )
        live = evidence.get("live", {})
        postgres = live.get("postgresql", {})
        if (
            postgres.get("host_identity") != "pg-test-1"
            or postgres.get("identity", {}).get("cluster_name")
            != "pg-test"
            or len(postgres.get("replication", [])) != 2
            or live.get("application_metrics", {}).get("series") != 0
            or live.get("vmalert", {}).get("rule_error_count") != 0
        ):
            raise ReviewError(
                "live identity, replication, SLI gap, or rule state drifted"
            )
        contract_text = (
            args.source_dir / "lab-contract.md"
        ).read_text(encoding="utf-8")
        for token in (
            "规则测试通过",
            "不等于",
            "production_ch25_gate",
            "pg_stat_statements_reset",
            "/tmp/pg36-ch25.*",
        ):
            if token not in contract_text:
                raise ReviewError(
                    f"lab safety contract token missing: {token}"
                )
        scan_secret_material(args.evidence_root)
    except (OSError, ReviewError) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1

    versions = evidence["live"]["versions"]
    vmalert = evidence["live"]["vmalert"]
    postgres = evidence["live"]["postgresql"]
    archiver = postgres["archiver"]
    print("status=review-ok")
    print(f"run_id={evidence['run_id']}")
    print(
        "versions="
        f"pigsty-{versions['pigsty']},"
        f"postgresql-{versions['postgresql']},"
        f"vm-{versions['VictoriaMetrics']},"
        f"vmalert-{versions['VMAlert']},"
        f"pg_exporter-{versions['pg_exporter']}"
    )
    print(
        "live_vmalert="
        f"{vmalert['group_count']}-groups,"
        f"{vmalert['alert_rule_count']}-alerts,"
        f"{vmalert['recording_rule_count']}-records,"
        "0-errors"
    )
    print("chapter_rules=18-recording+13-alert-isolated-only")
    print("accepted_alerts=7")
    print("proposed_alerts=6-test-sink-only")
    print("route_tests=8-ok")
    print("inhibition_tests=5-ok")
    print("application_sli_metrics=absent-declared-gap")
    print("postgresql_target=pg-test-1/pg-test/primary")
    print("replication_streams=2")
    print(
        "pg_stat_statements="
        f"{postgres['pg_stat_statements']['aggregate']['statement_rows']}"
        "-rows-no-query-text"
    )
    print(
        "archiver_baseline="
        f"failed_count-{archiver['failed_count']},"
        "last-success-retained"
    )
    print("counterexamples=25-rejected")
    print("real_receiver=false")
    print("live_deployment=false")
    print("mutation=live-none,isolated-ephemeral-cleaned")
    print("production_ch25_gate=pending")
    print("secret_material=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
