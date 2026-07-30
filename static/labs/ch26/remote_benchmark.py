#!/usr/bin/env python3
"""Run the bounded chapter 26 benchmark from the Pigsty meta node."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


os.umask(0o077)


DATABASE = "pg36_capacity"
BENCH_ROLE = "dbuser_pg36bench"
DATABASE_MARKER = "pg36-ch26-disposable-capacity-fixture-v1"
ROLE_MARKER = "pg36-ch26-disposable-capacity-role-v1"
ADMIN_SERVICE = "pg-test-1"
PRIMARY_ADDRESS = "10.10.10.11"
PRIMARY_HOST = "pg-test-1"
CLIENT_HOST = "pg-meta-1"
SOURCE_NAMES = [
    "requirements.json",
    "workload-contract.json",
    "experiment-matrix.json",
    "capacity-model.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "reset-cell.sql",
    "read-product.sql",
    "read-order.sql",
    "place-order.sql",
    "stat-snapshot.sql",
    "wait-sampler.sql",
    "system_sampler.py",
    "remote_benchmark.py",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
]


class BenchmarkError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        safe_command = " ".join(command[:2])
        raise BenchmarkError(
            f"command failed ({completed.returncode}): {safe_command}: "
            f"{completed.stderr.strip()[-2000:]}"
        )
    return completed


def admin_connection(database: str = "postgres", application: str = "admin") -> str:
    return (
        f"service={ADMIN_SERVICE} dbname={database} "
        f"application_name=pg36-ch26-{application}"
    )


def bench_connection(application: str) -> str:
    return (
        f"host={PRIMARY_ADDRESS} port=5432 dbname={DATABASE} user={BENCH_ROLE} "
        f"application_name={application}"
    )


def psql(
    connection: str,
    *,
    sql: str | None = None,
    sql_file: Path | None = None,
    variables: dict[str, str | int] | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "psql",
        "-X",
        "-w",
        "--set=ON_ERROR_STOP=1",
        "--no-psqlrc",
        f"--dbname={connection}",
    ]
    for name, value in sorted((variables or {}).items()):
        command.append(f"--set={name}={value}")
    if sql_file is not None:
        command.append(f"--file={sql_file}")
    elif sql is not None:
        command.append("--file=-")
    else:
        raise ValueError("sql or sql_file is required")
    return run(command, env=env, input_text=sql, timeout=timeout)


def psql_scalar(
    connection: str,
    sql: str,
    *,
    env: dict[str, str] | None = None,
) -> str:
    completed = run(
        [
            "psql",
            "-X",
            "-w",
            "--set=ON_ERROR_STOP=1",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            f"--dbname={connection}",
            "--file=-",
        ],
        env=env,
        input_text=sql,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BenchmarkError(f"expected one psql row, got {len(lines)}")
    return lines[0]


def psql_json(
    connection: str,
    *,
    sql: str | None = None,
    sql_file: Path | None = None,
    variables: dict[str, str | int] | None = None,
    env: dict[str, str] | None = None,
) -> Any:
    completed = psql(
        connection,
        sql=sql,
        sql_file=sql_file,
        variables=variables,
        env=env,
    )
    json_lines = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.lstrip().startswith(("{", "["))
    ]
    if len(json_lines) != 1:
        raise BenchmarkError(
            f"expected one JSON line from psql, got {len(json_lines)}"
        )
    try:
        return json.loads(json_lines[0])
    except json.JSONDecodeError as exc:
        raise BenchmarkError(f"invalid JSON from psql: {exc}") from exc


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def median(values: Iterable[float | int | None]) -> float | None:
    finite = [
        float(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    ]
    return statistics.median(finite) if finite else None


def bootstrap_median_interval(
    values: list[float],
    *,
    seed: int,
    samples: int = 10000,
) -> dict[str, float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(statistics.median(draw))
    return {
        "estimate": statistics.median(values),
        "low_95": float(quantile(estimates, 0.025)),
        "high_95": float(quantile(estimates, 0.975)),
        "method": "deterministic percentile bootstrap of run medians",
        "bootstrap_samples": samples,
        "run_count": len(values),
    }


def marker_state() -> dict[str, Any]:
    sql = f"""
SELECT jsonb_build_object(
  'database_exists', EXISTS (
    SELECT 1 FROM pg_database WHERE datname = '{DATABASE}'
  ),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database
    WHERE datname = '{DATABASE}'
  ),
  'role_exists', EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = '{BENCH_ROLE}'
  ),
  'role_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles
    WHERE rolname = '{BENCH_ROLE}'
  ),
  'database_sessions', (
    SELECT count(*)
    FROM pg_stat_activity
    WHERE datname = '{DATABASE}'
      AND pid <> pg_backend_pid()
  )
);
"""
    return psql_json(admin_connection(), sql=sql)


def assert_clean_start() -> None:
    state = marker_state()
    if state["database_exists"] or state["role_exists"]:
        raise BenchmarkError(
            "chapter 26 refuses an existing database or role; "
            f"database_marker={state.get('database_marker')!r}, "
            f"role_marker={state.get('role_marker')!r}"
        )


def create_fixture(password: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{48}", password):
        raise BenchmarkError("internal password format guard failed")
    role_sql = f"""
CREATE ROLE {BENCH_ROLE}
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOINHERIT
  NOREPLICATION
  NOBYPASSRLS
  CONNECTION LIMIT 32
  PASSWORD '{password}';
COMMENT ON ROLE {BENCH_ROLE} IS '{ROLE_MARKER}';
GRANT dbrole_readwrite TO {BENCH_ROLE} WITH INHERIT FALSE;
GRANT dbrole_readwrite TO {BENCH_ROLE} WITH SET FALSE;
"""
    psql(admin_connection(), sql=role_sql)
    database_sql = f"""
CREATE DATABASE {DATABASE}
  WITH OWNER {BENCH_ROLE}
       TEMPLATE template0
       ENCODING 'UTF8'
       LC_COLLATE 'C.UTF-8'
       LC_CTYPE 'C.UTF-8';
COMMENT ON DATABASE {DATABASE} IS '{DATABASE_MARKER}';
REVOKE ALL ON DATABASE {DATABASE} FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE {DATABASE} TO {BENCH_ROLE};
"""
    psql(admin_connection(), sql=database_sql)
    psql(
        admin_connection(DATABASE, "extension-setup"),
        sql=f"""
CREATE SCHEMA monitor;
REVOKE ALL ON SCHEMA monitor FROM PUBLIC;
CREATE EXTENSION pg_stat_statements SCHEMA monitor;
GRANT USAGE ON SCHEMA monitor TO {BENCH_ROLE};
GRANT SELECT ON monitor.pg_stat_statements TO {BENCH_ROLE};
""",
    )


def cleanup_fixture() -> dict[str, Any]:
    state = marker_state()
    if not state["database_exists"] and not state["role_exists"]:
        return {"status": "already-absent", "database_absent": True, "role_absent": True}
    if state["database_exists"] and state.get("database_marker") != DATABASE_MARKER:
        raise BenchmarkError("cleanup refused: database marker mismatch")
    if state["role_exists"] and state.get("role_marker") != ROLE_MARKER:
        raise BenchmarkError("cleanup refused: role marker mismatch")
    if state.get("database_sessions", 0) != 0:
        sessions = psql_json(
            admin_connection(),
            sql=f"""
SELECT jsonb_agg(jsonb_build_object(
  'application_name', application_name,
  'user', usename,
  'state', state
))
FROM pg_stat_activity
WHERE datname = '{DATABASE}'
  AND pid <> pg_backend_pid();
""",
        )
        raise BenchmarkError(
            f"cleanup refused: database has sessions: {sessions!r}"
        )
    if state["database_exists"]:
        psql(admin_connection(), sql=f"DROP DATABASE {DATABASE};")
    if state["role_exists"]:
        psql(admin_connection(), sql=f"DROP ROLE {BENCH_ROLE};")
    after = marker_state()
    if after["database_exists"] or after["role_exists"]:
        raise BenchmarkError("cleanup verification failed")
    return {
        "status": "removed-exact-marker-bound-fixture",
        "database_absent": True,
        "role_absent": True,
        "terminated_sessions": 0,
    }


def capture_environment() -> dict[str, Any]:
    client_hostname = run(["hostname"]).stdout.strip()
    server_hostname = run(
        ["ssh", "-o", "BatchMode=yes", f"vagrant@{PRIMARY_ADDRESS}", "hostname"]
    ).stdout.strip()
    if client_hostname != CLIENT_HOST or server_hostname != PRIMARY_HOST:
        raise BenchmarkError(
            f"host identity mismatch: client={client_hostname}, "
            f"server={server_hostname}"
        )
    postgres = psql_json(
        admin_connection(),
        sql="""
SELECT jsonb_build_object(
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'in_recovery', pg_is_in_recovery(),
  'server_address', inet_server_addr(),
  'server_port', inet_server_port(),
  'replica_count', (
    SELECT count(*) FROM pg_stat_replication WHERE state = 'streaming'
  ),
  'settings', (
    SELECT jsonb_object_agg(name, setting ORDER BY name)
    FROM pg_settings
    WHERE name = ANY (ARRAY[
      'block_size','shared_buffers','effective_cache_size','work_mem',
      'maintenance_work_mem','max_connections','max_worker_processes',
      'max_parallel_workers','max_parallel_workers_per_gather',
      'random_page_cost','effective_io_concurrency','io_method','io_workers',
      'synchronous_commit','full_page_writes','fsync','data_checksums',
      'wal_compression','max_wal_size','checkpoint_timeout',
      'track_io_timing','track_wal_io_timing','stats_fetch_consistency'
    ])
  )
);
""",
    )
    if (
        postgres.get("cluster_name") != "pg-test"
        or postgres.get("in_recovery") is not False
        or postgres.get("server_address") != PRIMARY_ADDRESS
        or postgres.get("replica_count") != 2
    ):
        raise BenchmarkError(f"PostgreSQL target identity failed: {postgres!r}")
    resource_script = r"""
import json, os
from pathlib import Path
mem = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, _, rest = line.partition(':')
    if key in {'MemTotal','MemAvailable','SwapTotal'}:
        mem[key] = int(rest.strip().split()[0]) * 1024
vfs = os.statvfs('/')
print(json.dumps({
  'cpu_count': os.cpu_count(),
  'memory_bytes': mem,
  'root_bytes': {
    'total': vfs.f_frsize * vfs.f_blocks,
    'available': vfs.f_frsize * vfs.f_bavail
  },
  'kernel': Path('/proc/sys/kernel/osrelease').read_text().strip()
}, separators=(',', ':')))
"""
    client_resources = json.loads(run(["python3", "-c", resource_script]).stdout)
    server_resources = json.loads(
        run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                f"vagrant@{PRIMARY_ADDRESS}",
                "python3",
                "-",
            ],
            input_text=resource_script,
        ).stdout
    )
    return {
        "captured_at": utc_now(),
        "client": {
            "hostname": client_hostname,
            "address": "10.10.10.10",
            "pgbench_version": run(["pgbench", "--version"]).stdout.strip(),
            "psql_version": run(["psql", "--version"]).stdout.strip(),
            "resources": client_resources,
        },
        "server": {
            "hostname": server_hostname,
            "address": PRIMARY_ADDRESS,
            "resources": server_resources,
            "postgresql": postgres,
        },
        "connection_path": {
            "mode": "direct-primary",
            "port": 5432,
            "haproxy_measured": False,
            "pgbouncer_measured": False,
            "client_and_server_are_distinct_hosts": True,
        },
    }


def create_pgpass(output_dir: Path, password: str) -> tuple[Path, dict[str, str]]:
    path = output_dir.parent / f".pg36-ch26-pgpass.{uuid.uuid4().hex}"
    admin_pgpass = Path.home() / ".pgpass"
    existing = admin_pgpass.read_text(encoding="utf-8")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(
        existing
        + f"{PRIMARY_ADDRESS}:5432:*:{BENCH_ROLE}:{password}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    env = os.environ.copy()
    env["PGSERVICEFILE"] = str(Path.home() / ".pg_service.conf")
    env["PGPASSFILE"] = str(path)
    return path, env


def initialize_scale(
    source_dir: Path,
    output_dir: Path,
    bench_env: dict[str, str],
    scale: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    completed = psql(
        bench_connection(f"pg36-ch26-setup-{scale['id']}"),
        sql_file=source_dir / "setup.sql",
        variables={"scale_factor": scale["factor"]},
        env=bench_env,
        timeout=600,
    )
    path = output_dir / f"initialize-{scale['id']}.txt"
    path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    path.chmod(0o600)
    json_lines = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.lstrip().startswith("{")
    ]
    if len(json_lines) != 1:
        raise BenchmarkError(f"scale {scale['id']} setup did not emit one JSON row")
    initialized = json.loads(json_lines[0])
    expected = {
        "customers": scale["customers"],
        "products": scale["products"],
        "historical_orders": scale["historical_orders"],
    }
    for key, value in expected.items():
        if initialized.get(key) != value:
            raise BenchmarkError(
                f"scale {scale['id']} {key}={initialized.get(key)}, expected {value}"
            )
    initialized["scale_id"] = scale["id"]
    initialized["elapsed_seconds"] = time.monotonic() - started
    return initialized


def reset_cell(
    source_dir: Path,
    bench_env: dict[str, str],
    application: str,
) -> None:
    result = psql_json(
        bench_connection(application),
        sql_file=source_dir / "reset-cell.sql",
        env=bench_env,
    )
    if result.get("live_order_rows") != 0 or result.get("inventory_rows", 0) <= 0:
        raise BenchmarkError(
            "cell reset did not prove live_order_rows=0: "
            f"{result!r}"
        )


def pgbench_command(
    source_dir: Path,
    bench_env: dict[str, str],
    *,
    application: str,
    scale: dict[str, Any],
    clients: int,
    duration: int,
    seed: int,
    log_prefix: Path | None,
) -> tuple[list[str], dict[str, str]]:
    jobs = 1 if clients == 1 else 2
    command = [
        "pgbench",
        f"--random-seed={seed}",
        f"--client={clients}",
        f"--jobs={jobs}",
        f"--time={duration}",
        "--protocol=prepared",
        "--no-vacuum",
        "--progress=2",
        "--progress-timestamp",
        "--report-per-command",
        "--failures-detailed",
        "--max-tries=1",
        "--latency-limit=250",
        f"--scale={scale['factor']}",
        f"--define=customer_count={scale['customers']}",
        f"--define=product_count={scale['products']}",
        f"--file={source_dir / 'read-product.sql'}@50",
        f"--file={source_dir / 'read-order.sql'}@30",
        f"--file={source_dir / 'place-order.sql'}@20",
    ]
    if log_prefix is not None:
        command.extend(["--log", f"--log-prefix={log_prefix}"])
    command.append(bench_connection(application))
    env = bench_env.copy()
    env["PGBENCH_RANDOM_SEED"] = str(seed)
    return command, env


def warm_up(
    source_dir: Path,
    bench_env: dict[str, str],
    scale: dict[str, Any],
    clients: int,
    duration: int,
    seed: int,
) -> dict[str, Any]:
    reset_cell(
        source_dir,
        bench_env,
        f"pg36-ch26-warmup-reset-{scale['id']}-c{clients}",
    )
    application = f"pg36-ch26-warmup-{scale['id']}-c{clients}"
    command, env = pgbench_command(
        source_dir,
        bench_env,
        application=application,
        scale=scale,
        clients=clients,
        duration=duration,
        seed=seed,
        log_prefix=None,
    )
    completed = run(command, env=env, timeout=duration + 30)
    if completed.returncode != 0 or "number of failed transactions: 0 " not in completed.stdout:
        raise BenchmarkError(
            f"warmup failed for {scale['id']}-c{clients}: "
            f"{completed.stdout[-1000:]} {completed.stderr[-1000:]}"
        )
    return {
        "scale_id": scale["id"],
        "clients": clients,
        "seconds": duration,
        "seed": seed,
        "status": "passed",
    }


def start_samplers(
    source_dir: Path,
    run_dir: Path,
    bench_env: dict[str, str],
    application: str,
    duration: float,
    remote_sampler: str,
) -> list[tuple[str, subprocess.Popen[str], Any]]:
    handles: list[tuple[str, subprocess.Popen[str], Any]] = []
    client_file = (run_dir / "client-system.jsonl").open("w", encoding="utf-8")
    client_process = subprocess.Popen(
        [
            "python3",
            str(source_dir / "system_sampler.py"),
            "--duration",
            str(duration),
            "--interval",
            "0.25",
        ],
        stdout=client_file,
        stderr=subprocess.PIPE,
        text=True,
    )
    handles.append(("client-system", client_process, client_file))

    server_file = (run_dir / "server-system.jsonl").open("w", encoding="utf-8")
    server_process = subprocess.Popen(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            f"vagrant@{PRIMARY_ADDRESS}",
            "python3",
            remote_sampler,
            "--duration",
            str(duration),
            "--interval",
            "0.25",
        ],
        stdout=server_file,
        stderr=subprocess.PIPE,
        text=True,
    )
    handles.append(("server-system", server_process, server_file))

    wait_file = (run_dir / "database-waits.jsonl").open("w", encoding="utf-8")
    wait_command = [
        "psql",
        "-X",
        "-w",
        "--set=ON_ERROR_STOP=1",
        "--no-psqlrc",
        f"--set=bench_application={application}",
        f"--dbname={admin_connection(DATABASE, 'wait-sampler')}",
        f"--file={source_dir / 'wait-sampler.sql'}",
    ]
    wait_process = subprocess.Popen(
        wait_command,
        stdout=wait_file,
        stderr=subprocess.PIPE,
        text=True,
        env=bench_env,
    )
    handles.append(("database-waits", wait_process, wait_file))
    return handles


def stop_samplers(
    handles: list[tuple[str, subprocess.Popen[str], Any]],
    *,
    wait_for_system: bool,
) -> None:
    for name, process, _ in handles:
        if name == "database-waits" and process.poll() is None:
            process.terminate()
    for name, process, file_handle in handles:
        try:
            timeout = 5 if name == "database-waits" or not wait_for_system else 20
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(timeout=5)
        finally:
            file_handle.close()
        if name != "database-waits" and process.returncode != 0:
            raise BenchmarkError(
                f"{name} sampler failed ({process.returncode}): "
                f"{(stderr or '').strip()[-1000:]}"
            )
        if name == "database-waits" and process.returncode not in (0, -15):
            raise BenchmarkError(
                f"wait sampler failed ({process.returncode}): "
                f"{(stderr or '').strip()[-1000:]}"
            )


def parse_pgbench_output(text: str) -> dict[str, Any]:
    patterns = {
        "processed_transactions": r"number of transactions actually processed: (\d+)",
        "failed_transactions": r"number of failed transactions: (\d+)",
        "late_transactions": r"number of transactions above the [0-9.]+ ms latency limit: (\d+)/",
        "latency_average_ms": r"latency average = ([0-9.]+) ms",
        "latency_stddev_ms": r"latency stddev = ([0-9.]+) ms",
        "initial_connection_ms": r"initial connection time = ([0-9.]+) ms",
        "tps": r"tps = ([0-9.]+) \(without initial connection time\)",
    }
    result: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise BenchmarkError(f"pgbench output is missing {key}")
        value = match.group(1)
        result[key] = int(value) if "transactions" in key else float(value)
    return result


def parse_transaction_logs(prefix: Path) -> dict[str, Any]:
    paths = sorted(prefix.parent.glob(prefix.name + ".*"))
    if not paths:
        raise BenchmarkError(f"no pgbench transaction log for {prefix}")
    latencies: list[float] = []
    script_counts: Counter[int] = Counter()
    failures = 0
    skipped = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 6:
                raise BenchmarkError(f"invalid pgbench log row in {path.name}")
            latency = fields[2]
            script_no = int(fields[3])
            if latency == "skipped":
                skipped += 1
                continue
            if latency in {"failed", "serialization", "deadlock"}:
                failures += 1
                continue
            latencies.append(int(latency) / 1000.0)
            script_counts[script_no] += 1
    mapping = {0: "read-product", 1: "read-order", 2: "place-order"}
    return {
        "log_files": [path.name for path in paths],
        "transactions": len(latencies),
        "failures": failures,
        "skipped": skipped,
        "latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else None,
            "p50": quantile(latencies, 0.50),
            "p95": quantile(latencies, 0.95),
            "p99": quantile(latencies, 0.99),
            "max": max(latencies) if latencies else None,
        },
        "script_counts": {
            mapping.get(script_no, f"unknown-{script_no}"): count
            for script_no, count in sorted(script_counts.items())
        },
        "_latencies": latencies,
    }


def parse_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def parse_system_samples(
    path: Path,
    *,
    measured_start_epoch: float,
    measured_end_epoch: float,
) -> dict[str, Any]:
    all_rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [
        row
        for row in all_rows
        if measured_start_epoch
        <= parse_timestamp(row["captured_at"])
        <= measured_end_epoch
    ]
    if len(rows) < 2:
        raise BenchmarkError(f"not enough system samples in {path}")
    busy_values: list[float] = []
    work_values: list[float] = []
    iowait_values: list[float] = []
    for before, after in zip(rows, rows[1:]):
        delta = {
            key: after["cpu"].get(key, 0) - before["cpu"].get(key, 0)
            for key in after["cpu"]
        }
        total = sum(
            value
            for key, value in delta.items()
            if key not in {"guest", "guest_nice"}
        )
        if total <= 0:
            continue
        idle = delta.get("idle", 0)
        iowait = delta.get("iowait", 0)
        busy_values.append((total - idle) / total)
        work_values.append((total - idle - iowait) / total)
        iowait_values.append(iowait / total)
    disk_first = rows[0]["root_device"].get("counters")
    disk_last = rows[-1]["root_device"].get("counters")
    disk_delta = None
    if disk_first and disk_last:
        disk_delta = {
            "read_bytes": (
                disk_last["sectors_read"] - disk_first["sectors_read"]
            )
            * 512,
            "write_bytes": (
                disk_last["sectors_written"] - disk_first["sectors_written"]
            )
            * 512,
            "io_ms": disk_last["io_ms"] - disk_first["io_ms"],
            "weighted_io_ms": (
                disk_last["weighted_io_ms"] - disk_first["weighted_io_ms"]
            ),
        }
    return {
        "scope": "samples inside the measured pgbench start/end window",
        "raw_sample_count": len(all_rows),
        "sample_count": len(rows),
        "sample_seconds": rows[-1]["monotonic_seconds"]
        - rows[0]["monotonic_seconds"],
        "cpu": {
            "busy_ratio_mean": statistics.fmean(busy_values),
            "busy_ratio_p95": quantile(busy_values, 0.95),
            "work_ratio_mean": statistics.fmean(work_values),
            "iowait_ratio_mean": statistics.fmean(iowait_values),
        },
        "memory": {
            "available_bytes_min": min(
                row["memory_bytes"]["MemAvailable"] for row in rows
            ),
            "dirty_bytes_max": max(
                row["memory_bytes"].get("Dirty", 0) for row in rows
            ),
        },
        "load": {
            "one_mean": statistics.fmean(row["load"]["one"] for row in rows),
            "one_max": max(row["load"]["one"] for row in rows),
        },
        "root_device_delta": disk_delta,
    }


def parse_wait_samples(path: Path) -> dict[str, Any]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            rows.append(json.loads(stripped))
    if not rows:
        raise BenchmarkError(f"no database wait samples in {path}")
    by_type: Counter[str] = Counter()
    by_event: Counter[str] = Counter()
    total = 0
    active = 0
    for row in rows:
        for session in row.get("sessions", []):
            count = int(session["count"])
            wait_type = session["wait_event_type"]
            wait_event = session["wait_event"]
            by_type[wait_type] += count
            by_event[f"{wait_type}/{wait_event}"] += count
            total += count
            if session["state"] == "active":
                active += count
    return {
        "sample_count": len(rows),
        "session_samples": total,
        "active_session_samples": active,
        "by_wait_type": dict(by_type.most_common()),
        "top_wait_events": dict(by_event.most_common(12)),
    }


def numeric_delta(after: Any, before: Any) -> Any:
    if isinstance(after, bool) or isinstance(before, bool):
        return None
    if isinstance(after, (int, float)) and isinstance(before, (int, float)):
        return after - before
    return None


def dict_numeric_delta(
    after: dict[str, Any],
    before: dict[str, Any],
    *,
    excluded: set[str] | None = None,
) -> dict[str, Any]:
    excluded = excluded or set()
    result: dict[str, Any] = {}
    for key in sorted(set(after) & set(before)):
        if key in excluded:
            continue
        delta = numeric_delta(after[key], before[key])
        if delta is not None:
            result[key] = delta
    return result


def stat_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    reset_paths = {
        "database": before["database"].get("stats_reset")
        == after["database"].get("stats_reset"),
        "wal": before["wal"].get("stats_reset")
        == after["wal"].get("stats_reset"),
        "checkpointer": before["checkpointer"].get("stats_reset")
        == after["checkpointer"].get("stats_reset"),
        "bgwriter": before["bgwriter"].get("stats_reset")
        == after["bgwriter"].get("stats_reset"),
        "io": {
            (
                row["backend_type"],
                row["object"],
                row["context"],
            ): row.get("stats_reset")
            for row in before["io"]
        }
        == {
            (
                row["backend_type"],
                row["object"],
                row["context"],
            ): row.get("stats_reset")
            for row in after["io"]
        },
    }
    if not all(reset_paths.values()):
        raise BenchmarkError(f"statistics reset changed during run: {reset_paths}")
    before_io = {
        (row["backend_type"], row["object"], row["context"]): row
        for row in before["io"]
    }
    after_io = {
        (row["backend_type"], row["object"], row["context"]): row
        for row in after["io"]
    }
    io_delta = []
    for key in sorted(set(before_io) & set(after_io)):
        delta = dict_numeric_delta(
            after_io[key],
            before_io[key],
            excluded={"stats_reset"},
        )
        if any(value != 0 for value in delta.values()):
            io_delta.append(
                {
                    "backend_type": key[0],
                    "object": key[1],
                    "context": key[2],
                    "delta": delta,
                }
            )
    before_statements = {
        str(row["queryid"]): row
        for row in before["statements"].get("rows", [])
    }
    after_statements = {
        str(row["queryid"]): row
        for row in after["statements"].get("rows", [])
    }
    statement_delta = []
    for queryid in sorted(set(before_statements) & set(after_statements)):
        delta = dict_numeric_delta(
            after_statements[queryid],
            before_statements[queryid],
            excluded={"queryid"},
        )
        if delta.get("calls", 0) > 0:
            statement_delta.append({"queryid": queryid, "delta": delta})
    new_queryids = sorted(set(after_statements) - set(before_statements))
    for queryid in new_queryids:
        row = after_statements[queryid]
        delta = {
            key: value
            for key, value in row.items()
            if key not in {"queryid", "stats_since"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        }
        if delta.get("calls", 0) > 0:
            statement_delta.append({"queryid": queryid, "delta": delta})
    return {
        "stats_reset_unchanged": reset_paths,
        "database": dict_numeric_delta(
            after["database"],
            before["database"],
            excluded={"stats_reset"},
        ),
        "wal": dict_numeric_delta(
            after["wal"],
            before["wal"],
            excluded={"stats_reset"},
        ),
        "checkpointer": dict_numeric_delta(
            after["checkpointer"],
            before["checkpointer"],
            excluded={"stats_reset"},
        ),
        "bgwriter": dict_numeric_delta(
            after["bgwriter"],
            before["bgwriter"],
            excluded={"stats_reset"},
        ),
        "io": io_delta,
        "statements": {
            "query_text_exported": False,
            "rows": statement_delta,
        },
        "relations": dict_numeric_delta(after["relations"], before["relations"]),
    }


def run_measured(
    source_dir: Path,
    output_dir: Path,
    bench_env: dict[str, str],
    scale: dict[str, Any],
    clients: int,
    repetition: int,
    duration: int,
    seed: int,
    remote_sampler: str,
) -> dict[str, Any]:
    run_id = f"{scale['id']}-c{clients}-r{repetition}"
    application = f"pg36-ch26-{run_id}"
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    run_dir.chmod(0o700)
    reset_cell(source_dir, bench_env, f"pg36-ch26-reset-{run_id}")
    before = psql_json(
        bench_connection(f"pg36-ch26-snapshot-before-{run_id}"),
        sql_file=source_dir / "stat-snapshot.sql",
        env=bench_env,
    )
    write_json(run_dir / "stats-before.json", before)
    sampler_duration = duration + 2.0
    handles = start_samplers(
        source_dir,
        run_dir,
        bench_env,
        application,
        sampler_duration,
        remote_sampler,
    )
    log_prefix = run_dir / "transactions"
    command, pgbench_env = pgbench_command(
        source_dir,
        bench_env,
        application=application,
        scale=scale,
        clients=clients,
        duration=duration,
        seed=seed,
        log_prefix=log_prefix,
    )
    time.sleep(0.5)
    started_at = utc_now()
    started_epoch = time.time()
    try:
        completed = run(command, env=pgbench_env, timeout=duration + 30)
    finally:
        stop_samplers(handles, wait_for_system=True)
    ended_epoch = time.time()
    ended_at = utc_now()
    (run_dir / "pgbench.stdout").write_text(completed.stdout, encoding="utf-8")
    (run_dir / "pgbench.stderr").write_text(completed.stderr, encoding="utf-8")
    (run_dir / "pgbench.stdout").chmod(0o600)
    (run_dir / "pgbench.stderr").chmod(0o600)
    time.sleep(1.2)
    after = psql_json(
        bench_connection(f"pg36-ch26-snapshot-after-{run_id}"),
        sql_file=source_dir / "stat-snapshot.sql",
        env=bench_env,
    )
    write_json(run_dir / "stats-after.json", after)
    output = parse_pgbench_output(completed.stdout)
    log = parse_transaction_logs(log_prefix)
    if (
        output["failed_transactions"] != 0
        or log["failures"] != 0
        or log["skipped"] != 0
        or output["processed_transactions"] != log["transactions"]
    ):
        raise BenchmarkError(
            f"{run_id} transaction evidence mismatch: output={output}, log={log}"
        )
    client_system = parse_system_samples(
        run_dir / "client-system.jsonl",
        measured_start_epoch=started_epoch,
        measured_end_epoch=ended_epoch,
    )
    server_system = parse_system_samples(
        run_dir / "server-system.jsonl",
        measured_start_epoch=started_epoch,
        measured_end_epoch=ended_epoch,
    )
    waits = parse_wait_samples(run_dir / "database-waits.jsonl")
    delta = stat_delta(before, after)
    latencies = log.pop("_latencies")
    summary = {
        "run_id": run_id,
        "scale_id": scale["id"],
        "scale_factor": scale["factor"],
        "clients": clients,
        "jobs": 1 if clients == 1 else 2,
        "repetition": repetition,
        "seed": seed,
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_seconds": ended_epoch - started_epoch,
        "measured_seconds": duration,
        "pgbench": output,
        "transaction_log": log,
        "client_system": client_system,
        "server_system": server_system,
        "database_waits": waits,
        "stat_delta": delta,
        "raw_files": {},
        "_latencies": latencies,
    }
    for path in sorted(run_dir.iterdir()):
        if path.is_file():
            summary["raw_files"][path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
    return summary


def fetch_vm_range(
    expression: str,
    start: float,
    end: float,
    *,
    step: int = 5,
) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "query": expression,
            "start": f"{start:.3f}",
            "end": f"{end:.3f}",
            "step": str(step),
        }
    )
    url = f"http://10.10.10.10:8428/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read())
    except Exception as exc:
        return {
            "status": "query-failed",
            "error_type": type(exc).__name__,
            "series": 0,
            "samples": 0,
        }
    rows = payload.get("data", {}).get("result", [])
    values: list[float] = []
    for row in rows:
        for _, raw in row.get("values", []):
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                values.append(number)
    if not values:
        return {
            "status": "missing",
            "series": len(rows),
            "samples": 0,
        }
    return {
        "status": "observed",
        "series": len(rows),
        "samples": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
    }


def capture_pigsty_window(start: float, end: float) -> dict[str, Any]:
    queries = {
        "server_cpu_busy_percent": (
            '100 * (1 - avg(rate(node_cpu_seconds_total{ins="pg-test-1",'
            'mode="idle"}[30s])))'
        ),
        "server_cpu_iowait_percent": (
            '100 * avg(rate(node_cpu_seconds_total{ins="pg-test-1",'
            'mode="iowait"}[30s]))'
        ),
        "client_cpu_busy_percent": (
            '100 * (1 - avg(rate(node_cpu_seconds_total{ins="pg-meta-1",'
            'mode="idle"}[30s])))'
        ),
        "server_disk_read_bytes_per_second": (
            'sum(rate(node_disk_read_bytes_total{ins="pg-test-1"}[30s]))'
        ),
        "server_disk_write_bytes_per_second": (
            'sum(rate(node_disk_written_bytes_total{ins="pg-test-1"}[30s]))'
        ),
        "wal_bytes_per_second": (
            'rate(pg_wal_bytes{cls="pg-test",ins="pg-test-1"}[30s])'
        ),
        "database_commits_per_second": (
            'rate(pg_db_xact_commit{cls="pg-test",ins="pg-test-1",'
            'datname="pg36_capacity"}[30s])'
        ),
        "replica_replay_gap_bytes": (
            'max(pg_repl_replay_diff{cls="pg-test",ins="pg-test-1"})'
        ),
    }
    return {
        "source": "Pigsty VictoriaMetrics query_range",
        "window_start_epoch": start,
        "window_end_epoch": end,
        "step_seconds": 5,
        "raw_payload_exported": False,
        "queries": {
            name: {
                "expression": expression,
                "result": fetch_vm_range(expression, start, end),
            }
            for name, expression in queries.items()
        },
    }


def summarize_cells(
    runs: list[dict[str, Any]],
    matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for run_row in runs:
        grouped[(run_row["scale_id"], run_row["clients"])].append(run_row)
    cells = []
    for cell in matrix["cells"]:
        key = (cell["scale_id"], cell["clients"])
        rows = sorted(grouped[key], key=lambda row: row["repetition"])
        if len(rows) != 5:
            raise BenchmarkError(f"cell {cell['cell_id']} has {len(rows)} runs")
        pooled = [
            value for row in rows for value in row.pop("_latencies")
        ]
        tps_values = [row["pgbench"]["tps"] for row in rows]
        p95_values = [
            row["transaction_log"]["latency_ms"]["p95"] for row in rows
        ]
        processed = sum(row["pgbench"]["processed_transactions"] for row in rows)
        wal_bytes = sum(row["stat_delta"]["wal"].get("wal_bytes", 0) for row in rows)
        place_orders = sum(
            row["transaction_log"]["script_counts"].get("place-order", 0)
            for row in rows
        )
        relation_growth = sum(
            row["stat_delta"]["relations"].get("schema_bytes", 0)
            for row in rows
        )
        cpu_demand = []
        for row in rows:
            processed_run = row["pgbench"]["processed_transactions"]
            cpu_demand.append(
                row["server_system"]["cpu"]["work_ratio_mean"]
                * row["measured_seconds"]
                / processed_run
            )
        cells.append(
            {
                "cell_id": cell["cell_id"],
                "scale_id": cell["scale_id"],
                "scale_factor": cell["scale_factor"],
                "clients": cell["clients"],
                "repetitions": len(rows),
                "run_ids": [row["run_id"] for row in rows],
                "transactions": processed,
                "failures": sum(
                    row["pgbench"]["failed_transactions"] for row in rows
                ),
                "late_transactions": sum(
                    row["pgbench"]["late_transactions"] for row in rows
                ),
                "tps": bootstrap_median_interval(
                    tps_values,
                    seed=2026072900 + cell["scale_factor"] * 10 + cell["clients"],
                ),
                "latency_ms": {
                    "pooled_sample_count": len(pooled),
                    "pooled_p50": quantile(pooled, 0.50),
                    "pooled_p95": quantile(pooled, 0.95),
                    "pooled_p99": quantile(pooled, 0.99),
                    "pooled_max": max(pooled),
                    "run_p95_median_interval": bootstrap_median_interval(
                        p95_values,
                        seed=2026073000
                        + cell["scale_factor"] * 10
                        + cell["clients"],
                    ),
                },
                "server_cpu": {
                    "work_ratio_median": median(
                        row["server_system"]["cpu"]["work_ratio_mean"]
                        for row in rows
                    ),
                    "busy_ratio_median": median(
                        row["server_system"]["cpu"]["busy_ratio_mean"]
                        for row in rows
                    ),
                    "iowait_ratio_median": median(
                        row["server_system"]["cpu"]["iowait_ratio_mean"]
                        for row in rows
                    ),
                    "cpu_seconds_per_transaction_median": statistics.median(
                        cpu_demand
                    ),
                },
                "client_cpu": {
                    "work_ratio_median": median(
                        row["client_system"]["cpu"]["work_ratio_mean"]
                        for row in rows
                    ),
                    "busy_ratio_median": median(
                        row["client_system"]["cpu"]["busy_ratio_mean"]
                        for row in rows
                    ),
                },
                "wal": {
                    "bytes": wal_bytes,
                    "bytes_per_transaction": wal_bytes / processed,
                    "records": sum(
                        row["stat_delta"]["wal"].get("wal_records", 0)
                        for row in rows
                    ),
                    "full_page_images": sum(
                        row["stat_delta"]["wal"].get("wal_fpi", 0)
                        for row in rows
                    ),
                },
                "durable_growth": {
                    "place_orders": place_orders,
                    "schema_growth_bytes": relation_growth,
                    "bytes_per_place_order": (
                        relation_growth / place_orders if place_orders else None
                    ),
                    "warning": "relation allocation is page-granular and includes index growth",
                },
                "database": {
                    "block_reads": sum(
                        row["stat_delta"]["database"].get("blks_read", 0)
                        for row in rows
                    ),
                    "block_hits": sum(
                        row["stat_delta"]["database"].get("blks_hit", 0)
                        for row in rows
                    ),
                    "temp_bytes": sum(
                        row["stat_delta"]["database"].get("temp_bytes", 0)
                        for row in rows
                    ),
                    "deadlocks": sum(
                        row["stat_delta"]["database"].get("deadlocks", 0)
                        for row in rows
                    ),
                },
                "wait_types": dict(
                    Counter(
                        {
                            wait_type: sum(
                                row["database_waits"]["by_wait_type"].get(
                                    wait_type, 0
                                )
                                for row in rows
                            )
                            for wait_type in {
                                key
                                for row in rows
                                for key in row["database_waits"][
                                    "by_wait_type"
                                ]
                            }
                        }
                    ).most_common()
                ),
            }
        )
    return cells


def derive_capacity(cells: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {(cell["scale_id"], cell["clients"]): cell for cell in cells}
    brackets = []
    provisional = []
    for scale_id in ("S", "M", "L"):
        low = by_key[(scale_id, 1)]
        high = by_key[(scale_id, 8)]
        gain = high["tps"]["estimate"] / low["tps"]["estimate"]
        latency_ratio = (
            high["latency_ms"]["pooled_p95"]
            / low["latency_ms"]["pooled_p95"]
        )
        high_server_cpu = high["server_cpu"]["work_ratio_median"]
        high_client_cpu = high["client_cpu"]["work_ratio_median"]
        if gain < 1.20 and latency_ratio > 2:
            interpretation = "knee-bracketed-at-or-below-eight-clients"
        elif high_server_cpu >= 0.85 and high_client_cpu < 0.85:
            interpretation = "server-resource-ceiling-observed-by-eight-clients"
        elif high_client_cpu >= 0.85:
            interpretation = "client-ceiling-confounds-knee"
        else:
            interpretation = "knee-not-bracketed-by-one-and-eight-clients"
        brackets.append(
            {
                "scale_id": scale_id,
                "throughput_gain_c8_over_c1": gain,
                "pooled_p95_multiplier_c8_over_c1": latency_ratio,
                "c8_server_work_ratio": high_server_cpu,
                "c8_client_work_ratio": high_client_cpu,
                "interpretation": interpretation,
                "exact_knee_known": False,
            }
        )
        demand = high["server_cpu"][
            "cpu_seconds_per_transaction_median"
        ]
        provisional.append(
            {
                "scale_id": scale_id,
                "cpu_seconds_per_mixed_transaction": demand,
                "sandbox_tps_at_65_percent_cpu": 0.65 / demand,
                "wal_bytes_per_mixed_transaction": high["wal"][
                    "bytes_per_transaction"
                ],
                "production_approved": False,
            }
        )
    return {
        "saturation_brackets": brackets,
        "sandbox_only_resource_demand": provisional,
        "production_sustainable_tps": None,
        "production_gate": "pending",
        "why_null": [
            "one shared-hypervisor virtual CPU and virtual storage are not production hardware",
            "the measured probe is closed-loop rather than an offered-load SLO sweep",
            "the direct-primary path excludes application, HAProxy, PgBouncer, and WAN costs",
            "failure, maintenance, backup, restore, and capacity-lead-time scenarios were not measured"
        ],
    }


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    output_dir.chmod(0o700)
    requirements = read_json(source_dir / "requirements.json")
    workload = read_json(source_dir / "workload-contract.json")
    matrix = read_json(source_dir / "experiment-matrix.json")
    source_hashes = {
        name: sha256(source_dir / name)
        for name in SOURCE_NAMES
        if (source_dir / name).exists()
    }
    if set(source_hashes) != set(SOURCE_NAMES):
        missing = sorted(set(SOURCE_NAMES) - set(source_hashes))
        raise BenchmarkError(f"remote source bundle is incomplete: {missing}")
    assert_clean_start()
    environment = capture_environment()
    password = secrets.token_hex(24)
    pgpass_path: Path | None = None
    bench_env: dict[str, str] | None = None
    fixture_created = False
    cleanup = {
        "status": "not-attempted",
        "database_absent": False,
        "role_absent": False,
    }
    run_uuid = str(uuid.uuid4())
    remote_sampler = f"/tmp/pg36-ch26-system-sampler.{run_uuid}.py"
    run(
        [
            "scp",
            "-q",
            str(source_dir / "system_sampler.py"),
            f"vagrant@{PRIMARY_ADDRESS}:{remote_sampler}",
        ]
    )
    overall_started_epoch = time.time()
    overall_started_at = utc_now()
    status = "failed"
    error: str | None = None
    result: dict[str, Any] = {}
    try:
        create_fixture(password)
        fixture_created = True
        pgpass_path, bench_env = create_pgpass(output_dir, password)
        identity = psql_json(
            bench_connection("pg36-ch26-role-gate"),
            env=bench_env,
            sql=f"""
SELECT jsonb_build_object(
  'database', current_database(),
  'user', current_user,
  'superuser', (
    SELECT rolsuper FROM pg_roles WHERE rolname = current_user
  ),
  'cluster_name', current_setting('cluster_name'),
  'in_recovery', pg_is_in_recovery(),
  'database_marker', (
    SELECT shobj_description(oid, 'pg_database')
    FROM pg_database
    WHERE datname = current_database()
  ),
  'role_marker', (
    SELECT shobj_description(oid, 'pg_authid')
    FROM pg_roles
    WHERE rolname = current_user
  ),
  'hba_membership', (
    SELECT jsonb_build_object(
      'role', parent.rolname,
      'inherit', membership.inherit_option,
      'set', membership.set_option,
      'readonly_member', pg_has_role(
        current_user,
        'dbrole_readonly',
        'MEMBER'
      )
    )
    FROM pg_auth_members AS membership
    JOIN pg_roles AS parent
      ON parent.oid = membership.roleid
    JOIN pg_roles AS child
      ON child.oid = membership.member
    WHERE parent.rolname = 'dbrole_readwrite'
      AND child.rolname = current_user
  )
);
""",
        )
        if identity != {
            "database": DATABASE,
            "user": BENCH_ROLE,
            "superuser": False,
            "cluster_name": "pg-test",
            "in_recovery": False,
            "database_marker": DATABASE_MARKER,
            "role_marker": ROLE_MARKER,
            "hba_membership": {
                "role": "dbrole_readwrite",
                "inherit": False,
                "set": False,
                "readonly_member": True,
            },
        }:
            raise BenchmarkError(f"benchmark role identity failed: {identity!r}")
        scales = workload["data_model"]["scales"]
        initialized = []
        warmups = []
        measured_runs = []
        for scale in scales:
            initialized.append(
                initialize_scale(
                    source_dir,
                    output_dir,
                    bench_env,
                    scale,
                )
            )
            for clients in workload["controls"]["concurrency_levels"]:
                warmups.append(
                    warm_up(
                        source_dir,
                        bench_env,
                        scale,
                        clients,
                        workload["controls"][
                            "warmup_seconds_per_scale_and_concurrency"
                        ],
                        workload["controls"]["base_seed"]
                        + scale["factor"] * 1000
                        + clients,
                    )
                )
            for repetition, order in enumerate(
                workload["controls"]["concurrency_order_by_repetition"],
                start=1,
            ):
                for clients in order:
                    seed = (
                        workload["controls"]["base_seed"]
                        + scale["factor"] * 100
                        + clients * 10
                        + repetition
                    )
                    row = run_measured(
                        source_dir,
                        output_dir,
                        bench_env,
                        scale,
                        clients,
                        repetition,
                        workload["controls"]["measured_seconds"],
                        seed,
                        remote_sampler,
                    )
                    measured_runs.append(row)
                    print(
                        "completed "
                        f"{row['run_id']} "
                        f"tps={row['pgbench']['tps']:.3f} "
                        "p95_ms="
                        f"{row['transaction_log']['latency_ms']['p95']:.3f}",
                        flush=True,
                    )
        overall_ended_epoch = time.time()
        pigsty = capture_pigsty_window(
            overall_started_epoch - 30,
            overall_ended_epoch + 30,
        )
        cells = summarize_cells(measured_runs, matrix)
        capacity = derive_capacity(cells)
        status = "passed"
        result = {
            "schema": "pg36-ch26-capacity-evidence-v1",
            "release": requirements["release"],
            "run_id": run_uuid,
            "status": status,
            "captured_at": utc_now(),
            "window": {
                "started_at": overall_started_at,
                "ended_at": utc_now(),
                "started_epoch": overall_started_epoch,
                "ended_epoch": overall_ended_epoch,
                "elapsed_seconds": overall_ended_epoch - overall_started_epoch,
            },
            "risk": requirements["risk"]["classification"],
            "target": requirements["target"],
            "source_hashes": source_hashes,
            "environment": environment,
            "benchmark_identity": identity,
            "experiment": {
                "workload_id": workload["workload_id"],
                "mode": workload["semantics"]["mode"],
                "measured_runs": len(measured_runs),
                "cells": len(cells),
                "repetitions_per_cell": 5,
                "initialized": initialized,
                "warmups": warmups,
                "run_order": [row["run_id"] for row in measured_runs],
                "runs": measured_runs,
                "cell_summaries": cells,
            },
            "pigsty_corroboration": pigsty,
            "capacity": capacity,
            "secrets_exported": False,
            "query_text_exported": False,
            "statistics_reset_performed": False,
            "cache_drop_performed": False,
            "configuration_changed": False,
            "production_ch26_gate": "pending",
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if pgpass_path is not None and pgpass_path.exists():
            pgpass_path.unlink()
        password = ""
        run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                f"vagrant@{PRIMARY_ADDRESS}",
                "rm",
                "-f",
                "--",
                remote_sampler,
            ],
            check=False,
        )
        if fixture_created:
            try:
                cleanup = cleanup_fixture()
            except Exception as cleanup_exc:
                cleanup = {
                    "status": "failed",
                    "database_absent": False,
                    "role_absent": False,
                    "error_type": type(cleanup_exc).__name__,
                }
                if error is None:
                    raise
        if result:
            result["cleanup"] = cleanup
            result["status"] = (
                "passed"
                if cleanup.get("database_absent")
                and cleanup.get("role_absent")
                else "failed"
            )
            write_json(output_dir / "capacity-evidence.json", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"chapter 26 benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
