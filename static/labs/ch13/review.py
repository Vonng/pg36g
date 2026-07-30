#!/usr/bin/env python3
"""Review ch13 evidence by contracts and state relationships."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


MARKER = "pg36 ch13 routine guard lab; safe to rebuild"
FIXED_PATH = "search_path=pg_catalog, pg_temp"


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


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError(f"cannot read {path}: {exc}") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    document = "\n".join(
        line
        for line in read_text(path).splitlines()
        if line and not line.startswith("[context] ")
    )
    try:
        return list(csv.DictReader(document.splitlines()))
    except csv.Error as exc:
        raise ReviewError(f"cannot parse CSV {path}: {exc}") from exc


def key_value_csv(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    require(
        all(set(row) == {"key", "value"} for row in rows),
        f"{path.name} is not a key/value document",
    )
    result = {row["key"]: row["value"] for row in rows}
    require(
        len(result) == len(rows),
        f"{path.name} contains duplicate keys",
    )
    return result


def review_manifest(
    evidence: Path,
    baseline_path: Path,
) -> str:
    manifest = read_text(evidence / "manifest.txt")
    checksum = canonical_checksum(baseline_path)
    require(
        "database=pg36_shop" in manifest
        and "in_recovery=false" in manifest
        and "model_version=ch04-v1" in manifest
        and "application_role=pg36_app" in manifest
        and "validation_path=direct-postgresql" in manifest
        and f"release_candidate_checksum={checksum}" in manifest,
        "manifest target or release identity drifted",
    )
    version = re.search(r"server_version=(\d+)\.", manifest)
    require(
        version is not None and 14 <= int(version.group(1)) <= 18,
        "manifest server version is outside the chapter contract",
    )
    return checksum


def review_routines(evidence: Path) -> None:
    rows = read_csv(evidence / "routine-catalog.csv")
    routines = {row["signature"]: row for row in rows}
    expected = {
        "shop_ch13.allowed_transition(text,text)": (
            "f",
            "sql",
            "i",
            "t",
            "s",
            "f",
            "",
        ),
        "shop_ch13.order_snapshot(bigint)": (
            "f",
            "sql",
            "s",
            "t",
            "s",
            "t",
            FIXED_PATH,
        ),
        "shop_ch13.guard_order_transition()": (
            "f",
            "plpgsql",
            "v",
            "f",
            "u",
            "t",
            FIXED_PATH,
        ),
        "shop_ch13.audit_order_transition()": (
            "f",
            "plpgsql",
            "v",
            "f",
            "u",
            "t",
            FIXED_PATH,
        ),
        "shop_ch13.validate_paid_order()": (
            "f",
            "plpgsql",
            "v",
            "f",
            "u",
            "t",
            FIXED_PATH,
        ),
        "shop_ch13.transition_order(bigint,bigint,text,text)": (
            "f",
            "plpgsql",
            "v",
            "f",
            "u",
            "t",
            FIXED_PATH,
        ),
        "shop_ch13.capture_payment(bigint,bigint,text,bigint,text)": (
            "f",
            "plpgsql",
            "v",
            "f",
            "u",
            "t",
            FIXED_PATH,
        ),
        (
            "shop_ch13.expire_stale_orders"
            "(timestamp with time zone,integer,integer)"
        ): (
            "p",
            "plpgsql",
            "v",
            "f",
            "u",
            "f",
            "",
        ),
    }
    require(
        set(routines) == set(expected),
        "routine inventory drifted",
    )

    for signature, attributes in expected.items():
        row = routines[signature]
        actual = (
            row["prokind"],
            row["language"],
            row["provolatile"],
            row["proisstrict"],
            row["proparallel"],
            row["prosecdef"],
            row["proconfig"],
        )
        require(
            actual == attributes and row["marker"] == MARKER,
            f"routine attributes drifted: {signature}",
        )


def review_triggers(evidence: Path) -> None:
    rows = read_csv(evidence / "trigger-catalog.csv")
    triggers = {
        (row["relation_name"], row["trigger_name"]): row
        for row in rows
    }
    require(
        set(triggers)
        == {
            ("payment", "z_validate_payment"),
            ("sales_order", "a_guard_order_transition"),
            ("sales_order", "z_audit_order_transition"),
            ("sales_order", "z_validate_paid_order"),
        },
        "trigger inventory drifted",
    )

    guard = triggers[
        ("sales_order", "a_guard_order_transition")
    ]
    require(
        guard["row_level"] == "t"
        and guard["before_timing"] == "t"
        and guard["tgdeferrable"] == "f"
        and guard["function_signature"]
        == "shop_ch13.guard_order_transition()",
        "BEFORE ROW guard declaration drifted",
    )

    audit = triggers[
        ("sales_order", "z_audit_order_transition")
    ]
    require(
        audit["row_level"] == "f"
        and audit["before_timing"] == "f"
        and audit["old_transition_table"] == "old_rows"
        and audit["new_transition_table"] == "new_rows"
        and "FOR EACH STATEMENT" in audit["trigger_definition"],
        "transition-table audit declaration drifted",
    )

    for key in (
        ("payment", "z_validate_payment"),
        ("sales_order", "z_validate_paid_order"),
    ):
        row = triggers[key]
        require(
            row["row_level"] == "t"
            and row["tgdeferrable"] == "t"
            and row["tginitdeferred"] == "t"
            and "CONSTRAINT TRIGGER" in row["trigger_definition"],
            f"deferred constraint trigger drifted: {key}",
        )

    require(
        all(row["marker"] == MARKER for row in rows),
        "trigger marker drifted",
    )


def review_security(evidence: Path) -> None:
    actual = key_value_csv(evidence / "security-catalog.csv")
    require(
        actual
        == {
            "app_schema_usage": "true",
            "app_order_select": "false",
            "app_order_update": "false",
            "app_payment_insert": "false",
            "app_snapshot_execute": "true",
            "app_transition_execute": "true",
            "app_capture_execute": "true",
            "app_guard_execute": "false",
            "app_procedure_execute": "false",
            "public_transition_execute": "false",
        },
        "least-privilege matrix drifted",
    )


def review_transition_matrix(evidence: Path) -> None:
    rows = read_csv(evidence / "transition-matrix.csv")
    require(
        len(rows) == 49,
        "transition matrix must enumerate 7 x 7 states",
    )
    allowed = {
        (row["old_status"], row["new_status"])
        for row in rows
        if row["allowed"] == "t"
    }
    require(
        all(row["allowed"] in {"t", "f"} for row in rows)
        and allowed
        == {
            ("created", "paid"),
            ("created", "canceled"),
            ("created", "expired"),
            ("paid", "packing"),
            ("packing", "shipped"),
            ("shipped", "completed"),
        },
        "allowed transition property drifted",
    )


def review_expected_failure(
    evidence: Path,
    name: str,
    sqlstate: str,
) -> None:
    exit_text = read_text(evidence / f"{name}.exit").strip()
    stderr = read_text(evidence / f"{name}.stderr")
    require(
        exit_text == "exit=3"
        and re.search(rf"\b{re.escape(sqlstate)}\b", stderr),
        f"{name} did not fail with SQLSTATE {sqlstate}",
    )


def review_failures(evidence: Path) -> None:
    for name, sqlstate in {
        "invalid-transition": "P3613",
        "paid-without-payment": "P3614",
        "version-conflict": "P3616",
        "payment-mismatch": "P3618",
        "delete-payment": "P3614",
        "direct-write": "42501",
        "procedure-in-transaction": "2D000",
    }.items():
        review_expected_failure(evidence, name, sqlstate)


def review_exception(evidence: Path) -> None:
    rows = read_csv(evidence / "exception-probe.csv")
    require(
        rows
        == [
            {
                "event": "caught-inner-subtransaction",
                "sqlstate": "P3613",
                "message": "order status transition rejected",
                "status_after": "created",
                "version_after": "0",
            }
        ],
        "exception subtransaction evidence drifted",
    )


def review_function_stats(evidence: Path) -> None:
    rows = read_csv(evidence / "function-stats.csv")
    stats = {row["signature"]: row for row in rows}
    required = {
        "shop_ch13.allowed_transition(text,text)",
        "shop_ch13.audit_order_transition()",
        "shop_ch13.guard_order_transition()",
        "shop_ch13.order_snapshot(bigint)",
        "shop_ch13.transition_order(bigint,bigint,text,text)",
    }
    require(
        required <= set(stats),
        "transaction-local function counters are incomplete",
    )
    require(
        all(
            int(stats[signature]["calls"]) >= 1
            and stats[signature]["total_time_nonnegative"] == "t"
            and stats[signature]["self_time_nonnegative"] == "t"
            for signature in required
        ),
        "function counter relationships drifted",
    )


def review_behavior(evidence: Path) -> None:
    api = read_text(evidence / "api-happy.csv")
    require(
        re.search(r"(?m)^101,canceled,1$", api) is not None
        and re.search(
            r"(?m)^102,paid,1,pay-ch13-102$",
            api,
        )
        is not None,
        "happy-path command function output drifted",
    )

    bulk = read_csv(evidence / "bulk-update.csv")
    manifest = read_text(evidence / "manifest.txt")
    admin_match = re.search(
        r"(?m)^admin_session_user=(.+)$",
        manifest,
    )
    require(
        admin_match is not None,
        "admin session user is missing from manifest",
    )
    require(
        bulk
        == [
            {
                "affected_count": "3",
                "order_ids": "{105,106,107}",
                "actor": "bulk-lab",
                "session_actor": admin_match.group(1),
            }
        ],
        "statement-level bulk audit evidence drifted",
    )

    procedure = read_csv(evidence / "procedure-run.csv")
    require(
        procedure == [{"p_total": "5"}],
        "top-level procedure result drifted",
    )
    rerun = read_csv(evidence / "procedure-rerun.csv")
    require(
        rerun == [{"p_total": "0"}],
        "procedure rerun was not idempotent",
    )


def review_final(
    evidence: Path,
    baseline: dict[str, Any],
) -> None:
    actual = key_value_csv(evidence / "final-state.csv")
    expected_state = baseline["expected_state"]
    expected = {
        "orders": str(expected_state["orders"]),
        "status_created": str(expected_state["created"]),
        "status_paid": str(expected_state["paid"]),
        "status_canceled": str(expected_state["canceled"]),
        "status_expired": str(expected_state["expired"]),
        "payments": str(expected_state["payments"]),
        "history_rows": str(expected_state["history_rows"]),
        "audit_statements": str(
            expected_state["audit_statements"]
        ),
        "audit_affected_sum": str(
            expected_state["audit_affected_rows"]
        ),
        "max_audit_batch": "3",
        "captured_minor": "2000",
        "business_checksum": expected_state[
            "business_checksum"
        ],
    }
    require(actual == expected, "final state or checksum drifted")

    verify = read_text(evidence / "verify.txt")
    for line in (
        "status=ok",
        "fixture=ch13-routine-guard-v1",
        (
            "boundary=check+before-trigger+deferred-constraint"
            "+command-function"
        ),
        "procedure_batches=2/2/1",
        "audit=10-rows/6-statements",
    ):
        require(line in verify, f"verify output is missing {line}")


def review_baseline(baseline: dict[str, Any]) -> None:
    require(
        baseline["schema"] == "pg36-ch13-release-proposal-v1"
        and baseline["release"] == "1.1-proposal"
        and baseline["fixture"] == "ch13-routine-guard-v1"
        and baseline["rollback"]["uses_cascade"] is False
        and baseline["security"]["public_execute"] is False
        and len(baseline["limitations"]) == 5,
        "release proposal contract drifted",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence_dir.resolve()
    baseline_path = (
        args.repo_root.resolve()
        / "static/labs/ch13/baseline-v1.1-proposal.json"
    )

    try:
        baseline = load_json(baseline_path)
        review_baseline(baseline)
        checksum = review_manifest(evidence, baseline_path)
        review_routines(evidence)
        review_triggers(evidence)
        review_security(evidence)
        review_transition_matrix(evidence)
        review_failures(evidence)
        review_exception(evidence)
        review_function_stats(evidence)
        review_behavior(evidence)
        review_final(evidence, baseline)
    except ReviewError as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1

    print("status=ok")
    print("business=orders:13/payments:1/history:10/audit:6")
    print(
        "boundary=check+before-row+deferred-constraint"
        "+security-definer"
    )
    print(
        "failure=42501/P3613/P3614/P3616/P3618/2D000"
    )
    print(
        "transaction=exception-subtransaction"
        "+commit-time-check+procedure-batches"
    )
    print(
        "observability=transition-table+function-stats+sqlstate"
    )
    print("release=1.1-proposal")
    print(f"release_candidate_checksum={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
