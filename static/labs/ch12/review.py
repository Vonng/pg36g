#!/usr/bin/env python3
"""Review ch12 evidence by contracts and state relationships."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


class ReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc


def canonical_checksum(path: Path) -> str:
    document = load_json(path)
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_api(evidence: Path) -> None:
    document = load_json(evidence / "api-results.json")
    require(
        document.get("schema") == "pg36-ch12-api-results-v1"
        and document.get("status") == "ok",
        "API evidence schema drifted",
    )
    cases = {
        case["label"]: case
        for case in document.get("cases", [])
    }
    expected = {
        "liveness": (200, None),
        "readiness": (200, None),
        "order-created": (201, None),
        "order-replayed": (201, None),
        "order-idempotency-conflict":
            (409, "idempotency_conflict"),
        "order-insufficient":
            (409, "insufficient_inventory"),
        "order-missing-sku": (404, "sku_not_found"),
        "order-invalid-json-shape": (400, "invalid_json"),
        "order-statement-timeout":
            (504, "database_timeout"),
        "order-serialization-retry": (201, None),
        "order-page-first": (200, None),
        "order-page-second": (200, None),
        "payment-amount-mismatch":
            (422, "amount_mismatch"),
        "payment-captured": (201, None),
        "payment-replayed": (201, None),
        "payment-idempotency-conflict":
            (409, "idempotency_conflict"),
        "payment-already-paid": (409, "already_paid"),
        "order-read": (200, None),
        "order-not-found": (404, "order_not_found"),
        "order-injection-shaped-input":
            (400, "invalid_order"),
        "pool-saturated-liveness": (200, None),
        "pool-saturated-readiness":
            (503, "pool_unavailable"),
        "pool-saturated-request":
            (503, "pool_unavailable"),
        "pool-recovered-readiness": (200, None),
    }
    require(
        set(cases) == set(expected),
        "API case inventory drifted",
    )
    for label, (status, code) in expected.items():
        case = cases[label]
        require(
            case["status"] == status,
            f"{label} status drifted",
        )
        if code is not None:
            require(
                case["body"]["error"]["code"] == code,
                f"{label} error code drifted",
            )

    require(
        cases["order-replayed"]["replayed"] is True
        and cases["payment-replayed"]["replayed"] is True,
        "idempotency replay header drifted",
    )
    require(
        cases["order-created"]["body"]
        == cases["order-replayed"]["body"]
        and cases["payment-captured"]["body"]
        == cases["payment-replayed"]["body"],
        "idempotent response body drifted",
    )
    require(
        cases["order-created"]["body"]["order_id"] == 1200001
        and cases["order-serialization-retry"]["body"][
            "order_id"
        ]
        == 1200002
        and cases["payment-captured"]["body"]["payment_id"]
        == 1200001,
        "business identity relationship drifted",
    )


def review_database(evidence: Path) -> None:
    state = load_json(evidence / "db-final.json")
    require(
        state
        == {
            "schema": "pg36-ch12-final-state-v1",
            "orders": 2,
            "items": 2,
            "payments": 1,
            "outbox": 3,
            "order_requests": 2,
            "payment_requests": 1,
            "inventory": {
                "PG36-SKU-001": {
                    "available": 8,
                    "version": 1,
                },
                "PG36-SKU-002": {
                    "available": 4,
                    "version": 1,
                },
            },
        },
        "final database state drifted",
    )

    verify = (evidence / "verify.txt").read_text(
        encoding="utf-8"
    )
    require(
        "status=ok" in verify
        and "orders=2" in verify
        and "payments=1" in verify
        and "outbox=3" in verify
        and "inventory=PG36-SKU-001:8:v1,PG36-SKU-002:4:v1"
        in verify
        and "app_can_create=false" in verify
        and "app_can_delete=false" in verify
        and "active_api_queries=0" in verify
        and "relation_checksum=f8a7bfae59c6d16cd323abecfefe1014"
        in verify,
        "SQL verification relationship drifted",
    )


def review_failures(evidence: Path) -> None:
    cancellation = load_json(evidence / "client-cancel.json")
    require(
        cancellation.get("schema")
        == "pg36-ch12-client-cancel-v1"
        and cancellation.get("active_workers_observed") == 1
        and cancellation.get("active_workers_after_cancel") == 0
        and cancellation.get("transport_result")
        != "unexpected-response",
        "client cancellation relationship drifted",
    )

    saturation = load_json(evidence / "pool-saturation.json")
    require(
        saturation
        == {
            "schema": "pg36-ch12-pool-saturation-v1",
            "max_conns": 2,
            "database_workers_observed": 2,
            "liveness_status": 200,
            "readiness_status": 503,
            "readiness_error": "pool_unavailable",
            "business_request_status": 503,
            "business_request_error": "pool_unavailable",
            "holder_statuses": [200, 200],
            "recovered_readiness_status": 200,
        },
        "pool saturation relationship drifted",
    )

    metrics = (evidence / "metrics.txt").read_text(
        encoding="utf-8"
    )
    for pattern in [
        r"^pg36_transaction_retries_total 1$",
        r"^pg36_idempotent_replays_total 2$",
        r'^pg36_db_errors_total\{sqlstate="40001"\} 1$',
        r'^pg36_db_errors_total\{sqlstate="57014"\} 1$',
        r"^pg36_pool_canceled_acquire_total [2-9][0-9]*$",
        r'^pg36_pool_connections\{state="max"\} 2$',
    ]:
        require(
            re.search(pattern, metrics, re.MULTILINE)
            is not None,
            f"metrics relationship drifted: {pattern}",
        )


def review_trace(evidence: Path) -> None:
    trace = load_json(evidence / "trace-correlation.json")
    require(
        trace
        == {
            "schema": "pg36-ch12-trace-correlation-v1",
            "order_trace": "trace-order-001",
            "payment_trace": "trace-payment-001",
            "application_names": ["pg36-ch12-api"],
            "outbox_traces": {
                "order:order-001:placed":
                    "trace-order-001",
                "order:order-retry:placed":
                    "trace-retry-001",
                "payment:pay-001:captured":
                    "trace-payment-001",
            },
        },
        "trace correlation drifted",
    )

    log_path = evidence / "service.log"
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError(f"cannot read service log: {exc}") from exc
    require(
        "password=" not in log_text.lower()
        and "pg36_database_url" not in log_text.lower(),
        "service log contains connection secret material",
    )
    entries: list[dict[str, Any]] = []
    for line in log_text.splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ReviewError(
                f"service log is not JSON: {line[:80]}"
            ) from exc

    require(
        any(
            entry.get("msg") == "service_start"
            and entry.get("query_mode") == "exec"
            and entry.get("max_conns") == 2
            for entry in entries
        ),
        "service startup identity drifted",
    )
    require(
        any(
            entry.get("msg") == "request_error"
            and entry.get("error_code") == "database_timeout"
            and entry.get("sqlstate") == "57014"
            for entry in entries
        ),
        "57014 structured log evidence missing",
    )
    require(
        any(
            entry.get("msg") == "request_error"
            and entry.get("error_code") == "client_cancelled"
            and entry.get("trace_id") == "trace-client-cancel"
            for entry in entries
        ),
        "client cancellation structured log missing",
    )
    require(
        sum(
            1
            for entry in entries
            if entry.get("msg") == "request_error"
            and entry.get("error_code") == "pool_unavailable"
        )
        >= 2,
        "pool acquisition errors are missing from logs",
    )


def review_release(
    evidence: Path,
    repo_root: Path,
) -> tuple[str, str]:
    manifest = (evidence / "manifest.txt").read_text(
        encoding="utf-8"
    )
    direct_path = (
        "validation_path=direct-postgresql" in manifest
        and "pooler_validation=not-run" in manifest
        and "app_endpoint_source=derived-from-admin-service"
        in manifest
    )
    supplied_path = (
        "validation_path=operator-supplied-application-endpoint"
        in manifest
        and "pooler_validation=behavior-run-config-identity-required"
        in manifest
        and "app_endpoint_source=PG36_APP_DATABASE_URL"
        in manifest
    )
    require(
        (direct_path or supplied_path)
        and "runtime_user=pg36_app" in manifest
        and "query_mode=exec" in manifest
        and "pgx_module=github.com/jackc/pgx/v5 v5.10.0"
        in manifest,
        "validation-path manifest drifted",
    )

    candidate_path = (
        repo_root
        / "static/labs/ch12/baseline-v1.0-rc.json"
    )
    candidate = load_json(candidate_path)
    require(
        candidate.get("candidate_baseline") == "1.0.0"
        and candidate.get("status") == "release-candidate"
        and len(candidate.get("promotion_blockers", [])) == 4
        and candidate.get("verified_now")
        == [
            "PostgreSQL 18.4 direct endpoint",
            "pgx v5.10.0 with QueryExecModeExec",
            "application-side pgxpool MaxConns=2 failure lab",
            "runtime role pg36_app without DDL or DELETE",
        ],
        "v1.0 release-candidate boundary drifted",
    )
    dependency = candidate["depends_on_candidates"][0]
    dependency_path = (
        repo_root
        / "static"
        / dependency["proposal"].lstrip("/")
    )
    require(
        canonical_checksum(dependency_path)
        == dependency["proposal_checksum"],
        "v0.6 dependency checksum drifted",
    )
    checksum = canonical_checksum(candidate_path)
    require(
        f"release_candidate_checksum={checksum}" in manifest,
        "v1.0 candidate checksum is missing from manifest",
    )
    validation = (
        "pg18.4-direct/pgx-v5.10.0/pooler:not-run"
        if direct_path
        else "operator-endpoint-behavior/config-identity:required"
    )
    return checksum, validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        review_api(args.evidence_dir)
        review_database(args.evidence_dir)
        review_failures(args.evidence_dir)
        review_trace(args.evidence_dir)
        checksum, validation = review_release(
            args.evidence_dir,
            args.repo_root,
        )
    except (ReviewError, OSError, KeyError, TypeError) as exc:
        print(f"ch12 review failed: {exc}", file=sys.stderr)
        return 1

    print("status=ok")
    print("business=orders:2/payments:1/outbox:3")
    print("contract=idempotency+atomic-reservation+outbox")
    print("failure=57014/40001/client-cancel/pool-exhaustion")
    print("observability=trace+json-log+pool-metrics")
    print(f"validation={validation}")
    print("release=1.0.0-rc")
    print(f"release_candidate_checksum={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
