#!/usr/bin/env python3
"""Secret-safe helpers for the chapter 23 security lab."""

from __future__ import annotations

import csv
import base64
import hashlib
import io
import json
import os
import shlex
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class LabError(RuntimeError):
    """Raised when a lab precondition or evidence contract fails."""


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


def run(
    args: list[str],
    *,
    stdin: str | bytes | None = None,
    timeout: float = 60,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[Any]:
    text_mode = not isinstance(stdin, bytes)
    try:
        result = subprocess.run(
            args,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text_mode,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LabError(f"cannot execute {args[0]}: {exc}") from exc
    if check and result.returncode != 0:
        stderr = result.stderr
        stdout = result.stdout
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        details = str(stderr).strip().splitlines()
        if not details:
            details = str(stdout).strip().splitlines()
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
    stdin: str | bytes | None = None,
    timeout: float = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[Any]:
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
    return str(result.stdout).strip()


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
        raise LabError(
            f"remote SQL did not return exactly one JSON value: {exc}"
        ) from exc


def remote_python_json(
    user: str,
    host: str,
    program: str,
    payload: Any,
    *,
    as_postgres: bool = True,
    timeout: float = 30,
) -> Any:
    encoded = base64.b64encode(program.encode("utf-8")).decode("ascii")
    bootstrap = (
        "import base64;"
        f"exec(compile(base64.b64decode({encoded!r}),"
        "'<remote-program>','exec'))"
    )
    args = ["sudo", "-n"]
    if as_postgres:
        args.extend(["-iu", "postgres"])
    args.extend(["python3", "-c", bootstrap])
    result = ssh_command(
        user,
        host,
        args,
        stdin=json.dumps(payload, separators=(",", ":")),
        timeout=timeout,
    )
    try:
        return json.loads(str(result.stdout))
    except json.JSONDecodeError as exc:
        raise LabError("remote Python returned invalid JSON") from exc


def remote_root_program_json(
    user: str,
    host: str,
    program: str,
    *,
    timeout: float = 30,
) -> Any:
    result = ssh_command(
        user,
        host,
        ["sudo", "-n", "python3", "-"],
        stdin=program,
        timeout=timeout,
    )
    try:
        return json.loads(str(result.stdout))
    except json.JSONDecodeError as exc:
        raise LabError("remote projection returned invalid JSON") from exc


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
        rows = json.loads(str(result.stdout))
    except json.JSONDecodeError as exc:
        raise LabError("patronictl returned invalid JSON") from exc
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
                "replay_lag_bytes": lower.get("replay_lag"),
            }
        )
    members.sort(key=lambda row: str(row["member"]))
    return {
        "schema": "pg36-ch23-patroni-topology-v1",
        "captured_at": utc_now(milliseconds=True),
        "cluster": "pg-test",
        "members": members,
    }


def topology_stable(
    topology: dict[str, Any],
    expected_leader: str,
) -> bool:
    rows = topology.get("members")
    if not isinstance(rows, list):
        return False
    members = {
        str(row.get("member")): row
        for row in rows
        if isinstance(row, dict)
    }
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
    timelines = {
        row.get("timeline")
        for row in members.values()
        if isinstance(row.get("timeline"), int)
    }
    return len(timelines) == 1


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
    args.append("--csv" if csv_output else "-qAt")
    args.extend(["-c", command])
    return str(
        ssh_command(user, host, args, timeout=timeout).stdout
    ).strip()


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


def selected_pool_settings(
    user: str,
    host: str,
) -> dict[str, int]:
    values = pgbouncer_config(user, host)
    keys = (
        "default_pool_size",
        "reserve_pool_size",
        "reserve_pool_timeout",
        "query_wait_timeout",
    )
    try:
        return {key: int(values[key]) for key in keys}
    except (KeyError, ValueError) as exc:
        raise LabError("PgBouncer pool settings are incomplete") from exc


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
    if set(values) != allowed:
        raise LabError("PgBouncer runtime setting set is not exact")
    for key, value in values.items():
        if not isinstance(value, int) or value < 0:
            raise LabError(f"invalid PgBouncer value for {key}")
        pgbouncer_admin(user, host, f"SET {key} = {value}")


def reconnect_database(user: str, host: str, database: str) -> None:
    if database != "test":
        raise LabError("refusing PgBouncer reconnect outside test")
    pgbouncer_admin(user, host, f"RECONNECT {database}")


def load_private_inventory(
    path: Path,
    *,
    expected_cluster: str,
    expected_login: str,
) -> tuple[str, dict[str, Any]]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise LabError(f"cannot stat private inventory: {exc}") from exc
    if mode != 0o600:
        raise LabError("private inventory must have mode 0600")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LabError(f"cannot read private inventory: {exc}") from exc
    try:
        cluster = document["all"]["children"][expected_cluster]
        variables = cluster["vars"]
        users = variables["pg_users"]
    except (KeyError, TypeError) as exc:
        raise LabError("private inventory shape is unsupported") from exc
    if variables.get("pg_cluster") != expected_cluster:
        raise LabError("private inventory cluster identity drifted")
    matches = [
        item
        for item in users
        if isinstance(item, dict) and item.get("name") == expected_login
    ]
    if len(matches) != 1:
        raise LabError("declared login is absent or duplicated")
    item = matches[0]
    password = item.get("password")
    if not isinstance(password, str) or not password:
        raise LabError("declared login credential is absent")
    if item.get("pgbouncer") is not True:
        raise LabError("declared login is not enabled for PgBouncer")
    projection = {
        "schema": "pg36-ch23-inventory-projection-v1",
        "captured_at": utc_now(milliseconds=True),
        "source": {
            "basename": path.name,
            "mode": "0600",
            "path_redacted": True,
        },
        "cluster": variables.get("pg_cluster"),
        "login": {
            "name": item.get("name"),
            "pgbouncer": item.get("pgbouncer"),
            "roles": sorted(str(value) for value in item.get("roles", [])),
            "password_present": True,
            "password_redacted": True,
        },
        "database_names": sorted(
            str(value.get("name"))
            for value in variables.get("pg_databases", [])
            if isinstance(value, dict) and value.get("name")
        ),
    }
    return password, projection


def ensure_no_secret_material(value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False).lower()
    forbidden = (
        "scram-sha-256$",
        "-----begin private key-----",
        "-----begin encrypted private key-----",
        '"password":',
        '"password_value":',
        "userlist.txt",
    )
    hits = [token for token in forbidden if token in serialized]
    if hits:
        raise LabError(f"secret material detected in evidence: {hits}")
