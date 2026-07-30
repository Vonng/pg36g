#!/usr/bin/env python3
"""Shared, secret-minimized helpers for the chapter 32 PITR lab."""

from __future__ import annotations

import hashlib
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


SOURCE_FILES = (
    "requirements.json",
    "recovery-contract.json",
    "negative-cases.json",
    "topology.mmd",
    "lab-contract.md",
    "setup.sql",
    "common.py",
    "capture.py",
    "exercise.py",
    "validate.py",
    "review.py",
    "task.sh",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
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
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "PAGER": "cat",
        "PSQL_PAGER": "cat",
        "PGCONNECT_TIMEOUT": "5",
    }
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


def json_from_output(output: str, label: str) -> Any:
    candidates = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(("{", "["))
    ]
    for candidate in reversed(candidates):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise LabError(f"{label} did not return JSON: {exc}") from exc


def remote_json_psql(
    user: str,
    host: str,
    database: str,
    sql: str,
    *,
    variables: dict[str, str] | None = None,
    timeout: int = 30,
) -> Any:
    return json_from_output(
        remote_psql(
            user,
            host,
            database,
            sql,
            variables=variables,
            timeout=timeout,
        ),
        "remote SQL",
    )


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
    rows = json_from_output(output, "patronictl")
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
                "receive_lag_bytes": row.get("Receive Lag"),
                "replay_lag_bytes": row.get("Replay Lag"),
            }
        )
    return {
        "captured_at": utc_now(),
        "cluster": rows[0].get("Cluster") if rows else None,
        "members": members,
    }


def require_stable_source(
    topology: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    target = requirements["target"]
    expected_members = {"pg-test-1", "pg-test-2", "pg-test-3"}
    rows = topology.get("members", [])
    members = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
    if topology.get("cluster") != target["cluster"]:
        raise LabError("Patroni cluster identity drifted")
    if set(members) != expected_members:
        raise LabError("Patroni member set drifted")
    leaders = [
        name
        for name, row in members.items()
        if row.get("role") in {"leader", "primary"}
    ]
    if leaders != [target["source_primary"]]:
        raise LabError("declared source primary is not the sole leader")
    for name, row in members.items():
        expected_state = (
            "running"
            if name == target["source_primary"]
            else "streaming"
        )
        if row.get("state") != expected_state:
            raise LabError(
                f"Patroni member {name} is not {expected_state}"
            )


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
    value = json_from_output(output, "pgBackRest info")
    if not isinstance(value, list):
        raise LabError("pgBackRest info JSON is not a list")
    return value


def sanitized_repo_info(value: list[Any]) -> list[Any]:
    sanitized = json.loads(json.dumps(value))
    for stanza in sanitized:
        if not isinstance(stanza, dict):
            continue
        for database in stanza.get("db", []):
            if isinstance(database, dict):
                database.pop("system-id", None)
    return sanitized


def source_sql_state(
    user: str,
    host: str,
    database: str,
    schema: str,
) -> tuple[dict[str, Any], str]:
    sql = rf"""
SELECT json_build_object(
  'captured_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                         'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
  'cluster_name', current_setting('cluster_name'),
  'server_version', current_setting('server_version'),
  'server_version_num', current_setting('server_version_num')::int,
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only',
      current_setting('transaction_read_only')::boolean,
  'checkpoint_timeline', c.timeline_id,
  'current_lsn', pg_current_wal_lsn()::text,
  'current_wal_segment', pg_walfile_name(pg_current_wal_lsn()),
  'archive_mode', current_setting('archive_mode'),
  'fixture_schema_exists', to_regnamespace('{schema}') IS NOT NULL,
  'settings', json_build_object(
    'max_connections', current_setting('max_connections')::int,
    'max_worker_processes',
        current_setting('max_worker_processes')::int,
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
    output = remote_psql(user, host, database, sql)
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 2:
        raise LabError("source-state SQL did not return two rows")
    try:
        state = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise LabError(f"source-state JSON is invalid: {exc}") from exc
    return state, lines[1]


def source_hashes(source_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = source_dir / name
        if not path.is_file():
            raise LabError(f"source file missing: {path}")
        result[name] = sha256_file(path)
    return result


def upstream_hashes(
    source_dir: Path,
    requirements: dict[str, Any],
) -> dict[str, dict[str, str]]:
    labs_root = source_dir.parent.resolve()
    result: dict[str, dict[str, str]] = {}
    for label, relative in requirements.get("upstream", {}).items():
        path = (source_dir / str(relative)).resolve()
        try:
            path.relative_to(labs_root)
        except ValueError as exc:
            raise LabError(f"upstream path escapes labs root: {path}") from exc
        if not path.is_file():
            raise LabError(f"upstream evidence missing: {path}")
        result[label] = {
            "name": path.name,
            "sha256": sha256_file(path),
        }
    return result


def archive_max(info: list[Any], stanza: str) -> str:
    matches = [
        row
        for row in info
        if isinstance(row, dict) and row.get("name") == stanza
    ]
    if len(matches) != 1:
        raise LabError("cannot identify repository stanza")
    ranges = matches[0].get("archive", [])
    maxima = [
        str(row["max"])
        for row in ranges
        if isinstance(row, dict) and isinstance(row.get("max"), str)
    ]
    if not maxima:
        raise LabError("repository has no archived WAL range")
    return max(maxima)


def choose_new_backup(
    before: list[Any],
    after: list[Any],
    stanza: str,
) -> dict[str, Any]:
    def one_stanza(values: list[Any]) -> dict[str, Any]:
        rows = [
            row
            for row in values
            if isinstance(row, dict) and row.get("name") == stanza
        ]
        if len(rows) != 1:
            raise LabError("pgBackRest stanza identity is ambiguous")
        return rows[0]

    old = one_stanza(before)
    new = one_stanza(after)
    old_labels = {
        row.get("label")
        for row in old.get("backup", [])
        if isinstance(row, dict)
    }
    created = [
        row
        for row in new.get("backup", [])
        if isinstance(row, dict) and row.get("label") not in old_labels
    ]
    if len(created) != 1:
        raise LabError("expected exactly one new pgBackRest backup")
    backup = created[0]
    if backup.get("type") != "full" or backup.get("error") is not False:
        raise LabError("fresh backup is not a successful full backup")
    if new.get("status", {}).get("code") != 0:
        raise LabError("repository status is not ok after backup")
    return backup
