#!/usr/bin/env python3
"""Shared, secret-free helpers for the chapter 21 recovery lab."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LabError(RuntimeError):
    """Raised when a command or evidence precondition fails."""


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


def run(
    args: list[str],
    *,
    stdin: str | None = None,
    timeout: int = 60,
    check: bool = True,
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
    timeout: int = 60,
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
    variables: dict[str, str] | None = None,
    timeout: int = 30,
) -> str:
    args = [
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
    ]
    for key, value in sorted((variables or {}).items()):
        args.append(f"--set={key}={value}")
    args.append("--file=-")
    return ssh_command(
        user,
        host,
        args,
        stdin=sql,
        timeout=timeout,
    ).stdout.strip()


def remote_json_psql(
    user: str,
    host: str,
    database: str,
    sql: str,
    *,
    timeout: int = 30,
) -> Any:
    output = remote_psql(user, host, database, sql, timeout=timeout)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise LabError(f"remote SQL did not return one JSON value: {exc}") from exc


def patroni_list(user: str, host: str) -> dict[str, Any]:
    output = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "patronictl",
            "-c",
            "/etc/patroni/patroni.yml",
            "list",
            "--format",
            "json",
        ],
        timeout=20,
    ).stdout
    try:
        rows = json.loads(output)
    except json.JSONDecodeError as exc:
        raise LabError(f"patronictl returned invalid JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise LabError("patronictl JSON is not a list")
    members = []
    for row in rows:
        if not isinstance(row, dict):
            raise LabError("patronictl member is not an object")
        members.append(
            {
                "member": row.get("Member"),
                "host": row.get("Host"),
                "role": str(row.get("Role", "")).lower(),
                "state": str(row.get("State", "")).lower(),
                "timeline": row.get("TL"),
                "receive_lsn": row.get("Receive LSN"),
                "receive_lag_bytes": row.get("Receive Lag"),
                "replay_lsn": row.get("Replay LSN"),
                "replay_lag_bytes": row.get("Replay Lag"),
            }
        )
    return {
        "captured_at": utc_now(),
        "cluster": rows[0].get("Cluster") if rows else None,
        "members": members,
    }


def pgbackrest_info(user: str, host: str, stanza: str) -> list[Any]:
    output = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "pgbackrest",
            f"--stanza={stanza}",
            "--repo=1",
            "--output=json",
            "info",
        ],
        timeout=30,
    ).stdout
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise LabError(f"pgBackRest returned invalid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise LabError("pgBackRest info JSON is not a list")
    return value


def sanitized_repo_info(value: list[Any]) -> list[Any]:
    """Remove raw PostgreSQL lineage identifiers from repository evidence."""
    sanitized = json.loads(json.dumps(value))
    for stanza in sanitized:
        if not isinstance(stanza, dict):
            continue
        for database in stanza.get("db", []):
            if isinstance(database, dict):
                database.pop("system-id", None)
    return sanitized


def source_sql_state(user: str, host: str) -> tuple[dict[str, Any], str]:
    sql = r"""
SELECT json_build_object(
  'captured_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                         'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only', current_setting('transaction_read_only')::boolean,
  'checkpoint_timeline', c.timeline_id,
  'current_lsn', pg_current_wal_lsn()::text,
  'current_wal_segment', pg_walfile_name(pg_current_wal_lsn()),
  'archive_mode', current_setting('archive_mode'),
  'archive_command_configured',
      current_setting('archive_command') <> '' AND
      current_setting('archive_command') <> '(disabled)',
  'settings', json_build_object(
    'max_connections', current_setting('max_connections')::int,
    'max_worker_processes', current_setting('max_worker_processes')::int,
    'max_wal_senders', current_setting('max_wal_senders')::int,
    'max_prepared_transactions',
        current_setting('max_prepared_transactions')::int,
    'max_locks_per_transaction',
        current_setting('max_locks_per_transaction')::int
  ),
  'archiver', (
    SELECT json_build_object(
      'archived_count', archived_count,
      'failed_count', failed_count,
      'last_archived_wal', last_archived_wal,
      'last_archived_time', last_archived_time,
      'last_failed_wal', last_failed_wal,
      'last_failed_time', last_failed_time
    )
    FROM pg_stat_archiver
  )
)
FROM pg_control_checkpoint() AS c;
SELECT system_identifier::text FROM pg_control_system();
"""
    output = remote_psql(user, host, "postgres", sql)
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 2:
        raise LabError("source state query did not return two rows")
    try:
        state = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise LabError(f"source state JSON is invalid: {exc}") from exc
    return state, lines[1]


def require_stable_source(
    topology: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    expected = requirements["source_acceptance"]
    members = {
        str(row.get("member")): row
        for row in topology.get("members", [])
    }
    if set(members) != set(expected["members"]):
        raise LabError("source Patroni member set drifted")
    leaders = [
        name
        for name, row in members.items()
        if row.get("role") in {"leader", "primary"}
    ]
    if leaders != [expected["initial_leader"]]:
        raise LabError("source leader drifted from the retained baseline")
    for name, row in members.items():
        if name == expected["initial_leader"]:
            if row.get("state") != "running":
                raise LabError("source primary is not running")
            continue
        if row.get("state") != "streaming":
            raise LabError(f"source replica {name} is not streaming")
        lag = row.get("replay_lag_bytes")
        if isinstance(lag, int) and lag > expected["maximum_replay_lag_bytes"]:
            raise LabError(f"source replica {name} exceeds the lag contract")
