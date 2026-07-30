#!/usr/bin/env python3
"""Validate chapter 25 contracts, live evidence, and adversarial mutations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


JSON_NAMES = [
    "requirements.json",
    "signal-contract.json",
    "coverage-matrix.json",
    "diagnostic-pack-contract.json",
    "route-tests.json",
]

YAML_NAMES = [
    "recording-rules.yml",
    "alert-rules.yml",
    "rule-tests.yml",
    "alertmanager-sandbox.yml",
]

SOURCE_NAMES = [
    *JSON_NAMES,
    *YAML_NAMES,
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]

REQUIRED_RECORDS = {
    "pg36_shop:sli_availability_bad_ratio:rate5m",
    "pg36_shop:sli_availability_bad_ratio:rate30m",
    "pg36_shop:sli_availability_bad_ratio:rate1h",
    "pg36_shop:sli_availability_bad_ratio:rate6h",
    "pg36_shop:sli_availability_bad_ratio:rate3d",
    "pg36_shop:sli_latency_bad_ratio:rate5m",
    "pg36_shop:sli_latency_bad_ratio:rate1h",
    "pg36_shop:sli_freshness_bad_ratio:rate5m",
    "pg36_shop:sli_freshness_bad_ratio:rate1h",
    "pg36:replica_replay_distance_bytes:max",
    "pg36:archive_failures:increase15m",
    "pg36:longest_transaction_seconds:max",
    "pg36:table_freeze_age:max",
    "pg36:dead_tuples:sum",
    "pg36:exporter_unavailable:max",
    "pg36:vmalert_rule_errors:sum",
    "pg36:vmalert_missed_iterations:increase15m",
    "pg36:notification_failures:increase15m",
}

PROPOSED_ALERTS = {
    "PG36ShopLatencyFastBurn",
    "PG36ShopRestoreEvidenceStale",
    "PG36ArchiveFailureActive",
    "PG36TransactionAgeHorizon",
    "PG36FreezeAgeHorizon",
    "PG36ShopSLIMissing",
}

REQUIRED_ANNOTATIONS = {
    "summary",
    "user_impact",
    "first_safe_action",
    "verification",
    "dashboard",
}

FORBIDDEN_LABELS = {
    "customer_id",
    "tenant_id",
    "order_id",
    "idempotency_token",
    "trace_id",
    "raw_query_text",
    "raw_sql",
    "error_message",
    "client_addr",
    "password",
    "token",
}


class ValidationError(RuntimeError):
    """Raised when an artifact cannot be loaded or interpreted."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--negative-cases", type=Path)
    parser.add_argument("--isolated-log", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc


def read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError(f"cannot read YAML {path}: {exc}") from exc


def write_private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail_if(
    failures: list[str],
    condition: bool,
    message: str,
) -> None:
    if condition:
        failures.append(message)


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_contracts(source_dir: Path) -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for name in JSON_NAMES:
        contracts[name] = read_json(source_dir / name)
    for name in YAML_NAMES:
        contracts[name] = read_yaml(source_dir / name)
    return contracts


def index_rows(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if isinstance(row, dict) and nonempty(row.get(key)):
            result[str(row[key])] = row
    return result


def flatten_rules(document: Any, kind: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(document, dict):
        return result
    for group in document.get("groups", []):
        if not isinstance(group, dict):
            continue
        for rule in group.get("rules", []):
            if isinstance(rule, dict) and nonempty(rule.get(kind)):
                result[str(rule[kind])] = rule
    return result


def validate_requirements(
    failures: list[str],
    requirements: dict[str, Any],
) -> None:
    fail_if(
        failures,
        requirements.get("schema")
        != "pg36-ch25-observability-requirements-v1",
        "requirements schema drifted",
    )
    target = requirements.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("service_id") != "pg36_shop"
        or target.get("environment") != "l2-sandbox"
        or target.get("expected_database_hostname") != "pg-test-1"
        or target.get("expected_cluster_name") != "pg-test"
        or target.get("production_data") is not False
        or target.get("production_traffic") is not False
        or target.get("production_slo_claimed") is not False,
        "sandbox scope is not explicit",
    )
    exercise = requirements.get("exercise", {})
    fail_if(
        failures,
        exercise.get("live_rule_deployment") is not False,
        "live rule deployment is forbidden",
    )
    fail_if(
        failures,
        exercise.get("real_notification") is not False,
        "real notification is forbidden",
    )
    fail_if(
        failures,
        exercise.get("live_alert_submission") is not False
        or exercise.get("live_silence_creation") is not False
        or exercise.get("database_mutation") != "none",
        "online mutation boundary drifted",
    )
    fail_if(
        failures,
        requirements.get("production_ch25_gate") != "pending"
        or requirements.get("production_approval") is not False,
        "production gate must remain pending",
    )
    required = set(requirements.get("required_artifacts", []))
    fail_if(
        failures,
        not {
            "signal-contract.json",
            "recording-rules.yml",
            "alert-rules.yml",
            "rule-tests.yml",
            "alertmanager-sandbox.yml",
            "route-tests.json",
            "diagnostic-pack-contract.json",
            "coverage-matrix.json",
        }.issubset(required),
        "required artifact inventory is incomplete",
    )
    fail_if(
        failures,
        len(requirements.get("hard_rejections", [])) < 18,
        "hard rejection inventory is incomplete",
    )


def validate_signal_contract(
    failures: list[str],
    signal: dict[str, Any],
) -> None:
    fail_if(
        failures,
        signal.get("schema") != "pg36-ch25-signal-contract-v1",
        "signal contract schema drifted",
    )
    fail_if(
        failures,
        len(signal.get("question_layers", [])) != 4
        or len(signal.get("signal_roles", [])) != 4
        or len(signal.get("application_slis", [])) != 5
        or len(signal.get("postgresql_native", [])) < 6,
        "signal inventory is incomplete",
    )
    identity = signal.get("identity", {})
    forbidden = set(identity.get("forbidden_unbounded", []))
    fail_if(
        failures,
        not FORBIDDEN_LABELS.issubset(forbidden),
        "forbidden labels allowlist drifted",
    )
    evidence_fields = set(
        signal.get("sql_observation", {})
        .get("pg_stat_statements", {})
        .get("evidence_fields", [])
    )
    fail_if(
        failures,
        bool(
            evidence_fields
            & {"query", "raw_sql", "bind values", "client_addr"}
        ),
        "query text entered pg_stat_statements evidence",
    )
    missing = signal.get("missing_and_cost", {})
    fail_if(
        failures,
        missing.get("missing_is_healthy") is not False,
        "missing data was interpreted as healthy",
    )
    fail_if(
        failures,
        missing.get("timing_disabled_means_zero") is not False,
        "disabled timing instrumentation was interpreted as zero",
    )
    fail_if(
        failures,
        any(
            row.get("expected_live_status")
            not in {
                "absent-until-application-instrumented",
                "absent-until-probe-implemented",
                "absent-until-reconciliation-implemented",
                "absent-until-evidence-export-implemented",
            }
            for row in signal.get("application_slis", [])
        ),
        "application SLI expected-live state drifted",
    )
    sql_observation = signal.get("sql_observation", {})
    pgss = sql_observation.get("pg_stat_statements", {})
    fail_if(
        failures,
        pgss.get("required_preload") is not True
        or pgss.get("required_extension") is not True
        or "pg_stat_statements_info.stats_reset"
        not in pgss.get("reset_requirements", []),
        "pg_stat_statements reset contract is incomplete",
    )
    logging = sql_observation.get("logging", {})
    fail_if(
        failures,
        "raw SQL" not in logging.get("forbidden_export", [])
        or "full bind parameters"
        not in logging.get("forbidden_export", []),
        "logging secret boundary drifted",
    )


def validate_coverage(
    failures: list[str],
    coverage: dict[str, Any],
) -> None:
    fail_if(
        failures,
        coverage.get("schema") != "pg36-ch25-coverage-matrix-v1",
        "coverage schema drifted",
    )
    rows = index_rows(coverage.get("rows"), "id")
    fail_if(
        failures,
        len(rows) < 14,
        "coverage matrix is incomplete",
    )
    for row_id in (
        "COV-USER-AVAILABILITY",
        "COV-USER-LATENCY",
        "COV-READ-FRESHNESS",
        "COV-CORRECTNESS",
        "COV-RESTORE",
    ):
        row = rows.get(row_id, {})
        fail_if(
            failures,
            row.get("live_expected") is not False
            or row.get("live_status") != "expected-gap"
            or not nonempty(row.get("blind_spot")),
            "application SLI gap was hidden",
        )
    deployment = coverage.get("deployment", {})
    fail_if(
        failures,
        deployment.get("chapter_recording_rules_live") is not False
        or deployment.get("chapter_alert_rules_live") is not False
        or deployment.get("chapter_routes_live") is not False,
        "chapter rules live claim is forbidden",
    )
    fail_if(
        failures,
        deployment.get("real_notification_exercised") is not False,
        "real notification exercised claim is forbidden",
    )
    fail_if(
        failures,
        coverage.get("next_diagnostic_chapter") != "ch31"
        or coverage.get("production_ch25_gate") != "pending"
        or coverage.get("production_approval") is not False,
        "coverage handoff or production boundary drifted",
    )


def validate_diagnostic_pack(
    failures: list[str],
    pack: dict[str, Any],
) -> None:
    fail_if(
        failures,
        pack.get("schema") != "pg36-ch25-diagnostic-pack-v1",
        "diagnostic pack schema drifted",
    )
    controls = pack.get("query_controls", {})
    fail_if(
        failures,
        controls.get("explain_analyze_allowed") is not False,
        "EXPLAIN ANALYZE entered diagnostic capture",
    )
    fail_if(
        failures,
        controls.get("statistics_reset_allowed") is not False
        or controls.get("load_generation_allowed") is not False
        or controls.get("database_statement_timeout") != "5s"
        or controls.get("database_lock_timeout") != "500ms",
        "diagnostic query safety controls drifted",
    )
    access = pack.get("access", {})
    fail_if(
        failures,
        access.get("filesystem_mode")
        != "0600 files under a 0700 directory",
        "private evidence mode drifted",
    )
    fields = [
        str(field).lower()
        for section in pack.get("sections", [])
        for field in section.get("fields", [])
    ]
    fail_if(
        failures,
        any(
            forbidden in field and "without" not in field
            for field in fields
            for forbidden in (
                "raw sql",
                "bind value",
                "password",
                "token value",
                "log body",
                "client address",
            )
        ),
        "diagnostic pack secrets are permitted",
    )
    fail_if(
        failures,
        len(pack.get("sections", [])) != 7
        or any(
            not isinstance(section.get("maximum_bytes"), int)
            or section["maximum_bytes"] > 1048576
            for section in pack.get("sections", [])
        ),
        "diagnostic pack size contract drifted",
    )
    fail_if(
        failures,
        pack.get("causal_language", {}).get(
            "dashboard_spike_is_root_cause"
        )
        is not False,
        "dashboard correlation was promoted to root cause",
    )


def validate_recording_rules(
    failures: list[str],
    recording: dict[str, Any],
) -> None:
    groups = recording.get("groups", []) if isinstance(recording, dict) else []
    seen: set[str] = set()
    for group in groups:
        rules = group.get("rules", []) if isinstance(group, dict) else []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            fail_if(
                failures,
                "alert" in rule,
                "recording group contains an alert and creates rule chaining",
            )
            record = rule.get("record")
            if nonempty(record):
                seen.add(str(record))
            fail_if(
                failures,
                not nonempty(record) or not nonempty(rule.get("expr")),
                "recording rule is incomplete",
            )
    fail_if(
        failures,
        not REQUIRED_RECORDS.issubset(seen),
        "recording rule inventory is incomplete",
    )
    archive_expr = str(
        flatten_rules(recording, "record")
        .get("pg36:archive_failures:increase15m", {})
        .get("expr", "")
    )
    fail_if(
        failures,
        "increase(pg_archiver_failed_count[15m])" not in archive_expr,
        "archive recording rule does not use a bounded increment",
    )


def validate_alert_rules(
    failures: list[str],
    alerts_document: dict[str, Any],
    accepted_candidates: dict[str, dict[str, Any]],
) -> None:
    alerts = flatten_rules(alerts_document, "alert")
    fail_if(
        failures,
        not set(accepted_candidates).issubset(alerts),
        "accepted alert inventory drifted",
    )
    fail_if(
        failures,
        not PROPOSED_ALERTS.issubset(alerts),
        "proposed alert inventory is incomplete",
    )
    for alert_name, candidate in accepted_candidates.items():
        rule = alerts.get(alert_name, {})
        labels = rule.get("labels", {})
        annotations = rule.get("annotations", {})
        policy_drift = (
            labels.get("route") != candidate.get("route")
            or labels.get("severity") != candidate.get("severity")
            or labels.get("owner_function")
            != candidate.get("owner_function")
            or labels.get("runbook_id") != candidate.get("runbook_id")
            or labels.get("governance_status") != "accepted-ch24"
            or str(rule.get("for")) != str(candidate.get("for"))
            or (
                candidate.get("objective_id") is not None
                and labels.get("objective_id")
                != candidate.get("objective_id")
            )
            or not REQUIRED_ANNOTATIONS.issubset(set(annotations))
            or annotations.get("first_safe_action")
            != candidate.get("first_safe_action")
        )
        fail_if(
            failures,
            policy_drift,
            f"accepted alert policy drifted: {alert_name}",
        )
    multiwindow = {
        "PG36ShopAvailabilityFastBurn": ("rate1h", "rate5m"),
        "PG36ShopAvailabilitySlowBurn": ("rate6h", "rate30m"),
        "PG36ShopAvailabilityBudgetTicket": ("rate3d", "rate6h"),
        "PG36ShopFreshnessFastBurn": ("rate1h", "rate5m"),
        "PG36ShopLatencyFastBurn": ("rate1h", "rate5m"),
    }
    for name, tokens in multiwindow.items():
        expression = str(alerts.get(name, {}).get("expr", ""))
        fail_if(
            failures,
            not all(token in expression for token in tokens)
            or "and on" not in " ".join(expression.split()),
            f"multiwindow alert lost one window: {name}",
        )
    for name in PROPOSED_ALERTS:
        labels = alerts.get(name, {}).get("labels", {})
        fail_if(
            failures,
            labels.get("route") != "test"
            or labels.get("severity") != "candidate"
            or labels.get("governance_status")
            != "proposed-not-accepted",
            f"proposed alert escaped test route: {name}",
        )
    capacity = alerts.get("PG36ShopCapacityHorizon", {})
    fail_if(
        failures,
        capacity.get("labels", {}).get("route") != "ticket",
        "capacity must ticket rather than page",
    )
    archive_expr = " ".join(
        str(alerts.get("PG36ArchiveFailureActive", {}).get("expr", "")).split()
    )
    fail_if(
        failures,
        "pg36:archive_failures:increase15m" not in archive_expr
        or "pg_archiver_finish_time" not in archive_expr
        or archive_expr.strip() == "pg_archiver_failed_count > 0",
        "archive cumulative counter was treated as an active failure",
    )
    for name, rule in alerts.items():
        labels = rule.get("labels", {})
        fail_if(
            failures,
            bool(FORBIDDEN_LABELS & set(labels)),
            f"unbounded or secret label appears in alert: {name}",
        )
        fail_if(
            failures,
            not nonempty(labels.get("owner_function"))
            or not nonempty(labels.get("runbook_id"))
            or not REQUIRED_ANNOTATIONS.issubset(
                set(rule.get("annotations", {}))
            ),
            f"alert is not actionable: {name}",
        )


MATCHER_RE = re.compile(
    r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"\s*$'
)


def matcher_matches(matcher: str, labels: dict[str, str]) -> bool:
    parsed = MATCHER_RE.match(matcher)
    if not parsed:
        raise ValidationError(f"unsupported Alertmanager matcher: {matcher}")
    key, operator, expected = parsed.groups()
    actual = str(labels.get(key, ""))
    if operator == "=":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == "=~":
        return re.fullmatch(expected, actual) is not None
    return re.fullmatch(expected, actual) is None


def match_all(matchers: Any, labels: dict[str, str]) -> bool:
    if not isinstance(matchers, list):
        return False
    return all(matcher_matches(str(matcher), labels) for matcher in matchers)


def resolve_route(config: dict[str, Any], labels: dict[str, str]) -> list[str]:
    root = config.get("route", {})
    receivers: list[str] = []
    for child in root.get("routes", []):
        if match_all(child.get("matchers", []), labels):
            receivers.append(str(child.get("receiver")))
            if child.get("continue") is not True:
                return receivers
    return receivers or [str(root.get("receiver"))]


def inhibition_matches(
    config: dict[str, Any],
    source: dict[str, str],
    target: dict[str, str],
) -> bool:
    for rule in config.get("inhibit_rules", []):
        if not match_all(rule.get("source_matchers", []), source):
            continue
        if not match_all(rule.get("target_matchers", []), target):
            continue
        equal = rule.get("equal", [])
        if all(source.get(key) == target.get(key) for key in equal):
            return True
    return False


def validate_alertmanager(
    failures: list[str],
    config: dict[str, Any],
) -> None:
    route = config.get("route", {})
    fail_if(
        failures,
        route.get("group_by")
        != ["service", "environment", "alertname"],
        "Alertmanager grouping contract drifted",
    )
    receivers = config.get("receivers", [])
    receiver_names = {
        receiver.get("name")
        for receiver in receivers
        if isinstance(receiver, dict)
    }
    fail_if(
        failures,
        len(receiver_names) != 7
        or any(
            not nonempty(name) or not str(name).endswith("-sink")
            for name in receiver_names
        ),
        "sandbox receiver inventory drifted",
    )
    fail_if(
        failures,
        any(
            set(receiver) != {"name"}
            for receiver in receivers
            if isinstance(receiver, dict)
        ),
        "receiver integration is forbidden in the sandbox",
    )
    for child in route.get("routes", []):
        fail_if(
            failures,
            not any(
                'environment = "isolated-lab"' == str(matcher)
                for matcher in child.get("matchers", [])
            ),
            "sandbox route lacks environment isolation",
        )
    for rule in config.get("inhibit_rules", []):
        target_text = " ".join(
            str(value) for value in rule.get("target_matchers", [])
        )
        fail_if(
            failures,
            "PG36ShopCorrectnessMismatch" in target_text
            or 'class = "integrity"' in target_text,
            "correctness inhibition is forbidden",
        )
    fail_if(
        failures,
        not any(
            'alertname = "PG36MonitoringPathBroken"'
            in rule.get("source_matchers", [])
            and 'class = "derived-missing"'
            in rule.get("target_matchers", [])
            for rule in config.get("inhibit_rules", [])
        ),
        "metamonitoring inhibition is missing or too broad",
    )


def validate_routes(
    failures: list[str],
    routes: dict[str, Any],
    alertmanager: dict[str, Any],
) -> None:
    fail_if(
        failures,
        routes.get("schema") != "pg36-ch25-route-tests-v1",
        "route tests schema drifted",
    )
    fail_if(
        failures,
        routes.get("real_receiver") is not False,
        "route tests contain a real receiver",
    )
    fail_if(
        failures,
        routes.get("live_alertmanager_used") is not False,
        "live Alertmanager use is forbidden",
    )
    route_tests = routes.get("tests", [])
    fail_if(
        failures,
        len(route_tests) != 8,
        "route test inventory is incomplete",
    )
    for test in route_tests:
        expected = test.get("expected_receivers", [])
        resolved = resolve_route(
            alertmanager,
            {
                str(key): str(value)
                for key, value in test.get("labels", {}).items()
            },
        )
        fail_if(
            failures,
            resolved != expected
            or any(not str(name).startswith("pg36-") for name in expected)
            or any(not str(name).endswith("-sink") for name in expected),
            f"route expectation drifted: {test.get('id')}",
        )
    inhibition_tests = routes.get("inhibition_tests", [])
    fail_if(
        failures,
        len(inhibition_tests) != 5,
        "inhibition test inventory is incomplete",
    )
    for test in inhibition_tests:
        actual = inhibition_matches(
            alertmanager,
            {
                str(key): str(value)
                for key, value in test.get("source", {}).items()
            },
            {
                str(key): str(value)
                for key, value in test.get("target", {}).items()
            },
        )
        fail_if(
            failures,
            actual is not test.get("expected_inhibited"),
            f"inhibition expectation drifted: {test.get('id')}",
        )


def validate_rule_tests(
    failures: list[str],
    tests_document: dict[str, Any],
    accepted_names: set[str],
) -> None:
    fail_if(
        failures,
        tests_document.get("rule_files")
        != ["recording-rules.yml", "alert-rules.yml"],
        "rule test files drifted",
    )
    fail_if(
        failures,
        tests_document.get("evaluation_interval") != "1m",
        "rule test evaluation interval drifted",
    )
    tested_alerts: set[str] = set()
    fast_expectations: list[Any] = []
    expression_tests = 0
    for test in tests_document.get("tests", []):
        expression_tests += len(test.get("metricsql_expr_test", []))
        for case in test.get("alert_rule_test", []):
            name = case.get("alertname")
            if nonempty(name):
                tested_alerts.add(str(name))
            if name == "PG36ShopAvailabilityFastBurn":
                fast_expectations.append(case.get("exp_alerts"))
    fail_if(
        failures,
        not accepted_names.issubset(tested_alerts)
        or "PG36ShopLatencyFastBurn" not in tested_alerts
        or "PG36ShopSLIMissing" not in tested_alerts,
        "rule tests do not cover accepted and boundary alerts",
    )
    fail_if(
        failures,
        expression_tests < 1
        or not any(value == [] for value in fast_expectations)
        or not any(bool(value) for value in fast_expectations),
        "rule tests do not cover recording, firing, and recovery",
    )
    group_order = tests_document.get("group_eval_order", [])
    fail_if(
        failures,
        group_order[:3]
        != [
            "pg36-shop-sli-recording",
            "pg36-postgresql-diagnostic-recording",
            "pg36-observation-meta-recording",
        ],
        "recording and alert group evaluation order drifted",
    )


def validate_contracts(
    contracts: dict[str, Any],
    accepted_candidates: dict[str, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    validate_requirements(failures, contracts["requirements.json"])
    validate_signal_contract(failures, contracts["signal-contract.json"])
    validate_coverage(failures, contracts["coverage-matrix.json"])
    validate_diagnostic_pack(
        failures, contracts["diagnostic-pack-contract.json"]
    )
    validate_recording_rules(
        failures, contracts["recording-rules.yml"]
    )
    validate_alert_rules(
        failures,
        contracts["alert-rules.yml"],
        accepted_candidates,
    )
    validate_alertmanager(
        failures, contracts["alertmanager-sandbox.yml"]
    )
    validate_routes(
        failures,
        contracts["route-tests.json"],
        contracts["alertmanager-sandbox.yml"],
    )
    validate_rule_tests(
        failures,
        contracts["rule-tests.yml"],
        set(accepted_candidates),
    )
    return failures


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_evidence(
    failures: list[str],
    evidence: dict[str, Any],
    source_dir: Path,
    upstream_root: Path,
) -> None:
    fail_if(
        failures,
        evidence.get("schema")
        != "pg36-ch25-observability-evidence-v1",
        "evidence schema drifted",
    )
    fail_if(
        failures,
        evidence.get("risk") != "L0-live-capture"
        or evidence.get("mutation") != "none",
        "live capture mutation boundary drifted",
    )
    target = evidence.get("target", {})
    fail_if(
        failures,
        target.get("id") != "pg36-l2-vagrant/pg-test"
        or target.get("production_data") is not False
        or target.get("production_traffic") is not False
        or target.get("production_slo_claimed") is not False,
        "evidence target sandbox boundary drifted",
    )
    hashes = evidence.get("source_hashes", {})
    for name in SOURCE_NAMES:
        fail_if(
            failures,
            hashes.get(name) != sha256(source_dir / name),
            f"source hash drifted: {name}",
        )
    requirements = read_json(source_dir / "requirements.json")
    ch24 = evidence.get("chapter_24", {})
    fail_if(
        failures,
        ch24.get("run_id")
        != requirements["upstream_governance"]["required_run_id"]
        or ch24.get("production_ch24_gate") != "pending",
        "chapter 24 governance binding drifted",
    )
    for name in requirements["upstream_governance"]["required_files"]:
        fail_if(
            failures,
            ch24.get("source_hashes", {}).get(name)
            != sha256(upstream_root / "ch24" / name),
            f"chapter 24 source hash drifted: {name}",
        )
    live = evidence.get("live", {})
    versions = live.get("versions", {})
    fail_if(
        failures,
        versions.get("pigsty") != "v4.4.0"
        or versions.get("postgresql") != 18
        or not all(
            nonempty(versions.get(name))
            for name in (
                "VictoriaMetrics",
                "VMAlert",
                "VictoriaLogs",
                "VictoriaTraces",
                "Alertmanager",
                "pg_exporter",
            )
        ),
        "live component version inventory is incomplete",
    )
    fail_if(
        failures,
        not all(
            row.get("ok") is True
            for row in live.get("health", {}).values()
        ),
        "one or more live endpoints are unhealthy",
    )
    vm = live.get("victoriametrics", {})
    fail_if(
        failures,
        not isinstance(vm.get("total_series"), int)
        or vm.get("total_series", 0) <= 0
        or not isinstance(vm.get("total_label_value_pairs"), int)
        or vm.get("total_label_value_pairs", 0) <= 0,
        "VictoriaMetrics TSDB inventory is empty",
    )
    vmalert = live.get("vmalert", {})
    fail_if(
        failures,
        vmalert.get("group_count", 0) <= 0
        or vmalert.get("rule_count")
        != vmalert.get("alert_rule_count", 0)
        + vmalert.get("recording_rule_count", 0)
        or vmalert.get("group_error_count") != 0
        or vmalert.get("rule_error_count") != 0,
        "live VMAlert baseline contains errors",
    )
    metrics = live.get("metric_summaries", {})
    fail_if(
        failures,
        metrics.get("pg_up", {}).get("series", 0) < 4
        or metrics.get("pg_up", {}).get("minimum") != 1.0
        or metrics.get("pg_exporter_up", {}).get("series", 0) < 4
        or metrics.get("pg_exporter_up", {}).get("minimum") != 1.0,
        "PostgreSQL exporter reachability baseline failed",
    )
    fail_if(
        failures,
        live.get("application_metrics", {}).get("series") != 0,
        "application SLI metrics unexpectedly appeared; review coverage before claiming the gap",
    )
    freshness = live.get("metric_freshness", {})
    fail_if(
        failures,
        any(
            row.get("newest_sample_age_seconds") is None
            or row.get("newest_sample_age_seconds", 9999) > 180
            for row in freshness.values()
        ),
        "monitoring samples are stale",
    )
    patroni = live.get("patroni", {})
    fail_if(
        failures,
        patroni.get("name") != "pg-test-1"
        or patroni.get("scope") != "pg-test"
        or patroni.get("role") != "primary"
        or patroni.get("state") != "running"
        or patroni.get("server_version_num", 0) // 10000 != 18
        or len(patroni.get("replication", [])) != 2
        or patroni.get("client_address_exported") is not False,
        "Patroni target identity or replication baseline drifted",
    )
    postgres = live.get("postgresql", {})
    identity = postgres.get("identity", {})
    fail_if(
        failures,
        postgres.get("host_identity") != "pg-test-1"
        or identity.get("cluster_name") != "pg-test"
        or identity.get("in_recovery") is not False
        or identity.get("server_version_num", 0) // 10000 != 18
        or len(postgres.get("replication", [])) != 2,
        "PostgreSQL target identity or replication baseline drifted",
    )
    fail_if(
        failures,
        any(
            row.get("state") != "streaming"
            or row.get("sync_state") != "async"
            or row.get("sent_replay_gap_bytes", -1) < 0
            for row in postgres.get("replication", [])
        ),
        "PostgreSQL replication evidence is incomplete",
    )
    settings = postgres.get("settings", {})
    fail_if(
        failures,
        "pg_stat_statements" not in settings.get(
            "shared_preload_libraries", ""
        )
        or "auto_explain"
        not in settings.get("shared_preload_libraries", "")
        or settings.get("track_activities") != "on"
        or settings.get("track_counts") != "on"
        or settings.get("track_io_timing") != "on"
        or settings.get("track_wal_io_timing") != "off"
        or settings.get("logging_collector") != "on"
        or settings.get("log_file_mode") not in {"0600", "0640"}
        or settings.get("auto_explain.log_min_duration") != "1000"
        or settings.get("auto_explain.log_analyze") != "on"
        or settings.get("auto_explain.log_timing") != "on"
        or settings.get("auto_explain.sample_rate") != "1"
        or settings.get("pg_stat_statements.track") != "all"
        or settings.get("pg_stat_statements.track_planning") != "off"
        or settings.get("pg_stat_statements.track_utility") != "off",
        "PostgreSQL observation settings drifted",
    )
    pgss = postgres.get("pg_stat_statements", {})
    fail_if(
        failures,
        pgss.get("extension", {}).get("schema") != "monitor"
        or not nonempty(pgss.get("extension", {}).get("version"))
        or parse_timestamp(pgss.get("info", {}).get("stats_reset")) is None
        or pgss.get("aggregate", {}).get("statement_rows", 0) <= 0
        or pgss.get("aggregate", {}).get("calls", 0) <= 0,
        "pg_stat_statements reset or aggregate evidence is incomplete",
    )
    archiver = postgres.get("archiver", {})
    failed_count = archiver.get("failed_count", 0)
    last_failed = parse_timestamp(archiver.get("last_failed_time"))
    last_success = parse_timestamp(archiver.get("last_archived_time"))
    fail_if(
        failures,
        failed_count > 0
        and (
            last_failed is None
            or last_success is None
            or last_success <= last_failed
        ),
        "historical archive failure did not retain later recovery evidence",
    )
    fail_if(
        failures,
        postgres.get("query_text_exported") is not False
        or postgres.get("client_address_exported") is not False
        or postgres.get("statistics_reset_performed") is not False
        or live.get("alertmanager", {}).get(
            "configuration_exported"
        )
        is not False
        or live.get("alertmanager", {}).get(
            "alert_bodies_exported"
        )
        is not False,
        "secret or reset boundary drifted in evidence",
    )
    claims = evidence.get("claims", {})
    fail_if(
        failures,
        any(value is not False for value in claims.values())
        or evidence.get("production_ch25_gate") != "pending"
        or evidence.get("production_approval") is not False,
        "evidence overclaims deployment, delivery, SLO, or production approval",
    )


def mutate_path(
    root: dict[str, Any],
    path: str,
    operation: str,
    value: Any,
) -> None:
    parts = path.split(".")
    current: Any = root
    for part in parts[:-1]:
        current = (
            current[int(part)]
            if isinstance(current, list)
            else current[part]
        )
    final = parts[-1]
    if operation == "set":
        if isinstance(current, list):
            current[int(final)] = value
        else:
            current[final] = value
    elif operation == "append":
        target = (
            current[int(final)]
            if isinstance(current, list)
            else current[final]
        )
        target.append(value)
    elif operation == "delete_value":
        target = (
            current[int(final)]
            if isinstance(current, list)
            else current[final]
        )
        target.remove(value)
    else:
        raise ValidationError(f"unknown mutation operation: {operation}")


def validate_negative_cases(
    contracts: dict[str, Any],
    accepted_candidates: dict[str, dict[str, Any]],
    negative: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    cases = negative.get("cases", [])
    fail_if(
        failures,
        negative.get("schema") != "pg36-ch25-negative-cases-v1"
        or len(cases) < 24,
        "negative case inventory is incomplete",
    )
    for case in cases:
        mutated = copy.deepcopy(contracts)
        try:
            mutate_path(
                mutated[case["artifact"]],
                case["path"],
                case["operation"],
                case.get("value"),
            )
            mutation_failures = validate_contracts(
                mutated, accepted_candidates
            )
            token = str(case.get("expect_rejection_contains", ""))
            rejected = bool(mutation_failures) and any(
                token in message for message in mutation_failures
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            rejected = False
            mutation_failures = [f"mutation failed to apply: {exc}"]
        if not rejected:
            failures.append(
                f"counterexample was not rejected as expected: {case.get('id')}"
            )
        results.append(
            {
                "id": case.get("id"),
                "rejected": rejected,
                "expected_token": case.get(
                    "expect_rejection_contains"
                ),
                "failure_count": len(mutation_failures),
            }
        )
    return failures, results


def validate_isolated_log(
    failures: list[str],
    path: Path | None,
) -> None:
    if path is None:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"cannot read isolated exercise log: {exc}")
        return
    required = (
        "vmalert_dry_run=ok",
        "vmalert_unit_tests=ok",
        "alertmanager_config=ok",
        "route_tests=8-ok",
        "inhibition_tests=5-ok",
        "real_receiver=false",
        "live_alertmanager_used=false",
        "remote_cleanup=ok",
    )
    for token in required:
        fail_if(
            failures,
            token not in text,
            f"isolated exercise token missing: {token}",
        )


def main() -> int:
    args = parse_args()
    try:
        contracts = load_contracts(args.source_dir)
        ch24_candidates = read_json(
            args.upstream_root / "ch24" / "alert-candidates.json"
        )
        accepted_candidates = index_rows(
            ch24_candidates.get("accepted"), "id"
        )
        expected_names = set(
            contracts["requirements.json"].get(
                "accepted_alerts_from_ch24", []
            )
        )
        if set(accepted_candidates) != expected_names:
            raise ValidationError(
                "chapter 24 accepted alert inventory changed"
            )

        if args.negative_cases:
            negative = read_json(args.negative_cases)
            failures, results = validate_negative_cases(
                contracts, accepted_candidates, negative
            )
            report = {
                "schema": "pg36-ch25-negative-report-v1",
                "passed": not failures,
                "case_count": len(results),
                "rejected_count": sum(
                    row["rejected"] for row in results
                ),
                "failure_count": len(failures),
                "failures": failures,
                "cases": results,
            }
        else:
            failures = validate_contracts(
                contracts, accepted_candidates
            )
            if args.evidence:
                evidence = read_json(args.evidence)
                validate_evidence(
                    failures,
                    evidence,
                    args.source_dir,
                    args.upstream_root,
                )
            validate_isolated_log(failures, args.isolated_log)
            alert_count = len(
                flatten_rules(
                    contracts["alert-rules.yml"], "alert"
                )
            )
            record_count = len(
                flatten_rules(
                    contracts["recording-rules.yml"], "record"
                )
            )
            report = {
                "schema": "pg36-ch25-validation-report-v1",
                "passed": not failures,
                "failure_count": len(failures),
                "failures": failures,
                "accepted_alert_count": len(accepted_candidates),
                "proposed_alert_count": len(PROPOSED_ALERTS),
                "alert_rule_count": alert_count,
                "recording_rule_count": record_count,
                "route_test_count": len(
                    contracts["route-tests.json"].get("tests", [])
                ),
                "inhibition_test_count": len(
                    contracts["route-tests.json"].get(
                        "inhibition_tests", []
                    )
                ),
                "coverage_row_count": len(
                    contracts["coverage-matrix.json"].get("rows", [])
                ),
                "live_evidence_checked": args.evidence is not None,
                "isolated_exercise_checked": args.isolated_log is not None,
            }
        write_private_json(args.output, report)
    except (OSError, ValidationError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    if report["passed"] is not True:
        for failure in report["failures"]:
            print(f"validation failed: {failure}", file=sys.stderr)
        return 1
    print("status=validation-ok")
    print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
