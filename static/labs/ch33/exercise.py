#!/usr/bin/env python3
"""Run a guarded process-failover drill and restore the teaching baseline."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import psycopg

from capture import (
    capture_node,
    capture_patroni,
    capture_phase,
)
from common import (
    LabError,
    read_json,
    run,
    service_env,
    sha256_file,
    ssh_base,
    utc_now,
    write_json,
)


OUTCOME_FILES = {"failover-run.json"}


def member_index(patroni: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = patroni.get("members")
    if not isinstance(rows, list):
        raise LabError("Patroni members are missing")
    result = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(result) != len(rows):
        raise LabError("Patroni member identity is duplicated")
    return result


def healthy_topology(
    patroni: dict[str, Any],
    leader: str,
    *,
    require_all: bool,
) -> bool:
    members = member_index(patroni)
    if require_all and set(members) != {
        "pg-test-1",
        "pg-test-2",
        "pg-test-3",
    }:
        return False
    primaries = [
        name
        for name, row in members.items()
        if row.get("role") == "primary"
    ]
    if primaries != [leader]:
        return False
    if members.get(leader, {}).get("state") != "running":
        return False
    for name, row in members.items():
        if name == leader:
            continue
        if row.get("role") == "primary":
            return False
        if require_all and (
            row.get("role") != "replica"
            or row.get("state") != "streaming"
        ):
            return False
    return True


def sole_leader(patroni: dict[str, Any]) -> str | None:
    leaders = [
        name
        for name, row in member_index(patroni).items()
        if row.get("role") == "primary"
        and row.get("state") == "running"
    ]
    return leaders[0] if len(leaders) == 1 else None


def automatic_failover_topology(
    patroni: dict[str, Any],
    eligible: set[str],
) -> str | None:
    members = member_index(patroni)
    leader = sole_leader(patroni)
    if leader not in eligible:
        return None
    other_candidates = eligible - {leader}
    if any(
        members.get(name, {}).get("role") != "replica"
        or members.get(name, {}).get("state") != "streaming"
        for name in other_candidates
    ):
        return None
    old = members.get("pg-test-1")
    if old is not None and old.get("role") == "primary":
        return None
    return leader


def require_service_file(
    path: Path,
    requirements: dict[str, Any],
) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
    ):
        raise LabError("private service file must be a regular mode-0600 file")
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as exc:
        raise LabError(f"cannot parse private service file: {exc}") from exc
    if not parser.has_section("pg36-ch33"):
        raise LabError("private service file lacks [pg36-ch33]")
    actual = parser["pg36-ch33"]
    probe = requirements["client_probe"]
    expected = {
        "host": str(probe["service_host"]),
        "port": str(probe["service_port"]),
        "dbname": str(probe["database"]),
        "user": str(probe["user"]),
        "sslmode": str(probe["sslmode"]),
        "target_session_attrs": str(probe["target_session_attrs"]),
    }
    if any(actual.get(key) != value for key, value in expected.items()):
        raise LabError("private service endpoint drifted from requirements")
    if not actual.get("password"):
        raise LabError("private service credential is empty")


def require_preflight(
    phase: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    if not healthy_topology(
        phase["patroni"],
        "pg-test-1",
        require_all=True,
    ):
        raise LabError("preflight topology is not the retained baseline")
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
        raise LabError("Patroni dynamic failover policy drifted")
    if policy.get("pause") is not False:
        raise LabError("Patroni automatic failover is paused")
    postgresql = policy.get("postgresql", {})
    if (
        postgresql.get("use_pg_rewind") is not True
        or postgresql.get("use_slots") is not True
    ):
        raise LabError("Patroni rewind or slot policy drifted")
    sql = phase["postgres"]
    if any(row.get("available") is not True for row in sql.values()):
        raise LabError("one or more PostgreSQL members are unavailable")
    system_ids = {
        str(row.get("system_identifier"))
        for row in sql.values()
    }
    if len(system_ids) != 1:
        raise LabError("managed members do not share one system identifier")
    for name, row in sql.items():
        expected_recovery = name != "pg-test-1"
        if row.get("in_recovery") is not expected_recovery:
            raise LabError(f"SQL role drifted for {name}")
    senders = sql["pg-test-1"].get("senders", [])
    maximum = expected["maximum_lag_on_failover_bytes"]
    if (
        len(senders) != 2
        or any(
            row.get("state") != "streaming"
            or row.get("replay_gap_bytes") is None
            or int(row["replay_gap_bytes"]) > maximum
            for row in senders
        )
    ):
        raise LabError("preflight replica lag exceeds failover policy")


def require_fixture_absent(service_file: Path) -> None:
    with psycopg.connect(
        "service=pg36-ch33",
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regnamespace('pg36_ch33') IS NULL
                """
            )
            row = cursor.fetchone()
    if row is None or row[0] is not True:
        raise LabError("chapter 33 fixture schema already exists")


def setup_fixture(
    source_dir: Path,
    service_file: Path,
    run_id: str,
) -> None:
    run(
        [
            "psql",
            "-X",
            "-w",
            "--dbname=service=pg36-ch33",
            "--set=ON_ERROR_STOP=1",
            "--set",
            f"run_id={run_id}",
            "--file",
            str(source_dir / "setup.sql"),
        ],
        env=service_env(service_file),
    )


def cleanup_fixture(
    service_file: Path,
    run_id: str,
) -> dict[str, Any]:
    with psycopg.connect(
        "service=pg36-ch33",
        autocommit=False,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    count(*) = 1,
                    bool_and(external_dispatch_enabled IS FALSE)
                FROM pg36_ch33.run_marker
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None or row != (True, True):
                raise LabError("fixture marker identity guard failed")
            cursor.execute("DROP SCHEMA pg36_ch33 CASCADE")
        connection.commit()
    with psycopg.connect(
        "service=pg36-ch33",
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regnamespace('pg36_ch33') IS NULL"
            )
            removed = bool(cursor.fetchone()[0])
    return {
        "schema": "pg36-ch33-fixture-cleanup-v1",
        "run_id": run_id,
        "marker_matched": True,
        "schema_removed": removed,
        "external_dispatch_count": 0,
        "completed_at": utc_now(),
    }


def start_probe(
    source_dir: Path,
    service_file: Path,
    output: Path,
    requirements: dict[str, Any],
    run_id: str,
) -> subprocess.Popen[str]:
    probe = requirements["client_probe"]
    stdout = (output / "client-probe.stdout").open(
        "x", encoding="utf-8"
    )
    stderr = (output / "client-probe.stderr").open(
        "x", encoding="utf-8"
    )
    stdout_path = output / "client-probe.stdout"
    stderr_path = output / "client-probe.stderr"
    stdout_path.chmod(0o600)
    stderr_path.chmod(0o600)
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
    timeout: float = 12,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_file.exists():
            return
        if process.poll() is not None:
            raise LabError("client probe exited before its first acknowledgement")
        time.sleep(0.1)
    raise LabError("client probe did not become ready")


def service_action(
    requirements: dict[str, Any],
    user: str,
    action: str,
) -> dict[str, Any]:
    if action not in {"start", "stop"}:
        raise LabError("unsupported service action")
    host = str(requirements["members"]["pg-test-1"]["address"])
    started_at = utc_now()
    started_ns = time.monotonic_ns()
    result = run(
        ssh_base(user, host)
        + ["sudo", "-n", "systemctl", action, "patroni"],
        timeout=45,
    )
    finished_ns = time.monotonic_ns()
    return {
        "schema": "pg36-ch33-service-action-v1",
        "kind": f"controlled-patroni-{action}",
        "member": "pg-test-1",
        "address": host,
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


def require_process_fence(node: dict[str, Any]) -> None:
    if (
        node.get("member_name") != "pg-test-1"
        or node.get("service_active") is not False
        or node.get("postmaster_alive") is not False
        or node.get("patroni_rest_reachable") is not False
    ):
        raise LabError("old primary process fence is incomplete")


def wait_topology(
    requirements: dict[str, Any],
    user: str,
    leader: str,
    *,
    require_all: bool,
    timeout: float,
) -> tuple[dict[str, Any], int]:
    observer = str(requirements["members"]["pg-test-3"]["address"])
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = capture_patroni(user, observer)
            if healthy_topology(
                last,
                leader,
                require_all=require_all,
            ):
                return last, time.monotonic_ns()
        except LabError:
            pass
        time.sleep(0.25)
    raise LabError(
        f"topology did not stabilize on {leader}: {last}"
    )


def wait_automatic_failover(
    requirements: dict[str, Any],
    user: str,
    timeout: float,
) -> tuple[dict[str, Any], str, int]:
    observer = str(requirements["members"]["pg-test-3"]["address"])
    eligible = set(
        requirements["managed_failover"]["eligible_candidates"]
    )
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = capture_patroni(user, observer)
            leader = automatic_failover_topology(last, eligible)
            if leader is not None:
                return last, leader, time.monotonic_ns()
        except LabError:
            pass
        time.sleep(0.25)
    raise LabError(
        f"automatic failover did not select an eligible replica: {last}"
    )


def planned_switchover(
    requirements: dict[str, Any],
    user: str,
    leader: str,
    candidate: str,
) -> dict[str, Any]:
    host = str(requirements["members"]["pg-test-3"]["address"])
    started_at = utc_now()
    started_ns = time.monotonic_ns()
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
        "schema": "pg36-ch33-baseline-action-v1",
        "kind": "planned-switchover",
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


def journal_projection(
    requirements: dict[str, Any],
    user: str,
    since_epoch: int,
) -> dict[str, Any]:
    host = str(requirements["members"]["pg-test-1"]["address"])
    program = r"""
import hashlib
import json
import subprocess
import sys

since = sys.argv[1]
result = subprocess.run(
    [
        "journalctl", "-u", "patroni", "--since", "@" + since,
        "--no-pager", "--output=short-iso",
    ],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
text = result.stdout
lower = text.lower()
patterns = {
    "pg_rewind": "pg_rewind",
    "different_leader": "different leader",
    "secondary": "secondary",
    "following": "following",
    "streaming": "streaming",
}
print(json.dumps({
    "return_code": result.returncode,
    "line_count": len(text.splitlines()),
    "sha256": hashlib.sha256(text.encode()).hexdigest(),
    "pattern_counts": {
        key: lower.count(pattern)
        for key, pattern in patterns.items()
    },
    "raw_log_exported": False,
}))
"""
    raw = run(
        ssh_base(user, host)
        + [
            "sudo",
            "-n",
            "python3",
            "-",
            str(since_epoch),
        ],
        stdin=program,
    ).stdout
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LabError("journal projection returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LabError("journal projection returned no object")
    value["schema"] = "pg36-ch33-journal-projection-v1"
    value["member"] = "pg-test-1"
    return value


def parse_events(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("outcome") == "summary":
            summary = value
        else:
            events.append(value)
    if summary is None:
        raise LabError("client probe summary is missing")
    return events, summary


def reconcile_client(
    service_file: Path,
    run_id: str,
    events_path: Path,
    action: dict[str, Any],
    stable_ns: int,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    events, summary = parse_events(events_path)
    acknowledged = [
        row for row in events if row.get("outcome") == "acknowledged"
    ]
    unknown = [row for row in events if row.get("outcome") == "unknown"]
    with psycopg.connect(
        "service=pg36-ch33",
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT attempt_no, token
                FROM pg36_ch33.write_probe
                WHERE run_id = %s
                ORDER BY attempt_no
                """,
                (run_id,),
            )
            persisted = {
                int(attempt): str(token)
                for attempt, token in cursor.fetchall()
            }
            cursor.execute(
                """
                SELECT count(*) - count(DISTINCT token)
                FROM pg36_ch33.write_probe
                WHERE run_id = %s
                """,
                (run_id,),
            )
            duplicate_tokens = int(cursor.fetchone()[0])
    missing_acknowledged = [
        row["attempt_no"]
        for row in acknowledged
        if persisted.get(int(row["attempt_no"])) != row["token"]
    ]
    unknown_outcomes = [
        {
            "attempt_no": int(row["attempt_no"]),
            "committed": (
                persisted.get(int(row["attempt_no"])) == row["token"]
            ),
        }
        for row in unknown
    ]
    ack_times = sorted(
        int(row["attempt_finished_monotonic_ns"])
        for row in acknowledged
    )
    gaps = [
        (right - left) / 1_000_000
        for left, right in zip(ack_times, ack_times[1:])
    ]
    before_action = [
        row
        for row in acknowledged
        if int(row["attempt_finished_monotonic_ns"])
        <= int(action["started_monotonic_ns"])
    ]
    after_stable = [
        row
        for row in acknowledged
        if int(row["attempt_finished_monotonic_ns"]) >= stable_ns
    ]
    if not before_action or not after_stable:
        raise LabError("client probe did not bracket the failover")
    initial_timelines = {
        int(row["timeline"])
        for row in before_action
    }
    if len(initial_timelines) != 1:
        raise LabError("pre-failover client timeline is ambiguous")
    initial_timeline = next(iter(initial_timelines))
    new_primary = [
        row
        for row in acknowledged
        if int(row["timeline"]) > initial_timeline
    ]
    if not new_primary:
        raise LabError("client probe observed no advanced failover timeline")
    maximum_gap = max(gaps, default=0.0)
    return {
        "schema": "pg36-ch33-client-reconciliation-v1",
        "run_id": run_id,
        "attempts": int(summary["attempts"]),
        "acknowledged": len(acknowledged),
        "unknown": len(unknown),
        "persisted_rows": len(persisted),
        "acknowledged_missing": len(missing_acknowledged),
        "duplicate_tokens": duplicate_tokens,
        "unreconciled_unknown_outcomes": 0,
        "unknown_outcome_resolution": unknown_outcomes,
        "backend_attribution": (
            "timeline-plus-patroni-topology;"
            "inet_server_addr-is-null-on-unix-socket-route"
        ),
        "initial_timeline": initial_timeline,
        "failover_timeline": min(
            int(row["timeline"]) for row in new_primary
        ),
        "old_timeline_acknowledged": sum(
            int(row["timeline"]) == initial_timeline
            for row in acknowledged
        ),
        "new_primary_acknowledged": len(new_primary),
        "last_ack_before_action_attempt": int(
            before_action[-1]["attempt_no"]
        ),
        "first_ack_after_stable_attempt": int(
            after_stable[0]["attempt_no"]
        ),
        "first_new_primary_ack_attempt": int(
            new_primary[0]["attempt_no"]
        ),
        "maximum_ack_gap_ms": maximum_gap,
        "measurement_resolution_ms": (
            float(requirements["client_probe"]["interval_seconds"])
            * 1000
        ),
        "control_plane_failover_ms": (
            stable_ns - int(action["started_monotonic_ns"])
        )
        / 1_000_000,
        "passed": (
            len(acknowledged)
            >= int(
                requirements["client_probe"][
                    "minimum_acknowledged_attempts"
                ]
            )
            and not missing_acknowledged
            and duplicate_tokens == 0
            and maximum_gap
            <= float(
                requirements["client_probe"][
                    "maximum_observed_write_gap_ms"
                ]
            )
        ),
    }


def choose_dcs_tabletop(
    source_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    model = read_json(source_dir / "failure-model.json")
    scenarios = model["dcs_scenarios"]
    selected = secrets.choice(scenarios)
    return {
        "schema": "pg36-ch33-dcs-tabletop-v1",
        "run_id": run_id,
        "draw_method": "system-random-choice",
        "scenario_count": len(scenarios),
        "drawn": selected,
        "live_dcs_fault_injected": False,
        "live_network_partition_injected": False,
        "leader_key_deleted": False,
        "decision_only": True,
        "production_action_authorized": False,
    }


def source_manifest(
    source_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    return {
        "schema": "pg36-ch33-drill-manifest-v1",
        "run_id": run_id,
        "captured_at": utc_now(),
        "target": "pg36-l2-vagrant/pg-test",
        "mode": "controlled-process-failover-rejoin-and-baseline-restore",
        "production_approval": False,
        "secret_values_exported": 0,
        "source_sha256": {
            path.name: sha256_file(path)
            for path in sorted(source_dir.iterdir())
            if path.is_file() and path.name not in OUTCOME_FILES
        },
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


def main() -> int:
    args = parse_args()
    requirements = read_json(args.requirements)
    run_id = str(uuid.uuid4())
    probe_process: subprocess.Popen[str] | None = None
    service_stopped = False
    fixture_created = False
    baseline_restored = False
    selected_leader: str | None = None
    try:
        if (
            args.target_token != requirements["target"]["id"]
            or args.target_token != "pg36-l2-vagrant/pg-test"
            or args.confirmation
            != "FENCE_FAILOVER_REJOIN_REBUILD_CH33"
            or args.authority != "nonproduction-no-data-no-traffic"
            or requirements["target"]["production_data_permitted"] is not False
            or requirements["target"]["production_traffic_permitted"]
            is not False
        ):
            raise LabError("direct exercise authority guard failed")
        require_service_file(args.service_file, requirements)
        os.environ["PGSERVICEFILE"] = str(args.service_file)
        os.environ["PGSERVICE"] = "pg36-ch33"
        if args.output.exists() and any(args.output.iterdir()):
            raise LabError("refusing to overwrite a non-empty exercise directory")
        args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.chmod(0o700)
        before = capture_phase(requirements, args.ssh_user, "before")
        require_preflight(before, requirements)
        require_fixture_absent(args.service_file)
        write_json(args.output / "before.json", before)

        setup_fixture(args.source_dir, args.service_file, run_id)
        fixture_created = True
        write_json(
            args.output / "dcs-tabletop.json",
            choose_dcs_tabletop(args.source_dir, run_id),
        )

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

        journal_since = int(time.time()) - 1
        stop_action = service_action(
            requirements,
            args.ssh_user,
            "stop",
        )
        service_stopped = True
        write_json(args.output / "stop-action.json", stop_action)
        fence = capture_node(
            args.ssh_user,
            str(requirements["members"]["pg-test-1"]["address"]),
        )
        require_process_fence(fence)
        fence["verified_at"] = utc_now()
        fence["verified_monotonic_ns"] = time.monotonic_ns()
        write_json(args.output / "old-primary-fence.json", fence)

        failed_patroni, selected_leader, stable_ns = wait_automatic_failover(
            requirements,
            args.ssh_user,
            timeout=float(
                requirements["managed_failover"][
                    "promotion_timeout_seconds"
                ]
            ),
        )
        if int(fence["verified_monotonic_ns"]) > stable_ns:
            raise LabError("candidate stabilized before fence evidence")
        failed = capture_phase(requirements, args.ssh_user, "failed")
        if automatic_failover_topology(
            failed_patroni,
            set(
                requirements["managed_failover"][
                    "eligible_candidates"
                ]
            ),
        ) != selected_leader:
            raise LabError("failed topology is not safe")
        failed["selected_leader"] = selected_leader
        failed["stable_monotonic_ns"] = stable_ns
        failed["stable_at"] = utc_now()
        write_json(args.output / "failed.json", failed)

        start_action = service_action(
            requirements,
            args.ssh_user,
            "start",
        )
        service_stopped = False
        write_json(args.output / "start-action.json", start_action)
        _, rejoined_ns = wait_topology(
            requirements,
            args.ssh_user,
            selected_leader,
            require_all=True,
            timeout=float(
                requirements["managed_failover"][
                    "rejoin_timeout_seconds"
                ]
            ),
        )
        rejoined = capture_phase(
            requirements,
            args.ssh_user,
            "rejoined",
        )
        if not healthy_topology(
            rejoined["patroni"],
            selected_leader,
            require_all=True,
        ):
            raise LabError("old primary did not rejoin as a streaming replica")
        rejoined["stable_monotonic_ns"] = rejoined_ns
        rejoined["stable_at"] = utc_now()
        write_json(args.output / "rejoined.json", rejoined)
        write_json(
            args.output / "journal-projection.json",
            journal_projection(
                requirements,
                args.ssh_user,
                journal_since,
            ),
        )

        probe_timeout = (
            float(requirements["client_probe"]["duration_seconds"]) + 15
        )
        probe_return = probe_process.wait(timeout=probe_timeout)
        close_probe_streams(probe_process)
        if probe_return != 0:
            raise LabError(
                f"client probe failed with exit {probe_return}"
            )
        client = reconcile_client(
            args.service_file,
            run_id,
            args.output / "client-events.jsonl",
            stop_action,
            stable_ns,
            requirements,
        )
        if client["passed"] is not True:
            raise LabError("client reconciliation did not pass")
        write_json(args.output / "client-reconciliation.json", client)

        restore_action = planned_switchover(
            requirements,
            args.ssh_user,
            selected_leader,
            "pg-test-1",
        )
        write_json(
            args.output / "baseline-restore-action.json",
            restore_action,
        )
        _, restored_ns = wait_topology(
            requirements,
            args.ssh_user,
            "pg-test-1",
            require_all=True,
            timeout=float(
                requirements["managed_failover"][
                    "baseline_restore_timeout_seconds"
                ]
            ),
        )
        baseline_restored = True
        restored = capture_phase(
            requirements,
            args.ssh_user,
            "restored",
        )
        if not healthy_topology(
            restored["patroni"],
            "pg-test-1",
            require_all=True,
        ):
            raise LabError("teaching baseline was not restored")
        restored["stable_monotonic_ns"] = restored_ns
        restored["stable_at"] = utc_now()
        write_json(args.output / "restored.json", restored)

        cleanup = cleanup_fixture(args.service_file, run_id)
        fixture_created = False
        write_json(args.output / "fixture-cleanup.json", cleanup)
        write_json(
            args.output / "drill-manifest.json",
            source_manifest(args.source_dir, run_id),
        )
    except (
        LabError,
        KeyError,
        TypeError,
        OSError,
        json.JSONDecodeError,
        psycopg.Error,
        subprocess.TimeoutExpired,
    ) as exc:
        if probe_process is not None and probe_process.poll() is None:
            probe_process.terminate()
            try:
                probe_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                probe_process.kill()
                probe_process.wait(timeout=5)
        close_probe_streams(probe_process)
        if service_stopped:
            try:
                service_action(requirements, args.ssh_user, "start")
                service_stopped = False
            except Exception as recovery_error:
                print(
                    f"automatic member restart failed: {recovery_error}",
                    file=sys.stderr,
                )
        if not baseline_restored:
            try:
                current = capture_patroni(
                    args.ssh_user,
                    str(
                        requirements["members"]["pg-test-3"]["address"]
                    ),
                )
                current_leader = sole_leader(current)
                if current_leader == "pg-test-1":
                    wait_topology(
                        requirements,
                        args.ssh_user,
                        "pg-test-1",
                        require_all=True,
                        timeout=60,
                    )
                    baseline_restored = True
                elif current_leader in set(
                    requirements["managed_failover"][
                        "eligible_candidates"
                    ]
                ):
                    wait_topology(
                        requirements,
                        args.ssh_user,
                        current_leader,
                        require_all=True,
                        timeout=60,
                    )
                    planned_switchover(
                        requirements,
                        args.ssh_user,
                        current_leader,
                        "pg-test-1",
                    )
                    wait_topology(
                        requirements,
                        args.ssh_user,
                        "pg-test-1",
                        require_all=True,
                        timeout=60,
                    )
                    baseline_restored = True
            except Exception as recovery_error:
                print(
                    "automatic safe baseline restore failed; "
                    f"inspect pg-test before any new action: {recovery_error}",
                    file=sys.stderr,
                )
        if fixture_created and baseline_restored:
            try:
                cleanup_fixture(args.service_file, run_id)
                fixture_created = False
            except Exception as cleanup_error:
                print(
                    f"exact fixture cleanup failed: {cleanup_error}",
                    file=sys.stderr,
                )
        print(f"managed failover exercise failed: {exc}", file=sys.stderr)
        return 1
    finally:
        close_probe_streams(probe_process)

    print("status=managed-failover-ok")
    print(f"run_id={run_id}")
    print(f"failed_over=pg-test-1-to-{selected_leader}")
    print("old_primary_rejoined=streaming")
    print("baseline_restored=pg-test-1")
    print("production_approval=false")
    print(f"evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
