#!/usr/bin/env python3
"""Run the guarded blind flow-pressure versus WAL-retention exercise."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

from common import (
    LabError,
    read_json,
    run,
    sha256_file,
    ssh_base,
    utc_now,
    write_json,
)


SOURCE_FILES = (
    "requirements.json",
    "classification-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "common.py",
    "capture.py",
    "exercise.py",
    "classify.py",
    "validate.py",
    "review.py",
    "task.sh",
)


REMOTE_PROGRAM = r'''
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


CONFIG = json.loads(__CONFIG_JSON__)


class ExerciseError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(args, timeout=60, check=True):
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExerciseError("cannot execute " + str(args[0]) + ": " + str(exc))
    if check and result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        detail = lines[-1] if lines else "exit " + str(result.returncode)
        raise ExerciseError("command failed (" + str(args[0]) + "): " + detail)
    return result


def json_value(raw, label):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExerciseError(label + " returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExerciseError(label + " returned no object")
    return value


run_id = CONFIG["run_id"]
if not re.fullmatch(r"[0-9a-f-]{36}", run_id):
    raise ExerciseError("run identity is unsafe")

prefix = str(CONFIG["root_prefix"])
root = Path(prefix + "-" + run_id)
if (
    not re.fullmatch(
        r"/tmp/pg36-ch34-overload-[0-9a-f-]{36}",
        str(root),
    )
    or root.exists()
):
    raise ExerciseError("disposable root is unsafe or already exists")

data_dir = root / "data"
socket_dir = root / "socket"
server_log = root / "postgres.log"
marker = root / ".pg36-ch34-owned"
port = int(CONFIG["port"])
clients = []
server_started = False
result = None


def executable(name):
    bindir = run(["pg_config", "--bindir"]).stdout.strip()
    path = Path(bindir) / name
    if not path.is_file():
        raise ExerciseError("PostgreSQL executable is missing: " + str(path))
    return str(path)


initdb = executable("initdb")
pg_ctl = executable("pg_ctl")
psql_bin = executable("psql")


def psql(sql, user="postgres", timeout=60, check=True):
    return run(
        [
            psql_bin,
            "-X",
            "-qAt",
            "-h",
            str(socket_dir),
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            "postgres",
            "--set=ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        timeout=timeout,
        check=check,
    )


def sql_json(sql, label):
    return json_value(psql(sql).stdout.strip(), label)


def scalar_int(sql, label):
    raw = psql(sql).stdout.strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ExerciseError(label + " did not return an integer") from exc


def filesystem_projection():
    usage = shutil.disk_usage(root)
    wal_bytes = 0
    wal_dir = data_dir / "pg_wal"
    if wal_dir.is_dir():
        for entry in wal_dir.iterdir():
            if entry.is_file():
                wal_bytes += entry.stat().st_size
    return {
        "root_free_bytes": usage.free,
        "root_total_bytes": usage.total,
        "pg_wal_allocated_bytes": wal_bytes,
        "filesystem_fill_injected": False,
    }


def engine_projection():
    return sql_json(
        """
        SELECT json_build_object(
            'server_version', current_setting('server_version'),
            'port', current_setting('port')::int,
            'listen_addresses', current_setting('listen_addresses'),
            'max_connections', current_setting('max_connections')::int,
            'superuser_reserved_connections',
                current_setting('superuser_reserved_connections')::int,
            'max_replication_slots',
                current_setting('max_replication_slots')::int,
            'max_slot_wal_keep_size',
                current_setting('max_slot_wal_keep_size'),
            'data_checksums', current_setting('data_checksums')
        )
        """,
        "engine projection",
    )


def slot_projection(slot_name=None):
    predicate = ""
    if slot_name is not None:
        if not re.fullmatch(r"[a-z0-9_]{1,63}", slot_name):
            raise ExerciseError("slot identity is unsafe")
        predicate = " WHERE slot_name = '" + slot_name + "'"
    return sql_json(
        """
        SELECT json_build_object(
            'physical_slots', count(*) FILTER (
                WHERE slot_type = 'physical'
            )::int,
            'inactive_physical_slots', count(*) FILTER (
                WHERE slot_type = 'physical' AND NOT active
            )::int,
            'rows', COALESCE(
                json_agg(
                    json_build_object(
                        'slot_name', slot_name,
                        'slot_type', slot_type,
                        'active', active,
                        'restart_lsn', restart_lsn::text,
                        'retained_wal_bytes',
                            COALESCE(
                                pg_wal_lsn_diff(
                                    pg_current_wal_lsn(),
                                    restart_lsn
                                )::bigint,
                                0
                            ),
                        'wal_status', wal_status,
                        'safe_wal_size', safe_wal_size,
                        'invalidation_reason', invalidation_reason
                    )
                    ORDER BY slot_name
                ),
                '[]'::json
            )
        )
        FROM pg_catalog.pg_replication_slots
        """ + predicate,
        "slot projection",
    )


def terminate_clients():
    terminated = 0
    killed = 0
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline and any(
        process.poll() is None for process in clients
    ):
        time.sleep(0.1)
    for process in clients:
        if process.poll() is None:
            process.terminate()
            terminated += 1
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and any(
        process.poll() is None for process in clients
    ):
        time.sleep(0.1)
    for process in clients:
        if process.poll() is None:
            process.kill()
            killed += 1
    for process in clients:
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=2)
            killed += 1
    return terminated, killed


def run_flow(case_id, engine):
    flow = CONFIG["flow"]
    application_prefix = "pg36-ch34-flow-" + run_id[:8] + "-"
    statement = (
        "BEGIN; "
        "SELECT pg_advisory_xact_lock(340034); "
        "SELECT pg_sleep(" + str(int(flow["statement_seconds"])) + "); "
        "COMMIT;"
    )
    launched_at = utc_now()
    for number in range(int(flow["attempted_clients"])):
        env = os.environ.copy()
        env["PGAPPNAME"] = application_prefix + str(number)
        process = subprocess.Popen(
            [
                psql_bin,
                "-X",
                "-qAt",
                "-h",
                str(socket_dir),
                "-p",
                str(port),
                "-U",
                "pg36_load",
                "-d",
                "postgres",
                "--set=ON_ERROR_STOP=1",
                "-c",
                statement,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        clients.append(process)
    time.sleep(float(flow["sample_after_seconds"]))

    connection = sql_json(
        """
        SELECT json_build_object(
            'attempted_clients', %d,
            'observed_sessions', count(*)::int,
            'active_sessions', count(*) FILTER (
                WHERE state = 'active'
            )::int,
            'lock_waiters', count(*) FILTER (
                WHERE wait_event_type = 'Lock'
            )::int,
            'application_prefix', '%s'
        )
        FROM pg_catalog.pg_stat_activity
        WHERE application_name LIKE '%s%%'
        """
        % (
            int(flow["attempted_clients"]),
            application_prefix,
            application_prefix,
        ),
        "flow activity projection",
    )
    rejected_before_action = sum(
        1
        for process in clients
        if process.poll() is not None and process.returncode != 0
    )
    connection["connection_rejections"] = rejected_before_action
    connection["sampled_at"] = utc_now()
    retention = slot_projection()
    retained_wal_bytes = 0
    for row in retention["rows"]:
        retained_wal_bytes += int(row.get("retained_wal_bytes") or 0)

    packet = {
        "case_id": case_id,
        "observed_at": utc_now(),
        "alert": CONFIG["common_alert"],
        "connection": {
            "attempted_clients": connection["attempted_clients"],
            "observed_sessions": connection["observed_sessions"],
            "active_sessions": connection["active_sessions"],
            "connection_rejections": connection["connection_rejections"],
            "lock_waiters": connection["lock_waiters"],
        },
        "retention": {
            "inactive_physical_slots": retention[
                "inactive_physical_slots"
            ],
            "retained_wal_bytes": retained_wal_bytes,
        },
        "engine": engine,
        "filesystem": filesystem_projection(),
    }

    canceled = scalar_int(
        """
        SELECT count(*)
        FROM (
            SELECT pg_cancel_backend(pid) AS signaled
            FROM pg_catalog.pg_stat_activity
            WHERE application_name LIKE '%s%%'
              AND pid <> pg_backend_pid()
        ) AS cancellation
        WHERE signaled
        """
        % application_prefix,
        "exact fixture cancellation",
    )
    fallback_terminated, fallback_killed = terminate_clients()
    time.sleep(0.25)
    post_sessions = scalar_int(
        """
        SELECT count(*)
        FROM pg_catalog.pg_stat_activity
        WHERE application_name LIKE '%s%%'
        """
        % application_prefix,
        "post-flow session count",
    )
    probe = scalar_int("SELECT 1", "post-flow probe")
    post_slots = slot_projection()
    return {
        "case_id": case_id,
        "scenario": "FLOW",
        "expected_route": "RELIEVE_FLOW_PRESSURE",
        "started_at": launched_at,
        "observed": {
            "connection": connection,
            "retention": retention,
        },
        "blind_packet": packet,
        "mitigation": {
            "action": "pg_cancel_backend",
            "scope": "exact-application-name-prefix",
            "application_prefix": application_prefix,
            "cancel_signals_sent": canceled,
            "fallback_exact_client_processes_terminated":
                fallback_terminated,
            "fallback_exact_client_processes_killed": fallback_killed,
            "broad_cancel_used": False,
            "max_connections_changed": False,
        },
        "recovery": {
            "post_fixture_sessions": post_sessions,
            "post_probe": probe,
            "post_inactive_physical_slots": post_slots[
                "inactive_physical_slots"
            ],
        },
    }


def run_retention(case_id, engine):
    retention_cfg = CONFIG["retention"]
    started_at = utc_now()
    slot_name = "pg36_ch34_" + run_id.replace("-", "")[:16]
    if not re.fullmatch(r"[a-z0-9_]{1,63}", slot_name):
        raise ExerciseError("generated slot identity is unsafe")
    if slot_projection()["physical_slots"] != 0:
        raise ExerciseError("disposable cluster unexpectedly has a slot")

    psql(
        "SELECT * FROM pg_catalog.pg_create_physical_replication_slot("
        "'" + slot_name + "', true, false)"
    )
    initial_lsn = psql("SELECT pg_current_wal_lsn()::text").stdout.strip()
    batches = 0
    snapshot = slot_projection(slot_name)
    while True:
        rows = snapshot["rows"]
        if len(rows) != 1:
            raise ExerciseError("owned physical slot disappeared")
        retained = int(rows[0]["retained_wal_bytes"])
        if retained >= int(retention_cfg["minimum_retained_wal_bytes"]):
            break
        if retained > int(retention_cfg["maximum_generated_wal_bytes"]):
            raise ExerciseError("retained WAL exceeded the exercise cap")
        psql(
            """
            INSERT INTO pg36_ch34_wal(payload)
            SELECT repeat(md5(g::text || clock_timestamp()::text), 8)
            FROM generate_series(1, %d) AS g;
            SELECT pg_switch_wal();
            CHECKPOINT;
            """
            % int(retention_cfg["payload_batch_rows"]),
            timeout=120,
        )
        batches += 1
        if batches > 12:
            raise ExerciseError("retained WAL did not reach the lower bound")
        snapshot = slot_projection(slot_name)

    retained = int(snapshot["rows"][0]["retained_wal_bytes"])
    if retained > int(retention_cfg["maximum_generated_wal_bytes"]):
        raise ExerciseError("retained WAL exceeded the exercise cap")
    final_lsn = psql("SELECT pg_current_wal_lsn()::text").stdout.strip()
    generated = scalar_int(
        """
        SELECT pg_wal_lsn_diff('%s', '%s')::bigint
        """
        % (final_lsn, initial_lsn),
        "generated WAL size",
    )
    packet = {
        "case_id": case_id,
        "observed_at": utc_now(),
        "alert": CONFIG["common_alert"],
        "connection": {
            "attempted_clients": 0,
            "observed_sessions": 0,
            "active_sessions": 0,
            "connection_rejections": 0,
            "lock_waiters": 0,
        },
        "retention": {
            "inactive_physical_slots": snapshot[
                "inactive_physical_slots"
            ],
            "retained_wal_bytes": retained,
        },
        "engine": engine,
        "filesystem": filesystem_projection(),
    }

    evidence_preserved_at = utc_now()
    psql(
        "SELECT pg_catalog.pg_drop_replication_slot('" + slot_name + "')"
    )
    psql("CHECKPOINT")
    post_slots = slot_projection()
    return {
        "case_id": case_id,
        "scenario": "RETENTION",
        "expected_route": "PRESERVE_RETENTION_EVIDENCE",
        "started_at": started_at,
        "observed": {
            "slot": snapshot,
            "initial_lsn": initial_lsn,
            "final_lsn": final_lsn,
            "generated_wal_bytes": generated,
            "generation_batches": batches,
        },
        "blind_packet": packet,
        "mitigation": {
            "action": "pg_drop_replication_slot",
            "slot_name": slot_name,
            "scope": "exact-owned-disposable-slot",
            "evidence_preserved_at": evidence_preserved_at,
            "manual_pg_wal_file_deletion": False,
            "broad_slot_cleanup_used": False,
            "connection_cancel_used": False,
        },
        "recovery": {
            "post_physical_slots": post_slots["physical_slots"],
            "post_inactive_physical_slots": post_slots[
                "inactive_physical_slots"
            ],
            "post_probe": scalar_int("SELECT 1", "post-retention probe"),
        },
    }


try:
    root.mkdir(mode=0o700)
    marker.write_text(run_id + "\n", encoding="utf-8")
    marker.chmod(0o600)
    socket_dir.mkdir(mode=0o700)
    run(
        [
            initdb,
            "-D",
            str(data_dir),
            "--data-checksums",
            "--no-locale",
            "--encoding=UTF8",
            "--auth-local=trust",
            "--auth-host=reject",
        ],
        timeout=120,
    )
    with (data_dir / "postgresql.conf").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n"
            "listen_addresses = ''\n"
            "port = " + str(port) + "\n"
            "unix_socket_directories = '" + str(socket_dir) + "'\n"
            "unix_socket_permissions = 0700\n"
            "max_connections = " + str(int(CONFIG["max_connections"])) + "\n"
            "superuser_reserved_connections = "
            + str(int(CONFIG["superuser_reserved_connections"])) + "\n"
            "max_replication_slots = "
            + str(int(CONFIG["max_replication_slots"])) + "\n"
            "max_slot_wal_keep_size = '-1'\n"
            "max_wal_size = '64MB'\n"
            "min_wal_size = '32MB'\n"
            "wal_level = replica\n"
            "log_connections = off\n"
            "log_disconnections = off\n"
        )
    run(
        [
            pg_ctl,
            "-D",
            str(data_dir),
            "-l",
            str(server_log),
            "-w",
            "start",
        ],
        timeout=120,
    )
    server_started = True
    psql(
        """
        CREATE ROLE pg36_load LOGIN;
        CREATE TABLE pg36_ch34_wal (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            payload text NOT NULL
        );
        """
    )
    engine = engine_projection()
    if (
        not str(engine["server_version"]).startswith(
            CONFIG["postgresql_observed"]
        )
        or engine["port"] != port
        or engine["listen_addresses"] != ""
        or engine["max_connections"] != int(CONFIG["max_connections"])
        or engine["superuser_reserved_connections"]
            != int(CONFIG["superuser_reserved_connections"])
        or engine["max_replication_slots"]
            != int(CONFIG["max_replication_slots"])
        or engine["max_slot_wal_keep_size"] != "-1"
        or engine["data_checksums"] != "on"
    ):
        raise ExerciseError(
            "disposable PostgreSQL settings drifted: "
            + json.dumps(engine, sort_keys=True)
        )

    scenarios = ["FLOW", "RETENTION"]
    secrets.SystemRandom().shuffle(scenarios)
    cases = []
    for scenario in scenarios:
        case_id = "case-" + secrets.token_hex(6)
        if scenario == "FLOW":
            cases.append(run_flow(case_id, engine))
        else:
            cases.append(run_retention(case_id, engine))

    result = {
        "schema": "pg36-ch34-exercise-v1",
        "run_id": run_id,
        "started_at": CONFIG["started_at"],
        "finished_at": utc_now(),
        "target": CONFIG["target"],
        "host": CONFIG["host"],
        "disposable": {
            "root": str(root),
            "port": port,
            "listen_addresses": "",
            "unix_socket_only": True,
            "data_checksums": True,
            "managed_patroni_member": False,
            "managed_dcs_member": False,
            "managed_service_route": False,
        },
        "common_alert": CONFIG["common_alert"],
        "scenario_order": scenarios,
        "cases": cases,
        "blind_packets": [case["blind_packet"] for case in cases],
        "hidden_answers": [
            {
                "case_id": case["case_id"],
                "scenario": case["scenario"],
                "expected_route": case["expected_route"],
            }
            for case in cases
        ],
        "safety": {
            "managed_postgresql_mutated": False,
            "managed_connection_storm": False,
            "managed_replication_slot_created": False,
            "managed_query_canceled": False,
            "managed_service_changed": False,
            "managed_route_changed": False,
            "host_cache_dropped": False,
            "oom_injected": False,
            "filesystem_fill_injected": False,
            "wrong_action_executed": False,
            "manual_pg_wal_file_deletion": False,
            "external_dispatch_count": 0,
            "production_data_touched": False,
            "production_traffic_touched": False,
        },
    }
finally:
    terminate_clients()
    if server_started:
        run(
            [
                pg_ctl,
                "-D",
                str(data_dir),
                "-m",
                "fast",
                "-w",
                "stop",
            ],
            timeout=120,
            check=False,
        )
    if root.exists():
        marker_ok = (
            marker.is_file()
            and marker.read_text(encoding="utf-8").strip() == run_id
        )
        if (
            not marker_ok
            or not re.fullmatch(
                r"/tmp/pg36-ch34-overload-[0-9a-f-]{36}",
                str(root),
            )
        ):
            raise ExerciseError("refusing unsafe disposable-root cleanup")
        shutil.rmtree(root)

if result is None:
    raise ExerciseError("exercise produced no result")
result["cleanup"] = {
    "exact_root": str(root),
    "marker_matched": True,
    "root_exists_after": root.exists(),
    "server_stopped_before_cleanup": True,
}
print(json.dumps(result, sort_keys=True))
'''


def require_guards(args: argparse.Namespace, requirements: dict[str, Any]) -> None:
    if args.target_token != "pg36-l2-vagrant/pg-test":
        raise LabError("target token does not identify the chapter 34 sandbox")
    if args.confirmation != "BLIND_FLOW_VS_RETENTION_CH34":
        raise LabError("chapter 34 confirmation token is missing")
    if args.authority != "nonproduction-no-data-no-traffic":
        raise LabError("chapter 34 authority boundary drifted")
    target = requirements.get("target", {})
    risk = requirements.get("risk", {})
    if (
        target.get("id") != args.target_token
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or risk.get("managed_postgresql_mutation_permitted") is not False
        or risk.get("managed_connection_storm_permitted") is not False
        or risk.get("managed_replication_slot_permitted") is not False
        or risk.get("managed_query_cancel_permitted") is not False
        or risk.get("oom_injection_permitted") is not False
        or risk.get("manual_pg_wal_deletion_permitted") is not False
    ):
        raise LabError("requirements do not preserve the chapter 34 boundary")


def source_manifest(source_dir: Path) -> dict[str, Any]:
    rows = []
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file() or path.is_symlink():
            raise LabError(f"source file is missing or unsafe: {name}")
        rows.append(
            {
                "path": name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema": "pg36-ch34-source-manifest-v1",
        "generated_at": utc_now(),
        "files": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--authority", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        requirements = read_json(args.requirements)
        require_guards(args, requirements)
        if args.output.exists() and any(args.output.iterdir()):
            raise LabError("refusing to overwrite a non-empty exercise directory")
        args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.chmod(0o700)
        run_id = str(uuid.UUID(bytes=secrets.token_bytes(16), version=4))
        disposable = requirements["disposable_cluster"]
        config = {
            "run_id": run_id,
            "started_at": utc_now(),
            "target": requirements["target"]["id"],
            "host": disposable["host"],
            "root_prefix": disposable["root_prefix"],
            "port": disposable["port"],
            "max_connections": disposable["max_connections"],
            "superuser_reserved_connections": disposable[
                "superuser_reserved_connections"
            ],
            "max_replication_slots": disposable["max_replication_slots"],
            "postgresql_observed": requirements["target"][
                "postgresql_observed"
            ],
            "common_alert": requirements["exercise"]["common_alert"],
            "flow": requirements["flow_scenario"],
            "retention": requirements["retention_scenario"],
        }
        program = REMOTE_PROGRAM.replace(
            "__CONFIG_JSON__",
            repr(json.dumps(config, sort_keys=True)),
            1,
        )
        if "__CONFIG_JSON__" in program:
            raise LabError("remote configuration substitution failed")
        host = str(requirements["target"]["observer_address"])
        remote = run(
            ssh_base(args.ssh_user, host)
            + ["sudo", "-n", "-iu", "postgres", "python3", "-"],
            stdin=program,
            timeout=420,
        )
        try:
            evidence = json.loads(remote.stdout)
        except json.JSONDecodeError as exc:
            raise LabError("remote exercise returned invalid JSON") from exc
        if not isinstance(evidence, dict):
            raise LabError("remote exercise returned no object")
        if evidence.get("run_id") != run_id:
            raise LabError("remote exercise run identity drifted")
        write_json(args.output / "exercise-evidence.json", evidence)
        write_json(
            args.output / "blind-packets.json",
            evidence["blind_packets"],
        )
        write_json(
            args.output / "hidden-answers.json",
            evidence["hidden_answers"],
        )
        write_json(args.output / "cleanup.json", evidence["cleanup"])
        write_json(
            args.output / "source-manifest.json",
            source_manifest(args.source_dir),
        )
        write_json(
            args.output / "run-manifest.json",
            {
                "schema": "pg36-ch34-run-manifest-v1",
                "run_id": run_id,
                "created_at": utc_now(),
                "target": requirements["target"]["id"],
                "exercise_host": disposable["host"],
                "scenario_order": evidence["scenario_order"],
                "blind_case_ids": [
                    row["case_id"] for row in evidence["blind_packets"]
                ],
                "production_ch34_gate": "pending",
            },
        )
    except (
        KeyError,
        TypeError,
        OSError,
        LabError,
    ) as exc:
        print(f"exercise failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
