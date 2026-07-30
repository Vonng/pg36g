#!/usr/bin/env python3
"""Capture a read-only, secret-minimized chapter 25 observability baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_NAMES = [
    "requirements.json",
    "signal-contract.json",
    "coverage-matrix.json",
    "diagnostic-pack-contract.json",
    "recording-rules.yml",
    "alert-rules.yml",
    "rule-tests.yml",
    "alertmanager-sandbox.yml",
    "route-tests.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]

METRIC_NAMES = [
    "pg_up",
    "pg_exporter_up",
    "pg_in_recovery",
    "pg_lag",
    "pg_repl_replay_diff",
    "pg_archiver_failed_count",
    "pg_activity_count",
    "pg_activity_max_tx_duration",
    "pg_db_deadlocks",
    "pg_db_temp_bytes",
    "pg_table_age",
    "pg_table_n_dead_tup",
    "vmalert_iteration_missed_total",
    "vmalert_alerting_rules_errors_total",
    "vmalert_recording_rules_errors_total",
    "alertmanager_notifications_failed_total",
]

SAFE_LABELS = {
    "cls",
    "ins",
    "ip",
    "instance",
    "job",
    "datname",
    "state",
    "application_name",
    "sync_state",
    "backend_type",
    "object",
    "context",
    "integration",
    "reason",
}

POSTGRES_SQL = r"""
SET statement_timeout = '5s';
SET lock_timeout = '500ms';
SET default_transaction_read_only = on;
BEGIN READ ONLY;
SELECT jsonb_build_object(
  'identity', jsonb_build_object(
    'cluster_name', current_setting('cluster_name'),
    'port', current_setting('port')::int,
    'server_version', current_setting('server_version'),
    'server_version_num', current_setting('server_version_num')::int,
    'in_recovery', pg_is_in_recovery()
  ),
  'settings', (
    SELECT jsonb_object_agg(name, setting ORDER BY name)
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'shared_preload_libraries','compute_query_id','track_activities',
      'track_counts','track_functions','track_io_timing',
      'track_wal_io_timing','stats_fetch_consistency',
      'log_min_duration_statement','log_min_duration_sample',
      'log_statement_sample_rate','log_lock_waits','log_temp_files',
      'log_parameter_max_length','log_parameter_max_length_on_error'
      ,'logging_collector','log_destination','log_directory',
      'log_filename','log_file_mode','log_connections',
      'log_disconnections','deadlock_timeout',
      'auto_explain.log_analyze','auto_explain.log_buffers',
      'auto_explain.log_format','auto_explain.log_level',
      'auto_explain.log_min_duration',
      'auto_explain.log_nested_statements',
      'auto_explain.log_parameter_max_length',
      'auto_explain.log_settings','auto_explain.log_timing',
      'auto_explain.log_triggers','auto_explain.log_verbose',
      'auto_explain.log_wal','auto_explain.sample_rate',
      'pg_stat_statements.max','pg_stat_statements.save',
      'pg_stat_statements.track',
      'pg_stat_statements.track_planning',
      'pg_stat_statements.track_utility'
    ])
  ),
  'pg_stat_statements', jsonb_build_object(
    'extension', (
      SELECT jsonb_build_object(
        'version', e.extversion,
        'schema', n.nspname
      )
      FROM pg_extension e
      JOIN pg_namespace n ON n.oid = e.extnamespace
      WHERE e.extname = 'pg_stat_statements'
    ),
    'info', (
      SELECT to_jsonb(s) FROM monitor.pg_stat_statements_info AS s
    ),
    'aggregate', (
      SELECT jsonb_build_object(
        'statement_rows', count(*),
        'calls', coalesce(sum(calls), 0)::bigint,
        'total_exec_ms',
          round(coalesce(sum(total_exec_time), 0)::numeric, 2),
        'total_plan_ms',
          round(coalesce(sum(total_plan_time), 0)::numeric, 2),
        'rows', coalesce(sum(rows), 0)::bigint,
        'earliest_stats_since', min(stats_since),
        'latest_stats_since', max(stats_since),
        'earliest_minmax_since', min(minmax_stats_since),
        'latest_minmax_since', max(minmax_stats_since)
      )
      FROM monitor.pg_stat_statements
    )
  ),
  'activity', (
    SELECT coalesce(
      jsonb_agg(
        to_jsonb(q)
        ORDER BY state NULLS LAST, wait_event_type NULLS LAST
      ),
      '[]'::jsonb
    )
    FROM (
      SELECT
        state,
        wait_event_type,
        count(*) AS sessions,
        round(
          max(extract(epoch FROM (clock_timestamp() - xact_start)))
            FILTER (WHERE xact_start IS NOT NULL)::numeric,
          3
        ) AS max_xact_seconds,
        round(
          max(extract(epoch FROM (clock_timestamp() - query_start)))
            FILTER (WHERE query_start IS NOT NULL)::numeric,
          3
        ) AS max_query_seconds
      FROM pg_stat_activity
      WHERE backend_type = 'client backend'
      GROUP BY state, wait_event_type
    ) AS q
  ),
  'locks', (
    SELECT coalesce(
      jsonb_agg(to_jsonb(q) ORDER BY locktype, mode, granted),
      '[]'::jsonb
    )
    FROM (
      SELECT locktype, mode, granted, count(*) AS locks
      FROM pg_locks
      GROUP BY locktype, mode, granted
    ) AS q
  ),
  'replication', (
    SELECT coalesce(
      jsonb_agg(to_jsonb(q) ORDER BY application_name),
      '[]'::jsonb
    )
    FROM (
      SELECT
        application_name,
        state,
        sync_state,
        pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint
          AS sent_replay_gap_bytes,
        extract(epoch FROM write_lag) AS write_lag_seconds,
        extract(epoch FROM flush_lag) AS flush_lag_seconds,
        extract(epoch FROM replay_lag) AS replay_lag_seconds
      FROM pg_stat_replication
    ) AS q
  ),
  'wal', (SELECT to_jsonb(s) FROM pg_stat_wal AS s),
  'checkpointer', (
    SELECT to_jsonb(s) FROM pg_stat_checkpointer AS s
  ),
  'archiver', (SELECT to_jsonb(s) FROM pg_stat_archiver AS s),
  'io', (
    SELECT coalesce(
      jsonb_agg(to_jsonb(q) ORDER BY backend_type, object, context),
      '[]'::jsonb
    )
    FROM (
      SELECT
        backend_type,
        object,
        context,
        coalesce(sum(reads), 0)::bigint AS reads,
        coalesce(sum(read_bytes), 0)::bigint AS read_bytes,
        round(coalesce(sum(read_time), 0)::numeric, 3) AS read_ms,
        coalesce(sum(writes), 0)::bigint AS writes,
        coalesce(sum(write_bytes), 0)::bigint AS write_bytes,
        round(coalesce(sum(write_time), 0)::numeric, 3) AS write_ms,
        coalesce(sum(fsyncs), 0)::bigint AS fsyncs,
        round(coalesce(sum(fsync_time), 0)::numeric, 3) AS fsync_ms
      FROM pg_stat_io
      GROUP BY backend_type, object, context
      HAVING
        coalesce(sum(reads), 0)
        + coalesce(sum(writes), 0)
        + coalesce(sum(fsyncs), 0) > 0
    ) AS q
  ),
  'maintenance', (
    SELECT jsonb_build_object(
      'user_tables', count(*),
      'estimated_live_tuples', coalesce(sum(n_live_tup), 0)::bigint,
      'estimated_dead_tuples', coalesce(sum(n_dead_tup), 0)::bigint,
      'max_mod_since_analyze',
        coalesce(max(n_mod_since_analyze), 0)::bigint,
      'max_ins_since_vacuum',
        coalesce(max(n_ins_since_vacuum), 0)::bigint,
      'max_table_freeze_age',
        coalesce(max(age(c.relfrozenxid)), 0)
    )
    FROM pg_stat_user_tables AS s
    JOIN pg_class AS c ON c.oid = s.relid
  ),
  'database', (
    SELECT jsonb_build_object(
      'database_rows', count(*),
      'commits', coalesce(sum(xact_commit), 0)::bigint,
      'rollbacks', coalesce(sum(xact_rollback), 0)::bigint,
      'deadlocks', coalesce(sum(deadlocks), 0)::bigint,
      'temp_bytes', coalesce(sum(temp_bytes), 0)::bigint,
      'non_null_stats_reset', count(stats_reset),
      'stats_reset_min', min(stats_reset),
      'stats_reset_max', max(stats_reset)
    )
    FROM pg_stat_database
  )
);
COMMIT;
"""


class CaptureError(RuntimeError):
    """Raised when a required read-only observation cannot be captured."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read JSON {path}: {exc}") from exc


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


def fetch_bytes(url: str, timeout: float = 10.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pg36-ch25-read-only-capture/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:  # urllib exposes several transport exceptions
        raise CaptureError(f"HTTP read failed for {url}: {exc}") from exc


def fetch_json(url: str, timeout: float = 10.0) -> Any:
    try:
        return json.loads(fetch_bytes(url, timeout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"invalid JSON from {url}: {exc}") from exc


def health(url: str) -> dict[str, Any]:
    body = fetch_bytes(url, 5.0)
    return {
        "ok": body.strip().upper().startswith(b"OK"),
        "response_bytes": len(body),
    }


def extract_label(line: str, label: str) -> str | None:
    match = re.search(rf'(?:^|[,{{]){re.escape(label)}="([^"]*)"', line)
    return match.group(1) if match else None


def version_from_metrics(
    text: str,
    metric_name: str,
    label: str = "version",
) -> str | None:
    prefix = metric_name + "{"
    for line in text.splitlines():
        if line.startswith(prefix):
            return extract_label(line, label)
    return None


def query_vm(expression: str) -> dict[str, Any]:
    params = urllib.parse.urlencode({"query": expression})
    payload = fetch_json(
        f"http://10.10.10.10:8428/api/v1/query?{params}"
    )
    if payload.get("status") != "success":
        raise CaptureError(f"VictoriaMetrics query failed: {expression}")
    rows = payload.get("data", {}).get("result", [])
    values: list[float] = []
    label_keys: set[str] = set()
    identities: list[dict[str, str]] = []
    for row in rows:
        metric = row.get("metric", {})
        if isinstance(metric, dict):
            label_keys.update(str(key) for key in metric if key != "__name__")
            identity = {
                str(key): str(value)
                for key, value in metric.items()
                if key in SAFE_LABELS
            }
            if identity and identity not in identities:
                identities.append(identity)
        value = row.get("value", [None, None])
        try:
            number = float(value[1])
        except (IndexError, TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    return {
        "series": len(rows),
        "nonzero_series": sum(value != 0 for value in values),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "label_keys": sorted(label_keys),
        "safe_identities": identities[:16],
    }


def metric_freshness(metric_name: str, captured_epoch: float) -> dict[str, Any]:
    result = query_vm(f"timestamp({metric_name})")
    maximum = result.get("maximum")
    result["newest_sample_age_seconds"] = (
        round(max(0.0, captured_epoch - float(maximum)), 3)
        if isinstance(maximum, (int, float))
        else None
    )
    return result


def summarize_vmalert() -> dict[str, Any]:
    rules_payload = fetch_json("http://10.10.10.10:8880/api/v1/rules")
    alerts_payload = fetch_json("http://10.10.10.10:8880/api/v1/alerts")
    if (
        rules_payload.get("status") != "success"
        or alerts_payload.get("status") != "success"
    ):
        raise CaptureError("VMAlert API did not return success")
    groups = rules_payload.get("data", {}).get("groups", [])
    rules = [
        rule
        for group in groups
        for rule in group.get("rules", [])
        if isinstance(rule, dict)
    ]
    alerts = alerts_payload.get("data", {}).get("alerts", [])
    return {
        "group_count": len(groups),
        "rule_count": len(rules),
        "alert_rule_count": sum(
            rule.get("type") == "alerting" for rule in rules
        ),
        "recording_rule_count": sum(
            rule.get("type") == "recording" for rule in rules
        ),
        "group_error_count": sum(
            bool(group.get("lastError")) for group in groups
        ),
        "rule_error_count": sum(
            bool(rule.get("lastError")) for rule in rules
        ),
        "alert_rule_states": dict(
            Counter(
                str(rule.get("state"))
                for rule in rules
                if rule.get("type") == "alerting"
            )
        ),
        "current_alert_count": len(alerts),
        "current_alert_states": dict(
            Counter(str(alert.get("state")) for alert in alerts)
        ),
    }


def summarize_exporter(text: str) -> dict[str, Any]:
    help_names: set[str] = set()
    label_keys: set[str] = set()
    for line in text.splitlines():
        if line.startswith("# HELP "):
            parts = line.split(maxsplit=3)
            if len(parts) >= 3:
                help_names.add(parts[2])
        elif line and not line.startswith("#") and "{" in line:
            labels = line.split("{", 1)[1].split("}", 1)[0]
            for match in re.finditer(r"(?:^|,)([a-zA-Z_:][a-zA-Z0-9_:]*)=", labels):
                label_keys.add(match.group(1))
    required_prefixes = (
        "pg_activity_",
        "pg_archiver_",
        "pg_checkpointer_",
        "pg_db_",
        "pg_io_",
        "pg_query_",
        "pg_repl_",
        "pg_table_",
    )
    relevant = sorted(
        name
        for name in help_names
        if name in {"pg_up", "pg_version", "pg_in_recovery"}
        or name.startswith(required_prefixes)
    )
    return {
        "response_bytes": len(text.encode("utf-8")),
        "help_metric_count": len(help_names),
        "relevant_metric_count": len(relevant),
        "relevant_metric_names": relevant,
        "label_keys": sorted(label_keys),
        "version": version_from_metrics(
            text, "pg_exporter_build_info", "version"
        ),
    }


def run_command(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 20.0,
) -> str:
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        stderr = getattr(exc, "stderr", "")
        raise CaptureError(
            f"command failed: {command[0]}: {str(stderr).strip()}"
        ) from exc
    return completed.stdout.strip()


def ssh_target_args(
    ssh_user: str,
    bastion: str,
    database_primary: str,
) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-J",
        f"{ssh_user}@{bastion}",
        "-o",
        f"HostName={database_primary}",
        "-p",
        "22",
        f"{ssh_user}@pg36-ch25-database-target",
    ]


def capture_postgresql(
    ssh_user: str,
    bastion: str,
    database_primary: str,
) -> dict[str, Any]:
    prefix = ssh_target_args(ssh_user, bastion, database_primary)
    hostname = run_command(prefix + ["hostname", "-s"])
    raw = run_command(
        prefix
        + [
            "sudo",
            "-iu",
            "postgres",
            "psql",
            "-XqAt",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input_text=POSTGRES_SQL,
        timeout=30.0,
    )
    json_lines = [
        line
        for line in raw.splitlines()
        if line.lstrip().startswith("{")
    ]
    if len(json_lines) != 1:
        raise CaptureError(
            "PostgreSQL capture did not return exactly one JSON row"
        )
    try:
        result = json.loads(json_lines[0])
    except json.JSONDecodeError as exc:
        raise CaptureError(f"PostgreSQL JSON is invalid: {exc}") from exc
    result["host_identity"] = hostname
    result["access_path"] = "ProxyJump via sandbox bastion"
    result["query_text_exported"] = False
    result["client_address_exported"] = False
    result["statistics_reset_performed"] = False
    return result


def summarize_patroni() -> dict[str, Any]:
    value = fetch_json("http://10.10.10.11:8008/")
    patroni = value.get("patroni", {})
    replication = value.get("replication", [])
    return {
        "name": patroni.get("name"),
        "scope": patroni.get("scope"),
        "patroni_version": patroni.get("version"),
        "role": value.get("role"),
        "state": value.get("state"),
        "server_version_num": value.get("server_version"),
        "timeline": value.get("timeline"),
        "replication": [
            {
                "application_name": row.get("application_name"),
                "state": row.get("state"),
                "sync_state": row.get("sync_state"),
            }
            for row in replication
            if isinstance(row, dict)
        ],
        "client_address_exported": False,
    }


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        target = requirements["target"]
        captured_at = datetime.now(timezone.utc)
        captured_epoch = captured_at.timestamp()

        vm_metrics = fetch_bytes(
            "http://10.10.10.10:8428/metrics"
        ).decode("utf-8", errors="replace")
        vmalert_metrics = fetch_bytes(
            "http://10.10.10.10:8880/metrics"
        ).decode("utf-8", errors="replace")
        vlogs_metrics = fetch_bytes(
            "http://10.10.10.10:9428/metrics"
        ).decode("utf-8", errors="replace")
        vtraces_metrics = fetch_bytes(
            "http://10.10.10.10:10428/metrics"
        ).decode("utf-8", errors="replace")
        alertmanager_metrics = fetch_bytes(
            "http://10.10.10.10:9059/metrics"
        ).decode("utf-8", errors="replace")
        pg_exporter_text = fetch_bytes(
            "http://10.10.10.11:9630/metrics"
        ).decode("utf-8", errors="replace")
        pgbouncer_exporter_text = fetch_bytes(
            "http://10.10.10.11:9631/metrics"
        ).decode("utf-8", errors="replace")

        tsdb = fetch_json(
            "http://10.10.10.10:8428/api/v1/status/tsdb?topN=5"
        )
        if tsdb.get("status") != "success":
            raise CaptureError("VictoriaMetrics TSDB status failed")
        tsdb_data = tsdb.get("data", {})

        metric_summaries = {
            name: query_vm(name) for name in METRIC_NAMES
        }
        freshness = {
            name: metric_freshness(name, captured_epoch)
            for name in (
                "pg_up",
                "pg_exporter_up",
                "vmalert_iteration_total",
                "alertmanager_notifications_failed_total",
            )
        }
        application_metrics = query_vm(
            'count({__name__=~"pg36_shop_.*"}) by (__name__)'
        )

        live_alertmanager = fetch_json(
            "http://10.10.10.10:9059/api/v2/alerts"
        )
        if not isinstance(live_alertmanager, list):
            raise CaptureError("Alertmanager alerts API is not a list")

        ch24_dir = args.upstream_root / "ch24"
        upstream_hashes = {
            name: sha256(ch24_dir / name)
            for name in requirements["upstream_governance"][
                "required_files"
            ]
        }
        upstream_run = read_json(ch24_dir / "governance-run.json")

        evidence = {
            "schema": "pg36-ch25-observability-evidence-v1",
            "release": requirements["release"],
            "run_id": str(uuid.uuid4()),
            "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
            "target": {
                "id": target["id"],
                "service_id": target["service_id"],
                "environment": target["environment"],
                "production_data": target["production_data"],
                "production_traffic": target["production_traffic"],
                "production_slo_claimed": target[
                    "production_slo_claimed"
                ],
            },
            "risk": "L0-live-capture",
            "mutation": "none",
            "chapter_24": {
                "run_id": upstream_run.get("run_id"),
                "production_ch24_gate": upstream_run.get(
                    "production_ch24_gate"
                ),
                "source_hashes": upstream_hashes,
            },
            "source_hashes": {
                name: sha256(args.source_dir / name)
                for name in SOURCE_NAMES
            },
            "live": {
                "versions": {
                    "pigsty": upstream_run.get(
                        "live_baseline", {}
                    ).get("pigsty_version"),
                    "postgresql": upstream_run.get(
                        "live_baseline", {}
                    ).get("postgresql_major"),
                    "VictoriaMetrics": version_from_metrics(
                        vm_metrics, "vm_app_version"
                    ),
                    "VMAlert": version_from_metrics(
                        vmalert_metrics, "vm_app_version"
                    ),
                    "VictoriaLogs": version_from_metrics(
                        vlogs_metrics, "vm_app_version"
                    ),
                    "VictoriaTraces": version_from_metrics(
                        vtraces_metrics, "vm_app_version"
                    ),
                    "Alertmanager": version_from_metrics(
                        alertmanager_metrics,
                        "alertmanager_build_info",
                    ),
                    "pg_exporter": version_from_metrics(
                        pg_exporter_text,
                        "pg_exporter_build_info",
                    ),
                },
                "health": {
                    "VictoriaMetrics": health(
                        "http://10.10.10.10:8428/health"
                    ),
                    "VictoriaLogs": health(
                        "http://10.10.10.10:9428/health"
                    ),
                    "VictoriaTraces": health(
                        "http://10.10.10.10:10428/health"
                    ),
                    "Alertmanager": health(
                        "http://10.10.10.10:9059/-/healthy"
                    ),
                },
                "victoriametrics": {
                    "total_series": tsdb_data.get("totalSeries"),
                    "total_label_value_pairs": tsdb_data.get(
                        "totalLabelValuePairs"
                    ),
                    "top_metric_series": tsdb_data.get(
                        "seriesCountByMetricName", []
                    ),
                    "top_label_cardinality": tsdb_data.get(
                        "labelValueCountByLabelName", []
                    ),
                },
                "vmalert": summarize_vmalert(),
                "alertmanager": {
                    "current_alert_count": len(live_alertmanager),
                    "alert_bodies_exported": False,
                    "configuration_exported": False,
                },
                "pg_exporter": summarize_exporter(pg_exporter_text),
                "pgbouncer_exporter": {
                    "response_bytes": len(
                        pgbouncer_exporter_text.encode("utf-8")
                    ),
                    "version": version_from_metrics(
                        pgbouncer_exporter_text,
                        "pg_exporter_build_info",
                    ),
                },
                "metric_summaries": metric_summaries,
                "metric_freshness": freshness,
                "application_metrics": application_metrics,
                "patroni": summarize_patroni(),
                "postgresql": capture_postgresql(
                    args.ssh_user,
                    target["bastion"],
                    target["database_primary"],
                ),
            },
            "claims": {
                "application_sli_metrics_exist": False,
                "chapter_rules_deployed": False,
                "live_alert_submitted": False,
                "real_notification_sent": False,
                "production_slo_measured": False,
                "dashboard_proves_root_cause": False,
                "auto_explain_overhead_reviewed": False,
                "log_group_access_reviewed": False,
                "production_ch25_approved": False,
            },
            "production_ch25_gate": "pending",
            "production_approval": False,
        }
        write_private_json(args.output, evidence)
    except (CaptureError, KeyError, OSError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1
    print(f"status=capture-ok")
    print(f"run_id={evidence['run_id']}")
    print("mutation=none")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
