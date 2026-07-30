#!/usr/bin/env python3
"""Run the bounded chapter 27 session-local parameter falsification experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import secrets
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATABASE = "pg36_tuning"
ROLE = "dbuser_pg36tune"
PRIMARY_ADDRESS = "10.10.10.11"
MARKER_PREFIX = "pg36-ch27-disposable-tuning-fixture-v1"
MODES = ("auto", "force_generic_plan")


class ExperimentError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        env=env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        safe_head = " ".join(command[:2])
        raise ExperimentError(
            f"command failed ({completed.returncode}): {safe_head}: "
            f"{completed.stderr.strip()[-2000:]}"
        )
    return completed


def admin_connection(database: str, application: str) -> str:
    return (
        f"service=pg-test-1 dbname={database} "
        f"application_name={application}"
    )


def bench_connection(application: str) -> str:
    return (
        f"host={PRIMARY_ADDRESS} port=5432 dbname={DATABASE} "
        f"user={ROLE} sslmode=disable application_name={application}"
    )


def psql(
    connection: str,
    *,
    env: dict[str, str] | None = None,
    sql: str | None = None,
    sql_file: Path | None = None,
    variables: dict[str, str | int] | None = None,
    timeout: int | None = None,
) -> str:
    command = [
        "psql",
        "-X",
        "-w",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
        "--no-psqlrc",
        "--dbname",
        connection,
    ]
    for key, value in sorted((variables or {}).items()):
        command.append(f"--set={key}={value}")
    if sql_file is not None:
        command.extend(["--file", str(sql_file)])
    else:
        command.extend(["--file", "-"])
    completed = run(
        command,
        env=env,
        input_text=sql if sql_file is None else None,
        timeout=timeout,
    )
    return completed.stdout.strip()


def parse_single_json(text: str, label: str) -> Any:
    stripped = text.strip()
    if stripped:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    lines = [line for line in text.splitlines() if line.lstrip().startswith(("{", "["))]
    if not lines:
        raise ExperimentError(f"{label} returned no JSON")
    candidate = "\n".join(lines)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise ExperimentError(f"{label} returned malformed JSON")


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ExperimentError("cannot calculate a quantile from no values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return (
        ordered[lower] * (upper - position)
        + ordered[upper] * (position - lower)
    )


def parse_pgbench_output(text: str) -> dict[str, Any]:
    patterns = {
        "processed_transactions": r"number of transactions actually processed: (\d+)",
        "failed_transactions": r"number of failed transactions: (\d+)",
        "late_transactions": (
            r"number of transactions above the [0-9.]+ ms latency limit: (\d+)/"
        ),
        "latency_average_ms": r"latency average = ([0-9.]+) ms",
        "latency_stddev_ms": r"latency stddev = ([0-9.]+) ms",
        "initial_connection_ms": r"initial connection time = ([0-9.]+) ms",
        "tps": r"tps = ([0-9.]+) \(without initial connection time\)",
    }
    result: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise ExperimentError(f"pgbench output is missing {key}")
        value = match.group(1)
        result[key] = int(value) if "transactions" in key else float(value)
    return result


def parse_transaction_logs(prefix: Path) -> dict[str, Any]:
    paths = sorted(prefix.parent.glob(prefix.name + ".*"))
    if not paths:
        raise ExperimentError(f"no transaction log for {prefix}")
    latencies: list[float] = []
    failures = 0
    skipped = 0
    script_counts = {"read-product": 0, "read-order": 0, "place-order": 0}
    script_names = {0: "read-product", 1: "read-order", 2: "place-order"}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 6:
                raise ExperimentError(f"invalid transaction log row in {path.name}")
            latency = fields[2]
            if latency == "skipped":
                skipped += 1
                continue
            if latency in {"failed", "serialization", "deadlock"}:
                failures += 1
                continue
            script_id = int(fields[3])
            if script_id not in script_names:
                raise ExperimentError(f"unknown script id {script_id}")
            latencies.append(int(latency) / 1000.0)
            script_counts[script_names[script_id]] += 1
    return {
        "files": [path.name for path in paths],
        "transactions": len(latencies),
        "failures": failures,
        "skipped": skipped,
        "script_counts": script_counts,
        "latency_ms": {
            "p50": quantile(latencies, 0.50),
            "p95": quantile(latencies, 0.95),
            "p99": quantile(latencies, 0.99),
            "max": max(latencies),
        },
        "_latencies": latencies,
    }


def settings_snapshot() -> dict[str, Any]:
    sql = r"""
\pset format unaligned
\pset tuples_only on
SELECT jsonb_build_object(
  'captured_at', clock_timestamp(),
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'in_recovery', pg_is_in_recovery(),
  'settings', (
    SELECT jsonb_agg(
      jsonb_build_object(
        'name', name,
        'setting', setting,
        'unit', unit,
        'context', context,
        'source', source,
        'sourcefile', sourcefile,
        'pending_restart', pending_restart
      )
      ORDER BY name
    )
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'shared_buffers',
      'effective_cache_size',
      'work_mem',
      'maintenance_work_mem',
      'autovacuum_work_mem',
      'max_connections',
      'max_worker_processes',
      'max_parallel_workers',
      'max_parallel_workers_per_gather',
      'synchronous_commit',
      'fsync',
      'full_page_writes',
      'wal_compression',
      'checkpoint_timeout',
      'checkpoint_completion_target',
      'max_wal_size',
      'random_page_cost',
      'effective_io_concurrency',
      'plan_cache_mode',
      'jit',
      'jit_above_cost',
      'statement_timeout',
      'lock_timeout',
      'idle_in_transaction_session_timeout'
    ])
  ),
  'file_errors', (
    SELECT coalesce(
      jsonb_agg(
        jsonb_build_object(
          'sourcefile', sourcefile,
          'sourceline', sourceline,
          'name', name,
          'error', error
        )
        ORDER BY sourcefile, sourceline
      ) FILTER (WHERE error IS NOT NULL),
      '[]'::jsonb
    )
    FROM pg_file_settings
  )
);
"""
    return parse_single_json(
        psql(admin_connection("postgres", "pg36-ch27-settings"), sql=sql),
        "settings snapshot",
    )


def database_stats() -> dict[str, Any]:
    sql = rf"""
\pset format unaligned
\pset tuples_only on
SELECT jsonb_build_object(
  'captured_at', clock_timestamp(),
  'stats_reset', stats_reset,
  'xact_commit', xact_commit,
  'xact_rollback', xact_rollback,
  'temp_bytes', temp_bytes,
  'deadlocks', deadlocks,
  'blks_read', blks_read,
  'blks_hit', blks_hit
)
FROM pg_stat_database
WHERE datname = '{DATABASE}';
"""
    return parse_single_json(
        psql(admin_connection("postgres", "pg36-ch27-stat"), sql=sql),
        "database stats",
    )


def subtract_stats(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    if before["stats_reset"] != after["stats_reset"]:
        raise ExperimentError("database statistics were reset during a run")
    keys = (
        "xact_commit",
        "xact_rollback",
        "temp_bytes",
        "deadlocks",
        "blks_read",
        "blks_hit",
    )
    delta = {key: after[key] - before[key] for key in keys}
    if any(value < 0 for value in delta.values()):
        raise ExperimentError(f"negative database statistics delta: {delta}")
    return delta


def reset_fixture(source_dir: Path, bench_env: dict[str, str], application: str) -> None:
    result = parse_single_json(
        psql(
            bench_connection(application),
            env=bench_env,
            sql_file=source_dir / "reset-run.sql",
            timeout=60,
        ),
        "fixture reset",
    )
    if result != {"inventory_rows": 16000, "live_order_rows": 0}:
        raise ExperimentError(f"fixture reset invariant failed: {result}")


def pgbench_command(
    source_dir: Path,
    application: str,
    seed: int,
    duration: int,
    log_prefix: Path | None,
) -> list[str]:
    command = [
        "pgbench",
        f"--random-seed={seed}",
        "--client=8",
        "--jobs=2",
        f"--time={duration}",
        "--protocol=prepared",
        "--no-vacuum",
        "--progress=3",
        "--progress-timestamp",
        "--report-per-command",
        "--failures-detailed",
        "--max-tries=1",
        "--latency-limit=250",
        "--scale=8",
        "--define=customer_count=80000",
        "--define=product_count=16000",
        f"--file={source_dir / 'read-product.sql'}@50",
        f"--file={source_dir / 'read-order.sql'}@30",
        f"--file={source_dir / 'place-order.sql'}@20",
    ]
    if log_prefix is not None:
        command.extend(["--log", f"--log-prefix={log_prefix}"])
    command.append(bench_connection(application))
    return command


def mode_environment(bench_env: dict[str, str], mode: str, seed: int) -> dict[str, str]:
    if mode not in MODES:
        raise ExperimentError(f"invalid experiment mode: {mode}")
    env = bench_env.copy()
    env["PGBENCH_RANDOM_SEED"] = str(seed)
    env["PGOPTIONS"] = (
        f"-c plan_cache_mode={mode} "
        "-c synchronous_commit=on "
        "-c statement_timeout=5s "
        "-c lock_timeout=1s"
    )
    return env


def warm_up(
    source_dir: Path,
    bench_env: dict[str, str],
    mode: str,
    seed: int,
) -> None:
    reset_fixture(source_dir, bench_env, f"pg36-ch27-warmup-reset-{mode}")
    env = mode_environment(bench_env, mode, seed)
    completed = run(
        pgbench_command(
            source_dir,
            f"pg36-ch27-warmup-{mode}",
            seed,
            5,
            None,
        ),
        env=env,
        timeout=40,
    )
    parsed = parse_pgbench_output(completed.stdout)
    if parsed["failed_transactions"] != 0:
        raise ExperimentError(f"warm-up failed in {mode}")


def measured_run(
    source_dir: Path,
    output_dir: Path,
    bench_env: dict[str, str],
    mode: str,
    repetition: int,
    sequence: int,
    seed: int,
) -> dict[str, Any]:
    run_id = f"r{repetition:02d}-{sequence:02d}-{mode}"
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, mode=0o700)
    reset_fixture(source_dir, bench_env, f"pg36-ch27-reset-{run_id}")
    stats_before = database_stats()
    (run_dir / "stats-before.json").write_text(
        json.dumps(stats_before, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log_prefix = run_dir / "transactions"
    application = f"pg36-ch27-{run_id}"
    env = mode_environment(bench_env, mode, seed)
    started_at = utc_now()
    started_monotonic = time.monotonic()
    completed = run(
        pgbench_command(source_dir, application, seed, 12, log_prefix),
        env=env,
        timeout=50,
        check=False,
    )
    ended_monotonic = time.monotonic()
    ended_at = utc_now()
    (run_dir / "pgbench.stdout").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "pgbench.stderr").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise ExperimentError(
            f"pgbench failed in {run_id}: {completed.stderr.strip()[-1000:]}"
        )
    pgbench = parse_pgbench_output(completed.stdout)
    logs = parse_transaction_logs(log_prefix)
    if logs["transactions"] != pgbench["processed_transactions"]:
        raise ExperimentError(f"transaction log count mismatch in {run_id}")
    if (
        pgbench["failed_transactions"] != 0
        or pgbench["late_transactions"] != 0
        or logs["failures"] != 0
        or logs["skipped"] != 0
    ):
        raise ExperimentError(f"failed, late, or skipped transaction in {run_id}")
    stats_after = database_stats()
    (run_dir / "stats-after.json").write_text(
        json.dumps(stats_after, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    delta = subtract_stats(stats_after, stats_before)
    if delta["temp_bytes"] != 0 or delta["deadlocks"] != 0:
        raise ExperimentError(f"temp or deadlock regression in {run_id}: {delta}")
    return {
        "run_id": run_id,
        "mode": mode,
        "repetition": repetition,
        "sequence": sequence,
        "seed": seed,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": ended_monotonic - started_monotonic,
        "pgbench": pgbench,
        "transactions": {
            key: value for key, value in logs.items() if key != "_latencies"
        },
        "database_delta": delta,
        "_latencies": logs["_latencies"],
    }


def plan_shape(node: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "Node Type",
        "Parent Relationship",
        "Join Type",
        "Strategy",
        "Relation Name",
        "Alias",
        "Index Name",
        "Scan Direction",
    )
    result = {key: node[key] for key in keep if key in node}
    result["Plans"] = [plan_shape(child) for child in node.get("Plans", [])]
    return result


def explain_probe(
    source_dir: Path,
    bench_env: dict[str, str],
    mode: str,
    script: str,
    value: int,
) -> dict[str, Any]:
    output = psql(
        bench_connection(f"pg36-ch27-plan-{mode}-{script}-{value}"),
        env=bench_env,
        sql_file=source_dir / f"plan-probe-{script}.sql",
        variables={"probe_mode": mode, "probe_value": value},
        timeout=20,
    )
    plan_json = parse_single_json(output, f"{mode} {script} plan")
    if not isinstance(plan_json, list) or len(plan_json) != 1:
        raise ExperimentError("EXPLAIN JSON must contain one plan")
    shape = plan_shape(plan_json[0]["Plan"])
    encoded = json.dumps(shape, sort_keys=True, separators=(",", ":")).encode()
    return {
        "script": script,
        "probe_value": value,
        "shape": shape,
        "shape_sha256": hashlib.sha256(encoded).hexdigest(),
        "settings": plan_json[0].get("Settings", {}),
    }


def plan_probes(
    source_dir: Path,
    bench_env: dict[str, str],
    mode: str,
) -> dict[str, Any]:
    counts = parse_single_json(
        psql(
            bench_connection(f"pg36-ch27-plan-counts-{mode}"),
            env=bench_env,
            sql_file=source_dir / "plan-probe-counts.sql",
            variables={"probe_mode": mode},
            timeout=30,
        ),
        f"{mode} prepared plan counts",
    )
    probes = [
        explain_probe(source_dir, bench_env, mode, "product", 1),
        explain_probe(source_dir, bench_env, mode, "product", 16000),
        explain_probe(source_dir, bench_env, mode, "order", 1),
        explain_probe(source_dir, bench_env, mode, "order", 80000),
    ]
    return {"mode": mode, "prepared_counts": counts, "probes": probes}


def bootstrap_interval(values: list[float]) -> list[float]:
    rng = random.Random(270027)
    estimates: list[float] = []
    for _ in range(10000):
        sample = [rng.choice(values) for _ in values]
        estimates.append(statistics.median(sample))
    return [quantile(estimates, 0.025), quantile(estimates, 0.975)]


def summarize(
    runs: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    settings_unchanged: bool,
) -> dict[str, Any]:
    arms: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        rows = [row for row in runs if row["mode"] == mode]
        latencies = [
            latency for row in rows for latency in row["_latencies"]
        ]
        arms[mode] = {
            "runs": len(rows),
            "transactions": sum(
                row["pgbench"]["processed_transactions"] for row in rows
            ),
            "failures": sum(
                row["pgbench"]["failed_transactions"] for row in rows
            ),
            "late_transactions": sum(
                row["pgbench"]["late_transactions"] for row in rows
            ),
            "skipped_transactions": sum(
                row["transactions"]["skipped"] for row in rows
            ),
            "tps_median": statistics.median(
                row["pgbench"]["tps"] for row in rows
            ),
            "latency_ms": {
                "p50": quantile(latencies, 0.50),
                "p95": quantile(latencies, 0.95),
                "p99": quantile(latencies, 0.99),
                "max": max(latencies),
            },
            "temp_bytes": sum(row["database_delta"]["temp_bytes"] for row in rows),
            "deadlocks": sum(row["database_delta"]["deadlocks"] for row in rows),
        }
    ratios = []
    for repetition in range(1, 6):
        baseline = next(
            row for row in runs
            if row["mode"] == "auto" and row["repetition"] == repetition
        )
        candidate = next(
            row for row in runs
            if row["mode"] == "force_generic_plan"
            and row["repetition"] == repetition
        )
        ratios.append(
            candidate["pgbench"]["tps"] / baseline["pgbench"]["tps"]
        )
    auto_fingerprints = {
        (row["script"], row["probe_value"]): row["shape_sha256"]
        for row in probes["auto"]["probes"]
    }
    candidate_fingerprints = {
        (row["script"], row["probe_value"]): row["shape_sha256"]
        for row in probes["force_generic_plan"]["probes"]
    }
    shapes_equal = auto_fingerprints == candidate_fingerprints
    ratio_ci = bootstrap_interval(ratios)
    p95_ratio = (
        arms["force_generic_plan"]["latency_ms"]["p95"]
        / arms["auto"]["latency_ms"]["p95"]
    )
    rules = {
        "all_runs_successful": all(
            arms[mode]["failures"] == 0
            and arms[mode]["late_transactions"] == 0
            and arms[mode]["skipped_transactions"] == 0
            for mode in MODES
        ),
        "plan_shapes_equal_for_probes": shapes_equal,
        "global_settings_unchanged": settings_unchanged,
        "candidate_p95_ratio_at_most_1_05": p95_ratio <= 1.05,
        "paired_tps_ratio_bootstrap_lower_at_least_1_02": ratio_ci[0] >= 1.02,
    }
    accepted = all(rules.values())
    return {
        "arms": arms,
        "paired_tps_ratios": ratios,
        "paired_tps_ratio_median": statistics.median(ratios),
        "paired_tps_ratio_bootstrap_95": ratio_ci,
        "candidate_p95_ratio": p95_ratio,
        "plan_shapes_equal_for_probes": shapes_equal,
        "acceptance_rules": rules,
        "decision": (
            "candidate-worthy-for-larger-canary"
            if accepted
            else "reject-persistent-change"
        ),
        "decision_reason": (
            "all predeclared material-benefit and non-regression rules passed"
            if accepted
            else "one or more predeclared material-benefit or non-regression rules failed"
        ),
        "production_ch27_gate": "pending",
    }


def create_fixture(
    run_id: str,
    password: str,
    source_dir: Path,
    bench_env: dict[str, str],
) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    create_sql = rf"""
\set ON_ERROR_STOP on
CREATE ROLE {ROLE}
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  INHERIT
  PASSWORD :'bench_password';
GRANT dbrole_readwrite TO {ROLE} WITH INHERIT FALSE, SET FALSE;
COMMENT ON ROLE {ROLE} IS '{marker}';
CREATE DATABASE {DATABASE}
  OWNER {ROLE}
  TEMPLATE template0
  ENCODING 'UTF8'
  ALLOW_CONNECTIONS false;
REVOKE CONNECT ON DATABASE {DATABASE} FROM PUBLIC;
GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE};
ALTER DATABASE {DATABASE} ALLOW_CONNECTIONS true;
COMMENT ON DATABASE {DATABASE} IS '{marker}';
"""
    psql(
        admin_connection("postgres", "pg36-ch27-create"),
        sql=create_sql,
        variables={"bench_password": password},
        timeout=60,
    )
    initialized = parse_single_json(
        psql(
            bench_connection("pg36-ch27-setup"),
            env=bench_env,
            sql_file=source_dir / "setup.sql",
            timeout=240,
        ),
        "fixture setup",
    )
    if (
        initialized.get("scale_factor") != 8
        or initialized.get("customers") != 80000
        or initialized.get("products") != 16000
        or initialized.get("historical_orders") != 800000
    ):
        raise ExperimentError(f"fixture initialization mismatch: {initialized}")
    return {"marker": marker, "initialized": initialized}


def cleanup_fixture(run_id: str) -> dict[str, Any]:
    marker = f"{MARKER_PREFIX}:{run_id}"
    inspect_sql = rf"""
\pset format unaligned
\pset tuples_only on
SELECT jsonb_build_object(
  'database_exists', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'role_exists', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'
  ),
  'role_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles WHERE rolname = '{ROLE}'
  ),
  'sessions', (
    SELECT coalesce(
      jsonb_agg(
        jsonb_build_object(
          'backend_type', backend_type,
          'usename', usename,
          'application_name', application_name,
          'state', state
        )
        ORDER BY pid
      ),
      '[]'::jsonb
    )
    FROM pg_stat_activity WHERE datname = '{DATABASE}'
  )
);
"""
    observed: dict[str, Any] | None = None
    for _ in range(31):
        observed = parse_single_json(
            psql(
                admin_connection("postgres", "pg36-ch27-cleanup-check"),
                sql=inspect_sql,
            ),
            "cleanup marker inspection",
        )
        sessions = observed.get("sessions", [])
        if not sessions:
            break
        if not all(
            row.get("backend_type") == "autovacuum worker"
            for row in sessions
        ):
            raise ExperimentError(
                f"cleanup refused due to non-autovacuum session: {observed}"
            )
        time.sleep(1)
    assert observed is not None
    database_exists = observed.get("database_exists") is True
    role_exists = observed.get("role_exists") is True
    if (
        (database_exists and observed.get("database_marker") != marker)
        or (role_exists and observed.get("role_marker") != marker)
        or observed.get("sessions") != []
    ):
        raise ExperimentError(f"cleanup refused due to marker/session state: {observed}")
    cleanup_lines = [r"\set ON_ERROR_STOP on"]
    if database_exists:
        cleanup_lines.append(f"DROP DATABASE {DATABASE};")
    if role_exists:
        cleanup_lines.append(f"DROP ROLE {ROLE};")
    cleanup_sql = "\n".join(cleanup_lines) + "\n"
    if database_exists or role_exists:
        psql(
            admin_connection("postgres", "pg36-ch27-cleanup"),
            sql=cleanup_sql,
            timeout=60,
        )
    verify_sql = rf"""
\pset format unaligned
\pset tuples_only on
SELECT jsonb_build_object(
  'database_absent', NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'role_absent', NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'
  )
);
"""
    result = parse_single_json(
        psql(admin_connection("postgres", "pg36-ch27-cleanup-verify"), sql=verify_sql),
        "cleanup verification",
    )
    if result != {"database_absent": True, "role_absent": True}:
        raise ExperimentError(f"cleanup verification failed: {result}")
    return {
        **result,
        "marker_matched": database_exists or role_exists,
        "unrelated_sessions_terminated": 0,
        "drop_with_force_used": False,
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ExperimentError(f"refusing to overwrite {output_dir}")
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    run_id = str(uuid.uuid4())
    password = secrets.token_urlsafe(32)
    bench_env = os.environ.copy()
    bench_env["PGPASSWORD"] = password
    bench_env["PGCONNECT_TIMEOUT"] = "5"
    settings_before = settings_snapshot()
    if (
        settings_before.get("cluster_name") != "pg-test"
        or settings_before.get("in_recovery") is not False
        or settings_before.get("file_errors") != []
    ):
        raise ExperimentError(f"target settings precondition failed: {settings_before}")
    fixture_attempted = False
    cleanup: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    try:
        fixture_attempted = True
        fixture = create_fixture(run_id, password, source_dir, bench_env)
        probes = {
            mode: plan_probes(source_dir, bench_env, mode)
            for mode in MODES
        }
        warm_up(source_dir, bench_env, "auto", 270001)
        warm_up(source_dir, bench_env, "force_generic_plan", 270002)
        runs: list[dict[str, Any]] = []
        sequence = 0
        for repetition in range(1, 6):
            order = (
                MODES
                if repetition % 2 == 1
                else tuple(reversed(MODES))
            )
            seed = 270100 + repetition
            for mode in order:
                sequence += 1
                row = measured_run(
                    source_dir,
                    output_dir,
                    bench_env,
                    mode,
                    repetition,
                    sequence,
                    seed,
                )
                print(
                    f"run={row['run_id']} "
                    f"tps={row['pgbench']['tps']:.3f} "
                    f"p95={row['transactions']['latency_ms']['p95']:.3f}",
                    flush=True,
                )
                runs.append(row)
        settings_after = settings_snapshot()
        normalized_before = {
            "settings": settings_before["settings"],
            "file_errors": settings_before["file_errors"],
        }
        normalized_after = {
            "settings": settings_after["settings"],
            "file_errors": settings_after["file_errors"],
        }
        settings_unchanged = normalized_before == normalized_after
        summary = summarize(runs, probes, settings_unchanged)
        evidence = {
            "schema": "pg36-ch27-tuning-evidence-v1",
            "captured_at": utc_now(),
            "run_id": run_id,
            "target": "pg36-l2-vagrant/pg-test",
            "risk": "L2-bounded-session-local-parameter-experiment",
            "status": "exercise-complete-pending-cleanup",
            "fixture": fixture,
            "parameter": {
                "name": "plan_cache_mode",
                "baseline": "auto",
                "candidate": "force_generic_plan",
                "scope": "benchmark-session-only",
                "persistent_configuration_change": False,
            },
            "settings_before": settings_before,
            "settings_after": settings_after,
            "global_settings_unchanged": settings_unchanged,
            "plan_probes": probes,
            "runs": [
                {key: value for key, value in row.items() if key != "_latencies"}
                for row in runs
            ],
            "summary": summary,
            "production_ch27_gate": "pending",
        }
    finally:
        if fixture_attempted:
            cleanup = cleanup_fixture(run_id)
    if evidence is None or cleanup is None:
        raise ExperimentError("experiment did not produce evidence and cleanup")
    evidence["cleanup"] = cleanup
    evidence["status"] = "passed"
    evidence_path = output_dir / "tuning-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for path in output_dir.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run_id,
                "decision": evidence["summary"]["decision"],
                "database_absent": True,
                "role_absent": True,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ExperimentError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"chapter 27 experiment failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
