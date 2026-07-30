#!/usr/bin/env python3
"""Review a complete chapter 21 isolated-recovery evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


OUTCOME_FILES = {"restore-run.json", "migration-effort.json"}
EXPECTED_NEGATIVE_CODES = {
    "claim-production-from-sandbox": "E_PRODUCTION_CLAIM",
    "restore-to-unreviewed-target": "E_TARGET",
    "accept-failed-repository": "E_REPOSITORY",
    "accept-failed-backup": "E_BACKUP",
    "accept-missing-target-wal": "E_ARCHIVE",
    "restore-with-archive-push-enabled": "E_ISOLATION",
    "restore-on-a-tcp-listener": "E_ISOLATION",
    "accept-read-only-before-promotion": "E_PROMOTION",
    "lose-the-keep-marker": "E_BOUNDARY",
    "replay-the-discard-marker": "E_BOUNDARY",
    "accept-foreign-system-identifier": "E_LINEAGE",
    "accept-no-new-timeline": "E_TIMELINE",
    "leave-isolated-postmaster-running": "E_SHUTDOWN",
    "degrade-the-source-cluster": "E_SOURCE_HEALTH",
}
FORBIDDEN_TEXT = (
    "repo1-s3-key-secret=",
    "repo1-cipher-pass=",
    "password=",
    "minio_secret_key:",
    "pg_admin_password:",
)


class ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_inputs(source: Path) -> dict[str, str]:
    return {
        path.name: sha256(path)
        for path in sorted(source.iterdir())
        if path.is_file() and path.name not in OUTCOME_FILES
    }


def review_source_identity(
    drill: Path,
    source: Path,
    requirements: dict[str, Any],
    scenarios: dict[str, Any],
) -> None:
    manifest = read_json(drill / "drill-manifest.json")
    require(
        manifest.get("schema") == "pg36-ch21-drill-manifest-v1"
        and manifest.get("release") == requirements["release"]
        and manifest.get("target") == requirements["target"]["id"]
        and manifest.get("status") == "completed"
        and manifest.get("production_approval") is False
        and manifest.get("destructive_cleanup") is False
        and manifest.get("secret_values_exported") == 0
        and manifest.get("raw_system_identifier_exported") is False,
        "drill identity or authority drifted",
    )
    require(
        manifest.get("source_sha256") == source_inputs(source),
        "captured source checksums do not match reviewed inputs",
    )
    report = read_json(drill / "validation-report.json")
    checksums = report.get("canonical_sha256", {})
    require(
        checksums.get("requirements") == canonical_sha256(requirements)
        and checksums.get("recovery_scenarios")
        == canonical_sha256(scenarios),
        "validation used different decision documents",
    )


def review_positive(
    root: Path,
    drill: Path,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    report = read_json(drill / "validation-report.json")
    require(
        report.get("schema") == "pg36-ch21-validation-report-v1"
        and report.get("release") == requirements["release"]
        and report.get("status") == "ok"
        and report.get("decision")
        == {
            "sandbox_named_pitr": "accepted-with-exceptions",
            "production_ch21_gate": "pending",
            "regional_disaster_recovery": "not-run",
            "restore_directory": "retained-and-stopped",
        },
        "positive validation decision drifted",
    )
    require(
        report.get("accepted_exception_ids")
        == requirements["required_exception_ids"],
        "accepted exception set drifted",
    )
    recovery = report.get("recovery", {})
    boundary = recovery.get("boundary", {})
    require(
        boundary.get("base_present") is True
        and boundary.get("keep_present") is True
        and boundary.get("discard_present") is False
        and recovery.get("system_identifier_relation") == "matches source"
        and recovery.get("restored_timeline", 0)
        > recovery.get("source_timeline", 0)
        and recovery.get("rollback_write_probe") is True,
        "recovery boundary, lineage or write evidence drifted",
    )
    require(
        0 <= recovery.get("start_to_first_connection_ms", -1)
        <= recovery.get("start_to_promoted_ms", -1)
        <= requirements["objectives"]["maximum_start_to_promoted_ms"],
        "recovery phase timing is invalid",
    )
    for gate in ("preflight-ch19", "postflight-ch19"):
        value = read_json(root / gate / "validation-report.json")
        require(
            value.get("schema") == "pg36-ch19-validation-report-v1"
            and value.get("status") == "ok",
            f"{gate} is not a passing chapter-19 gate",
        )
    return report


def review_negative(drill: Path) -> None:
    report = read_json(drill / "negative-report.json")
    require(
        report.get("schema") == "pg36-ch21-negative-report-v1"
        and report.get("status") == "ok"
        and report.get("case_count") == len(EXPECTED_NEGATIVE_CODES),
        "negative report identity drifted",
    )
    actual = {
        str(row.get("id")): str(row.get("actual_code"))
        for row in report.get("cases", [])
        if isinstance(row, dict)
    }
    expected = {
        str(row.get("id")): str(row.get("expected_code"))
        for row in report.get("cases", [])
        if isinstance(row, dict)
    }
    require(
        actual == EXPECTED_NEGATIVE_CODES
        and expected == EXPECTED_NEGATIVE_CODES,
        "counterexamples did not fail with intended policy codes",
    )


def review_raw_evidence(drill: Path) -> None:
    for path in sorted(drill.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        require(
            all(token not in lowered for token in FORBIDDEN_TEXT),
            f"evidence appears to contain a forbidden secret field: {path}",
        )
        require(
            not re.search(
                r'"(?:system-id|system_identifier)"\s*:\s*"?[0-9]{12,}',
                text,
            ),
            f"evidence contains a raw PostgreSQL system identifier: {path}",
        )
    manifest = read_json(drill / "drill-manifest.json")
    restore_root = str(manifest.get("restore_root", ""))
    require(
        re.fullmatch(
            r"/data/pg36-ch21-restore/"
            r"run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}",
            restore_root,
        )
        is not None,
        "retained restore path crossed its allowlist",
    )
    shutdown = read_json(drill / "isolated-shutdown.json")
    require(
        shutdown.get("postmaster_pid_exists") is False
        and shutdown.get("socket_exists") is False
        and shutdown.get("tcp_listener") is False
        and shutdown.get("restore_directory_retained") is True,
        "retained restore is not stopped and isolated",
    )


def review_optional_outcome(
    source: Path,
    report: dict[str, Any],
) -> None:
    path = source / "restore-run.json"
    if not path.exists():
        return
    outcome = read_json(path)
    recovery = report["recovery"]
    require(
        outcome.get("schema") == "pg36-ch21-reference-run-v1"
        and outcome.get("run_id") == report.get("run_id")
        and outcome.get("backup_label") == report["backup"]["label"]
        and outcome.get("restore_copy_ms")
        == recovery["restore_copy_ms"]
        and outcome.get("start_to_first_connection_ms")
        == recovery["start_to_first_connection_ms"]
        and outcome.get("start_to_promoted_ms")
        == recovery["start_to_promoted_ms"]
        and outcome.get("source_timeline")
        == recovery["source_timeline"]
        and outcome.get("restored_timeline")
        == recovery["restored_timeline"]
        and outcome.get("production_ch21_gate") == "pending",
        "published reference-run outcome drifted from accepted evidence",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = args.evidence
        drill = root / "drill"
        requirements = read_json(args.source_dir / "requirements.json")
        scenarios = read_json(args.source_dir / "recovery-scenarios.json")
        review_source_identity(
            drill,
            args.source_dir,
            requirements,
            scenarios,
        )
        report = review_positive(root, drill, requirements)
        review_negative(drill)
        review_raw_evidence(drill)
        review_optional_outcome(args.source_dir, report)
    except (ReviewError, KeyError, TypeError, OSError) as error:
        sys.stderr.write(f"review failed: {error}\n")
        return 1
    print("status=review-ok")
    print("sandbox_named_pitr=accepted-with-exceptions")
    print(f"counterexamples={len(EXPECTED_NEGATIVE_CODES)}-rejected")
    print("secret_values_exported=0")
    print("raw_system_identifiers_exported=0")
    print("isolated_postmaster=stopped")
    print("restore_directory=retained")
    print("production_ch21_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
