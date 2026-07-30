#!/usr/bin/env python3
"""Run one guarded planned switchover and restore the teaching baseline."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from capture import (
    CaptureError,
    capture_patroni,
    capture_phase,
    read_json,
    ssh_base,
    write_json,
)

OUTCOME_FILES = {"drill-run.json", "migration-effort.json"}


class DrillError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DrillError(f"cannot execute {args[0]}: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else f"exit {result.returncode}"
        raise DrillError(f"command failed ({args[0]}): {detail}")
    return result


def service_env(service_file: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PGSERVICEFILE"] = str(service_file)
    environment["PGSERVICE"] = "pg36-ch20"
    return environment


def validate_service_file(
    service_file: Path,
    requirements: dict[str, Any],
) -> None:
    try:
        mode = stat.S_IMODE(service_file.stat().st_mode)
    except OSError as exc:
        raise DrillError(f"cannot stat private service file: {exc}") from exc
    if (
        mode != 0o600
        or not service_file.is_file()
        or service_file.is_symlink()
    ):
        raise DrillError("private service file must be a regular mode-0600 file")
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with service_file.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as exc:
        raise DrillError(f"cannot parse private service file: {exc}") from exc
    if not parser.has_section("pg36-ch20"):
        raise DrillError("private service file lacks [pg36-ch20]")
    actual = parser["pg36-ch20"]
    expected = requirements["client_probe"]
    checks = {
        "host": str(expected["service_host"]),
        "port": str(expected["service_port"]),
        "dbname": str(expected["database"]),
        "user": str(expected["user"]),
        "sslmode": str(expected["sslmode"]),
        "target_session_attrs": str(expected["target_session_attrs"]),
    }
    if any(actual.get(key) != value for key, value in checks.items()):
        raise DrillError("private service endpoint drifted from the lab contract")
    if not actual.get("password"):
        raise DrillError("private service credential is missing")


def setup_fixture(source_dir: Path, service_file: Path) -> None:
    run(
        [
            "psql",
            "-X",
            "-w",
            "--dbname=service=pg36-ch20",
            "--set=ON_ERROR_STOP=1",
            "--file",
            str(source_dir / "setup.sql"),
        ],
        env=service_env(service_file),
    )


def member_index(patroni: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = patroni.get("members")
    if not isinstance(rows, list):
        raise DrillError("Patroni members are missing")
    result = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(result) != len(rows):
        raise DrillError("Patroni member identity is duplicated")
    return result


def topology_stable(
    patroni: dict[str, Any],
    expected_leader: str,
) -> bool:
    members = member_index(patroni)
    if set(members) != {"pg-test-1", "pg-test-2", "pg-test-3"}:
        return False
    leaders = [
        name
        for name, row in members.items()
        if row.get("role") == "primary"
    ]
    if leaders != [expected_leader]:
        return False
    for name, row in members.items():
        expected_state = "running" if name == expected_leader else "streaming"
        if row.get("state") != expected_state:
            return False
    return True


def require_preflight(
    phase: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    if not topology_stable(phase["patroni"], "pg-test-1"):
        raise DrillError("preflight topology is not the retained chapter-19 baseline")
    policy = phase["dynamic_policy"]
    expected = requirements["expected_dynamic_policy"]
    checks = {
        "ttl": expected["ttl_seconds"],
        "loop_wait": expected["loop_wait_seconds"],
        "retry_timeout": expected["retry_timeout_seconds"],
        "maximum_lag_on_failover": expected[
            "maximum_lag_on_failover_bytes"
        ],
        "synchronous_mode": expected["synchronous_mode"],
        "synchronous_mode_strict": expected["synchronous_mode_strict"],
        "failsafe_mode": expected["failsafe_mode"],
    }
    if any(policy.get(key) != value for key, value in checks.items()):
        raise DrillError("Patroni dynamic policy drifted from the drill contract")
    if policy.get("pause") is not False:
        raise DrillError("Patroni is paused")
    postgresql = policy.get("postgresql", {})
    if (
        postgresql.get("use_pg_rewind") is not expected["use_pg_rewind"]
        or postgresql.get("use_slots") is not expected["use_slots"]
    ):
        raise DrillError("Patroni rewind/slot policy drifted")

    postgres = phase["postgres"]
    system_ids = {
        str(row.get("system_identifier"))
        for row in postgres.values()
    }
    if len(system_ids) != 1:
        raise DrillError("members do not share one system identifier")
    members = requirements["members"]
    for name, contract in members.items():
        host = str(contract["address"])
        expected_recovery = name != "pg-test-1"
        if postgres[host].get("in_recovery") is not expected_recovery:
            raise DrillError(f"SQL role drifted for {name}")
    primary = postgres[members["pg-test-1"]["address"]]
    senders = primary.get("senders", [])
    if len(senders) != 2:
        raise DrillError("primary does not see two replication senders")
    max_lag = requirements["topology_acceptance"][
        "maximum_pre_switch_replay_lag_bytes"
    ]
    if any(
        row.get("state") != "streaming"
        or row.get("replay_gap_bytes") is None
        or int(row["replay_gap_bytes"]) > max_lag
        for row in senders
    ):
        raise DrillError("replica replay gap is outside the switchover preflight")


def wait_for_topology(
    requirements: dict[str, Any],
    user: str,
    expected_leader: str,
) -> tuple[dict[str, Any], int]:
    observer = str(
        requirements["members"]["pg-test-3"]["address"]
    )
    timeout = float(
        requirements["topology_acceptance"]["stable_timeout_seconds"]
    )
    started = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = capture_patroni(user, observer)
            if topology_stable(last, expected_leader):
                return last, time.monotonic_ns()
        except CaptureError:
            pass
        time.sleep(0.5)
    raise DrillError(
        f"topology did not stabilize on {expected_leader}: {last}"
    )


def switchover(
    requirements: dict[str, Any],
    user: str,
    leader: str,
    candidate: str,
) -> dict[str, Any]:
    members = requirements["members"]
    host = str(members[leader]["address"])
    started_ns = time.monotonic_ns()
    started_at = utc_now()
    result = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "switchover",
            "pg-test",
            "--leader",
            leader,
            "--candidate",
            candidate,
            "--force",
        ],
        timeout=60,
    )
    finished_ns = time.monotonic_ns()
    return {
        "schema": "pg36-ch20-action-v1",
        "kind": "planned-switchover",
        "executor": "patronictl",
        "cluster": "pg-test",
        "leader": leader,
        "candidate": candidate,
        "started_at": started_at,
        "started_monotonic_ns": started_ns,
        "finished_at": utc_now(),
        "finished_monotonic_ns": finished_ns,
        "duration_ms": (finished_ns - started_ns) / 1_000_000,
        "return_code": result.returncode,
        "stdout_sha256": hashlib.sha256(
            result.stdout.encode("utf-8")
        ).hexdigest(),
        "stderr_empty": not bool(result.stderr.strip()),
    }


def read_probe_events(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("outcome") == "summary":
            summary = value
        else:
            events.append(value)
    if summary is None:
        raise DrillError("client probe summary is missing")
    return events, summary


def reconcile(
    service_file: Path,
    run_id: str,
    probe_path: Path,
    action: dict[str, Any],
    stable_ns: int,
) -> dict[str, Any]:
    events, summary = read_probe_events(probe_path)
    old_service_file = os.environ.get("PGSERVICEFILE")
    old_service = os.environ.get("PGSERVICE")
    os.environ["PGSERVICEFILE"] = str(service_file)
    os.environ["PGSERVICE"] = "pg36-ch20"
    try:
        with psycopg.connect(
            "service=pg36-ch20",
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT attempt_no, token, committed_at
                    FROM pg36_ch20.write_probe
                    WHERE run_id = %s
                    ORDER BY attempt_no
                    """,
                    (run_id,),
                )
                rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM (
                        SELECT token
                        FROM pg36_ch20.write_probe
                        WHERE run_id = %s
                        GROUP BY token
                        HAVING count(*) > 1
                    ) AS duplicated
                    """,
                    (run_id,),
                )
                duplicate_tokens = int(cursor.fetchone()[0])
    finally:
        if old_service_file is None:
            os.environ.pop("PGSERVICEFILE", None)
        else:
            os.environ["PGSERVICEFILE"] = old_service_file
        if old_service is None:
            os.environ.pop("PGSERVICE", None)
        else:
            os.environ["PGSERVICE"] = old_service

    persisted = {
        str(token): {
            "attempt_no": int(attempt_no),
            "committed_at": committed_at.isoformat(),
        }
        for attempt_no, token, committed_at in rows
    }
    acknowledged = [
        event
        for event in events
        if event.get("outcome") == "acknowledged"
    ]
    unknown = [
        event
        for event in events
        if event.get("outcome") == "unknown"
    ]
    acknowledged_missing = [
        str(event["token"])
        for event in acknowledged
        if str(event["token"]) not in persisted
    ]
    unknown_committed = [
        str(event["token"])
        for event in unknown
        if str(event["token"]) in persisted
    ]
    unknown_absent = [
        str(event["token"])
        for event in unknown
        if str(event["token"]) not in persisted
    ]

    ack_times = sorted(
        int(event["attempt_finished_monotonic_ns"])
        for event in acknowledged
    )
    action_started_ns = int(action["started_monotonic_ns"])
    before = [value for value in ack_times if value <= action_started_ns]
    after_stable = [value for value in ack_times if value >= stable_ns]
    if not before or not after_stable:
        raise DrillError(
            "probe does not bracket the switchover and stable topology"
        )
    conservative_write_gap_ms = (
        min(after_stable) - max(before)
    ) / 1_000_000
    transition_adjacent_gaps = [
        (right - left) / 1_000_000
        for left, right in zip(ack_times, ack_times[1:])
        if left <= stable_ns and right >= action_started_ns
    ]
    if not transition_adjacent_gaps:
        raise DrillError("no adjacent acknowledged probe events bracket transition")

    timeline_hex = sorted(
        {
            str(event.get("timeline_hex"))
            for event in acknowledged
            if event.get("timeline_hex")
        }
    )
    return {
        "schema": "pg36-ch20-reconciliation-v1",
        "run_id": run_id,
        "status": "reconciled",
        "probe_summary": summary,
        "counts": {
            "events": len(events),
            "acknowledged": len(acknowledged),
            "unknown": len(unknown),
            "persisted_rows": len(persisted),
            "acknowledged_rows_missing": len(acknowledged_missing),
            "duplicate_tokens": duplicate_tokens,
            "unknown_committed": len(unknown_committed),
            "unknown_absent": len(unknown_absent),
            "unreconciled_unknown_outcomes": 0,
        },
        "metrics": {
            "action_command_ms": action["duration_ms"],
            "action_to_stable_ms": (
                stable_ns - action_started_ns
            )
            / 1_000_000,
            "conservative_write_gap_ms": conservative_write_gap_ms,
            "maximum_adjacent_ack_gap_ms": max(
                transition_adjacent_gaps
            ),
            "probe_interval_seconds": (
                None
                if len(events) < 2
                else (
                    int(events[1]["attempt_started_monotonic_ns"])
                    - int(events[0]["attempt_started_monotonic_ns"])
                )
                / 1_000_000_000
            ),
        },
        "timeline_hex_seen": timeline_hex,
        "acknowledged_missing_tokens": acknowledged_missing,
        "unknown_committed_tokens": unknown_committed,
        "unknown_absent_tokens": unknown_absent,
        "interpretation": (
            "an error after send is outcome-unknown until token lookup; "
            "absence is not silently retried as a new business action"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--service-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--authority", required=True)
    return parser.parse_args()


def write_manifest(
    output: Path,
    source_dir: Path,
    requirements: dict[str, Any],
    run_id: str,
) -> None:
    manifest = {
        "schema": "pg36-ch20-drill-manifest-v1",
        "release": requirements["release"],
        "captured_at": utc_now(),
        "target": requirements["target"]["id"],
        "run_id": run_id,
        "mode": "planned-switchover-and-planned-baseline-restore",
        "production_approval": False,
        "unplanned_failure_injected": False,
        "secret_values_exported": 0,
        "source_sha256": {
            path.name: sha256(path)
            for path in sorted(source_dir.iterdir())
            if path.is_file() and path.name not in OUTCOME_FILES
        },
    }
    write_json(output / "drill-manifest.json", manifest)


def start_probe(
    source_dir: Path,
    service_file: Path,
    output: Path,
    requirements: dict[str, Any],
    run_id: str,
) -> subprocess.Popen[str]:
    probe = requirements["client_probe"]
    stdout = (output / "client-probe.stdout").open(
        "w", encoding="utf-8"
    )
    stderr = (output / "client-probe.stderr").open(
        "w", encoding="utf-8"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(source_dir / "client_probe.py"),
            "--run-id",
            run_id,
            "--output",
            str(output / "client-events.jsonl"),
            "--ready-file",
            str(output / "client-ready.json"),
            "--duration",
            str(probe["duration_seconds"]),
            "--interval",
            str(probe["interval_seconds"]),
        ],
        stdout=stdout,
        stderr=stderr,
        text=True,
        env=service_env(service_file),
    )
    process._pg36_stdout = stdout  # type: ignore[attr-defined]
    process._pg36_stderr = stderr  # type: ignore[attr-defined]
    return process


def close_probe_streams(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    for name in ("_pg36_stdout", "_pg36_stderr"):
        stream = getattr(process, name, None)
        if stream is not None:
            stream.close()


def wait_probe_ready(
    process: subprocess.Popen[str],
    ready_file: Path,
    timeout: float = 10,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_file.exists():
            return
        if process.poll() is not None:
            raise DrillError("client probe exited before its first acknowledgement")
        time.sleep(0.1)
    raise DrillError("client probe did not become ready")


def main() -> int:
    args = parse_args()
    requirements = read_json(args.requirements)
    run_id = str(uuid.uuid4())
    probe_process: subprocess.Popen[str] | None = None
    restored = False
    try:
        if (
            args.target_token != "pg36-l2-vagrant/pg-test"
            or args.target_token != requirements["target"]["id"]
            or args.confirmation
            != "SWITCH_CH20_PG_TEST_1_TO_2_AND_BACK"
            or args.authority
            != "nonproduction-no-data-no-traffic"
            or requirements["target"]["production_data_permitted"] is not False
            or requirements["target"]["production_traffic_permitted"] is not False
        ):
            raise DrillError("direct drill authority guard failed")
        validate_service_file(args.service_file, requirements)
        if args.output.exists() and any(args.output.iterdir()):
            raise DrillError("refusing to overwrite a non-empty drill directory")
        args.output.mkdir(parents=True, exist_ok=True)
        before = capture_phase(
            requirements,
            args.source_dir,
            args.ssh_user,
            "before",
        )
        require_preflight(before, requirements)
        write_json(args.output / "phases" / "before.json", before)
        setup_fixture(args.source_dir, args.service_file)

        probe_process = start_probe(
            args.source_dir,
            args.service_file,
            args.output,
            requirements,
            run_id,
        )
        wait_probe_ready(
            probe_process,
            args.output / "client-ready.json",
        )
        time.sleep(float(requirements["client_probe"]["warmup_seconds"]))

        pre_switch = capture_phase(
            requirements,
            args.source_dir,
            args.ssh_user,
            "pre-switch",
        )
        require_preflight(pre_switch, requirements)
        write_json(
            args.output / "phases" / "pre-switch.json",
            pre_switch,
        )

        forward = switchover(
            requirements,
            args.ssh_user,
            "pg-test-1",
            "pg-test-2",
        )
        write_json(args.output / "forward-action.json", forward)
        _, stable_ns = wait_for_topology(
            requirements,
            args.ssh_user,
            "pg-test-2",
        )
        forward["stable_monotonic_ns"] = stable_ns
        forward["stable_at"] = utc_now()
        write_json(args.output / "forward-action.json", forward)

        after = capture_phase(
            requirements,
            args.source_dir,
            args.ssh_user,
            "after-forward",
        )
        write_json(args.output / "phases" / "after-forward.json", after)

        probe_timeout = (
            float(requirements["client_probe"]["duration_seconds"]) + 10
        )
        probe_return_code = probe_process.wait(timeout=probe_timeout)
        close_probe_streams(probe_process)
        if probe_return_code != 0:
            raise DrillError(
                f"client probe failed with exit {probe_return_code}"
            )
        reconciliation = reconcile(
            args.service_file,
            run_id,
            args.output / "client-events.jsonl",
            forward,
            stable_ns,
        )
        write_json(
            args.output / "reconciliation.json",
            reconciliation,
        )

        restore = switchover(
            requirements,
            args.ssh_user,
            "pg-test-2",
            "pg-test-1",
        )
        write_json(args.output / "restore-action.json", restore)
        _, restored_stable_ns = wait_for_topology(
            requirements,
            args.ssh_user,
            "pg-test-1",
        )
        restore["stable_monotonic_ns"] = restored_stable_ns
        restore["stable_at"] = utc_now()
        write_json(args.output / "restore-action.json", restore)
        restored = True

        restored_phase = capture_phase(
            requirements,
            args.source_dir,
            args.ssh_user,
            "restored",
        )
        write_json(
            args.output / "phases" / "restored.json",
            restored_phase,
        )
        write_manifest(
            args.output,
            args.source_dir,
            requirements,
            run_id,
        )
    except (
        DrillError,
        CaptureError,
        KeyError,
        TypeError,
        OSError,
        json.JSONDecodeError,
        psycopg.Error,
        subprocess.TimeoutExpired,
    ) as error:
        if probe_process is not None and probe_process.poll() is None:
            probe_process.terminate()
            try:
                probe_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                probe_process.kill()
                probe_process.wait(timeout=5)
        close_probe_streams(probe_process)
        if not restored:
            try:
                current = capture_patroni(
                    args.ssh_user,
                    str(
                        requirements["members"]["pg-test-3"]["address"]
                    ),
                )
                if topology_stable(current, "pg-test-2"):
                    recovery = switchover(
                        requirements,
                        args.ssh_user,
                        "pg-test-2",
                        "pg-test-1",
                    )
                    write_json(
                        args.output / "emergency-restore-action.json",
                        recovery,
                    )
                    wait_for_topology(
                        requirements,
                        args.ssh_user,
                        "pg-test-1",
                    )
            except Exception as recovery_error:
                sys.stderr.write(
                    "automatic safe baseline restore failed; "
                    f"inspect pg-test before any new action: {recovery_error}\n"
                )
        sys.stderr.write(f"planned switchover drill failed: {error}\n")
        return 1
    finally:
        close_probe_streams(probe_process)

    print("status=drill-captured")
    print(f"run_id={run_id}")
    print("forward=pg-test-1-to-pg-test-2")
    print("restored=pg-test-2-to-pg-test-1")
    print("production_approval=false")
    print(f"evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
