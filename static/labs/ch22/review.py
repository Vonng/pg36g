#!/usr/bin/env python3
"""Review a complete chapter 22 service evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


OUTCOME_FILES = {"connection-run.json", "migration-effort.json"}
EXPECTED_NEGATIVE_CODES = {
    "claim-production-from-sandbox": "E_PRODUCTION_CLAIM",
    "route-primary-to-replica": "E_ENDPOINT",
    "route-replica-to-primary": "E_ENDPOINT",
    "route-offline-to-wrong-member": "E_ENDPOINT",
    "treat-session-state-as-sticky": "E_POOL_SEMANTICS",
    "accept-broken-protocol-prepare": "E_PREPARED",
    "accept-sql-prepare-across-backends": "E_PREPARED",
    "exceed-server-pool-cap": "E_BACKPRESSURE",
    "claim-no-queue-with-saturation": "E_BACKPRESSURE",
    "leave-pgbouncer-overridden": "E_CONFIG_RESTORE",
    "lose-acknowledged-write": "E_COMMIT_EVIDENCE",
    "leave-unknown-outcome-unreconciled": "E_COMMIT_EVIDENCE",
    "accept-excessive-write-gap": "E_RECOVERY_TIME",
    "leave-wrong-final-leader": "E_TOPOLOGY",
    "degrade-source-after-drill": "E_TOPOLOGY",
}


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
) -> None:
    manifest = read_json(drill / "drill-manifest.json")
    require(
        manifest.get("schema") == "pg36-ch22-drill-manifest-v1"
        and manifest.get("release") == requirements["release"]
        and manifest.get("target") == requirements["target"]["id"]
        and manifest.get("status") == "completed"
        and manifest.get("production_approval") is False
        and manifest.get("unplanned_failure_injected") is False
        and manifest.get("destructive_cleanup") is False
        and manifest.get("secret_values_exported") == 0,
        "drill identity or authority drifted",
    )
    require(
        manifest.get("source_sha256") == source_inputs(source),
        "captured source checksums do not match reviewed inputs",
    )


def review_positive(
    root: Path,
    drill: Path,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    report = read_json(drill / "validation-report.json")
    require(
        report.get("schema") == "pg36-ch22-validation-report-v1"
        and report.get("release") == requirements["release"]
        and report.get("status") == "ok"
        and report.get("decision")
        == {
            "sandbox_service_contract": "accepted-with-exceptions",
            "production_ch22_gate": "pending",
            "unplanned_failover": "not-run",
            "vip_or_multi_entry_failover": "not-run",
            "tls_acceptance": "not-run",
            "production_load_test": "not-run",
        },
        "positive validation decision drifted",
    )
    require(
        report.get("accepted_exception_ids")
        == requirements["required_exception_ids"],
        "accepted exception set drifted",
    )
    service = report.get("service", {})
    switch = report.get("switch", {})
    require(
        service.get("endpoint_count") == 4
        and service.get("pool_mode") == "transaction"
        and service.get("pool_server_cap_observed") <= 2
        and service.get("pool_waiters_observed", 0) >= 1
        and service.get("protocol_prepare_reassignment") is True
        and service.get("sql_prepare_expected_sqlstate") == "26000",
        "service semantics evidence drifted",
    )
    require(
        switch.get("forward_timeline")
        == switch.get("initial_timeline", -2) + 1
        and switch.get("restored_timeline")
        == switch.get("initial_timeline", -2) + 2
        and switch.get("acknowledged", 0)
        >= requirements["switch_probe"]["minimum_acknowledged_attempts"]
        and switch.get("maximum_conservative_write_gap_ms")
        <= requirements["switch_probe"][
            "maximum_conservative_write_gap_ms"
        ]
        and switch.get("final_leader") == "pg-test-1",
        "planned switch evidence drifted",
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
        report.get("schema") == "pg36-ch22-negative-report-v1"
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


def review_client_events(drill: Path, report: dict[str, Any]) -> None:
    events: list[dict[str, Any]] = []
    for line in (drill / "client-events.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        value = json.loads(line)
        require(
            value.get("schema") == "pg36-ch22-client-event-v1",
            "client event schema drifted",
        )
        events.append(value)
    reconciliation = read_json(drill / "reconciliation.json")
    require(
        len(events) == reconciliation["counts"]["events"]
        and len(
            [row for row in events if row.get("outcome") == "acknowledged"]
        )
        == reconciliation["counts"]["acknowledged"]
        and len(
            [row for row in events if row.get("outcome") == "unknown"]
        )
        == reconciliation["counts"]["unknown"]
        and len({row.get("token") for row in events}) == len(events),
        "raw client event count or token identity drifted",
    )
    require(
        reconciliation.get("run_id") == report.get("run_id")
        and reconciliation["counts"]["acknowledged_rows_missing"] == 0
        and reconciliation["counts"]["duplicate_tokens"] == 0
        and reconciliation["counts"]["unreconciled_unknown_outcomes"] == 0,
        "raw reconciliation drifted",
    )


def review_raw_evidence(drill: Path) -> None:
    forbidden_plain = (
        "password=",
        "insecure-password",
        "scram-sha-256$",
        "pg_admin_password:",
        "pg_monitor_password:",
    )
    sensitive_json = re.compile(
        r'"(?:password|credential|scram_verifier)"\s*:\s*"[^"]+"',
        re.IGNORECASE,
    )
    raw_system_id = re.compile(
        r'"(?:system-id|system_identifier)"\s*:\s*"?[0-9]{12,}',
        re.IGNORECASE,
    )
    for path in sorted(drill.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        require(
            all(token not in lowered for token in forbidden_plain),
            f"evidence contains a forbidden secret representation: {path}",
        )
        require(
            sensitive_json.search(text) is None,
            f"evidence contains a credential value: {path}",
        )
        require(
            raw_system_id.search(text) is None,
            f"evidence contains a raw PostgreSQL system identifier: {path}",
        )
    manifest = read_json(drill / "drill-manifest.json")
    fixture = read_json(drill / "fixture.json")
    replica = read_json(drill / "replica-visibility.json")
    require(
        manifest.get("private_service_file_removed") is True
        and manifest.get("declared_login_role_mutated") is False
        and manifest.get("secret_values_exported") == 0
        and fixture.get("credential_exported") is False
        and fixture.get("declared_role_preserved") is True
        and replica.get("token_value_exported") is False,
        "secret or private-file boundary drifted",
    )


def review_optional_outcome(
    source: Path,
    report: dict[str, Any],
) -> None:
    path = source / "connection-run.json"
    if not path.exists():
        return
    outcome = read_json(path)
    require(
        outcome.get("schema") == "pg36-ch22-reference-run-v1"
        and outcome.get("run_id") == report.get("run_id")
        and outcome.get("sandbox_service_contract")
        == "accepted-with-exceptions"
        and outcome.get("production_ch22_gate") == "pending"
        and outcome.get("final_leader") == "pg-test-1",
        "published chapter-22 outcome drifted",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--source-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    drill = args.evidence_root / "drill"
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        review_source_identity(drill, args.source_dir, requirements)
        report = review_positive(
            args.evidence_root,
            drill,
            requirements,
        )
        review_negative(drill)
        review_client_events(drill, report)
        review_raw_evidence(drill)
        review_optional_outcome(args.source_dir, report)
    except (ReviewError, OSError, json.JSONDecodeError, KeyError) as exc:
        sys.stderr.write(f"review failed: {exc}\n")
        return 1
    print("status=review-ok")
    print(
        "service="
        f"endpoints={report['service']['endpoint_count']} "
        f"pool_active_max={report['service']['pool_server_cap_observed']} "
        f"waiters_max={report['service']['pool_waiters_observed']}"
    )
    print(
        "switch="
        f"acknowledged={report['switch']['acknowledged']} "
        f"unknown={report['switch']['unknown']} "
        "missing=0 duplicates=0 unreconciled=0 "
        f"gap_ms={report['switch']['maximum_conservative_write_gap_ms']:.3f}"
    )
    print("counterexamples=15-rejected")
    print("sandbox_service_contract=accepted-with-exceptions")
    print("production_ch22_gate=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
