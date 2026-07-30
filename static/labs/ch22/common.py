#!/usr/bin/env python3
"""Shared, secret-free helpers for the chapter 22 service lab."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shlex
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LabError(RuntimeError):
    """Raised when a command or evidence precondition fails."""


def utc_now(*, milliseconds: bool = False) -> str:
    now = datetime.now(timezone.utc)
    if not milliseconds:
        now = now.replace(microsecond=0)
    timespec = "milliseconds" if milliseconds else "seconds"
    return now.isoformat(timespec=timespec).replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run(
    args: list[str],
    *,
    stdin: str | None = None,
    timeout: float = 60,
    check: bool = True,
    env: dict[str, str] | None = None,
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
        raise LabError(f"cannot execute {args[0]}: {exc}") from exc
    if check and result.returncode != 0:
        details = result.stderr.strip().splitlines()
        if not details:
            details = result.stdout.strip().splitlines()
        detail = details[-1] if details else f"exit {result.returncode}"
        raise LabError(f"command failed ({args[0]}): {detail}")
    return result


def ssh_base(user: str, host: str) -> list[str]:
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "LogLevel=ERROR",
        f"{user}@{host}",
    ]


def ssh_command(
    user: str,
    host: str,
    remote_args: list[str],
    *,
    stdin: str | None = None,
    timeout: float = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        ssh_base(user, host) + [shlex.join(remote_args)],
        stdin=stdin,
        timeout=timeout,
        check=check,
    )


def remote_psql(
    user: str,
    host: str,
    database: str,
    sql: str,
    *,
    timeout: float = 30,
) -> str:
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "/usr/bin/psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-d",
            database,
            "--file=-",
        ],
        stdin=sql,
        timeout=timeout,
    )
    return result.stdout.strip()


def remote_json_psql(
    user: str,
    host: str,
    database: str,
    sql: str,
    *,
    timeout: float = 30,
) -> Any:
    output = remote_psql(user, host, database, sql, timeout=timeout)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise LabError(f"remote SQL did not return one JSON value: {exc}") from exc


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower().replace(" ", "-")
    if role in {"leader", "primary", "master"}:
        return "primary"
    if role in {"replica", "standby", "sync-standby"}:
        return "replica"
    return role


def patroni_list(user: str, host: str) -> dict[str, Any]:
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "list",
            "pg-test",
            "--format=json",
        ],
        timeout=20,
    )
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LabError(f"patronictl returned invalid JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise LabError("patronictl JSON is not a list")
    members: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise LabError("patronictl member is not an object")
        lower = {
            str(key).lower().replace(" ", "_"): value
            for key, value in row.items()
        }
        members.append(
            {
                "member": lower.get("member"),
                "host": lower.get("host"),
                "role": normalize_role(lower.get("role")),
                "state": str(lower.get("state", "")).lower(),
                "timeline": lower.get("tl", lower.get("timeline")),
                "receive_lsn": lower.get("receive_lsn"),
                "receive_lag_bytes": lower.get("receive_lag"),
                "replay_lsn": lower.get("replay_lsn"),
                "replay_lag_bytes": lower.get("replay_lag"),
            }
        )
    members.sort(key=lambda row: str(row["member"]))
    return {
        "schema": "pg36-ch22-patroni-topology-v1",
        "captured_at": utc_now(milliseconds=True),
        "cluster": rows[0].get("Cluster") if rows else None,
        "members": members,
    }


def topology_index(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = topology.get("members")
    if not isinstance(rows, list):
        raise LabError("Patroni member list is missing")
    result = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if len(result) != len(rows):
        raise LabError("Patroni member identities are missing or duplicated")
    return result


def topology_stable(
    topology: dict[str, Any],
    expected_leader: str,
) -> bool:
    try:
        members = topology_index(topology)
    except LabError:
        return False
    if set(members) != {"pg-test-1", "pg-test-2", "pg-test-3"}:
        return False
    for name, row in members.items():
        expected_role = "primary" if name == expected_leader else "replica"
        expected_state = "running" if name == expected_leader else "streaming"
        if (
            row.get("role") != expected_role
            or row.get("state") != expected_state
        ):
            return False
        if name != expected_leader:
            lag = row.get("replay_lag_bytes")
            if isinstance(lag, int) and lag != 0:
                return False
    timelines = {
        row.get("timeline")
        for row in members.values()
        if isinstance(row.get("timeline"), int)
    }
    return len(timelines) == 1


def current_leader(topology: dict[str, Any]) -> str | None:
    leaders = [
        name
        for name, row in topology_index(topology).items()
        if row.get("role") == "primary"
    ]
    return leaders[0] if len(leaders) == 1 else None


def wait_for_topology(
    requirements: dict[str, Any],
    user: str,
    expected_leader: str,
    *,
    timeout: float = 30,
) -> tuple[dict[str, Any], int]:
    observer = str(requirements["target"]["members"]["pg-test-3"])
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = patroni_list(user, observer)
            if topology_stable(last, expected_leader):
                return last, time.monotonic_ns()
        except LabError:
            pass
        time.sleep(0.25)
    raise LabError(
        f"topology did not stabilize on {expected_leader}: {last}"
    )


def switchover(
    requirements: dict[str, Any],
    user: str,
    *,
    leader: str,
    candidate: str,
) -> dict[str, Any]:
    host = str(requirements["target"]["members"][leader])
    started_ns = time.monotonic_ns()
    started_at = utc_now(milliseconds=True)
    result = ssh_command(
        user,
        host,
        [
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
        "schema": "pg36-ch22-switchover-action-v1",
        "kind": "healthy-planned-switchover",
        "cluster": "pg-test",
        "leader": leader,
        "candidate": candidate,
        "started_at": started_at,
        "started_monotonic_ns": started_ns,
        "finished_at": utc_now(milliseconds=True),
        "finished_monotonic_ns": finished_ns,
        "duration_ms": (finished_ns - started_ns) / 1_000_000,
        "return_code": result.returncode,
        "stdout_sha256": hashlib.sha256(
            result.stdout.encode("utf-8")
        ).hexdigest(),
        "stderr_empty": not bool(result.stderr.strip()),
    }


def pgbouncer_admin(
    user: str,
    host: str,
    command: str,
    *,
    csv_output: bool = False,
    timeout: float = 20,
) -> str:
    args = [
        "sudo",
        "-n",
        "-iu",
        "postgres",
        "/usr/bin/psql",
        "-X",
        "-h",
        "/run/postgresql",
        "-p",
        "6432",
        "-d",
        "pgbouncer",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    if csv_output:
        args.append("--csv")
    else:
        args.extend(["-qAt"])
    args.extend(["-c", command])
    return ssh_command(
        user,
        host,
        args,
        timeout=timeout,
    ).stdout.strip()


def pgbouncer_config(user: str, host: str) -> dict[str, str]:
    raw = pgbouncer_admin(user, host, "SHOW CONFIG")
    result: dict[str, str] = {}
    for line in raw.splitlines():
        fields = line.split("|")
        if len(fields) >= 2:
            result[fields[0]] = fields[1]
    if not result:
        raise LabError("PgBouncer SHOW CONFIG returned no settings")
    return result


def pgbouncer_pools(user: str, host: str) -> list[dict[str, str]]:
    raw = pgbouncer_admin(
        user,
        host,
        "SHOW POOLS",
        csv_output=True,
    )
    return [dict(row) for row in csv.DictReader(io.StringIO(raw))]


def set_pgbouncer_config(
    user: str,
    host: str,
    values: dict[str, int],
) -> None:
    allowed = {
        "default_pool_size",
        "reserve_pool_size",
        "reserve_pool_timeout",
        "query_wait_timeout",
    }
    if set(values) - allowed:
        raise LabError("refusing an unapproved PgBouncer runtime setting")
    for key, value in values.items():
        if not isinstance(value, int) or value < 0:
            raise LabError(f"invalid PgBouncer value for {key}")
        pgbouncer_admin(user, host, f"SET {key} = {value}")


def project_pgbouncer_config(values: dict[str, str]) -> dict[str, Any]:
    numeric = {
        "listen_port",
        "max_client_conn",
        "default_pool_size",
        "reserve_pool_size",
        "reserve_pool_timeout",
        "query_wait_timeout",
        "max_db_connections",
        "max_user_connections",
        "max_prepared_statements",
        "server_reset_query_always",
    }
    keys = numeric | {
        "pool_mode",
        "listen_addr",
        "unix_socket_dir",
        "server_reset_query",
        "client_tls_sslmode",
    }
    result: dict[str, Any] = {}
    for key in sorted(keys):
        if key not in values:
            raise LabError(f"PgBouncer setting is missing: {key}")
        result[key] = int(values[key]) if key in numeric else values[key]
    return result


def reconnect_database(user: str, host: str, database: str) -> None:
    if database != "test":
        raise LabError("refusing PgBouncer reconnect outside test")
    pgbouncer_admin(user, host, f"RECONNECT {database}")
