#!/usr/bin/env python3
"""Run one guarded pgBackRest named-point restore in an isolated postmaster."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from common import (
    LabError,
    patroni_list,
    pgbackrest_info,
    read_json,
    remote_json_psql,
    remote_psql,
    require_stable_source,
    sanitized_repo_info,
    source_sql_state,
    ssh_command,
    utc_now,
    write_json,
)


OUTCOME_FILES = {"restore-run.json", "migration-effort.json"}
RUN_ID_PATTERN = re.compile(r"^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")


class DrillError(LabError):
    """Raised when the guarded drill cannot satisfy its contract."""


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inputs(source_dir: Path) -> dict[str, str]:
    return {
        path.name: sha256(path)
        for path in sorted(source_dir.iterdir())
        if path.is_file() and path.name not in OUTCOME_FILES
    }


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 6)


def require_authority(args: argparse.Namespace, requirements: dict[str, Any]) -> None:
    if (
        args.target_token != requirements["target"]["id"]
        or args.confirmation != "BACKUP_AND_ISOLATED_PITR_CH21"
        or args.authority != "nonproduction-no-data-no-traffic"
    ):
        raise DrillError("exact target, confirmation and authority are required")
    if requirements["target"].get("production_data_permitted") is not False:
        raise DrillError("requirements unexpectedly permit production data")
    if requirements["target"].get("production_traffic_permitted") is not False:
        raise DrillError("requirements unexpectedly permit production traffic")


def require_empty_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise DrillError(f"refusing to overwrite non-empty evidence: {path}")
    path.mkdir(parents=True, exist_ok=True)


def current_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def parse_marker(output: str, expected: dict[str, str]) -> dict[str, str]:
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 1:
        raise DrillError("marker insertion did not return exactly one row")
    fields = lines[0].split("|", 3)
    if len(fields) != 4:
        raise DrillError("marker insertion result is malformed")
    row = {
        "run_id": fields[0],
        "stage": fields[1],
        "token": fields[2],
        "committed_at": fields[3],
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise DrillError("marker insertion returned unexpected identity")
    return row


def insert_marker(
    *,
    user: str,
    host: str,
    database: str,
    setup_sql: str,
    run_id: str,
    stage: str,
    token: str,
) -> dict[str, str]:
    output = remote_psql(
        user,
        host,
        database,
        setup_sql,
        variables={"run_id": run_id, "stage": stage, "token": token},
    )
    return parse_marker(
        output,
        {"run_id": run_id, "stage": stage, "token": token},
    )


def choose_new_backup(
    before: list[Any],
    after: list[Any],
    stanza: str,
) -> dict[str, Any]:
    def one_stanza(values: list[Any]) -> dict[str, Any]:
        matches = [
            row
            for row in values
            if isinstance(row, dict) and row.get("name") == stanza
        ]
        if len(matches) != 1:
            raise DrillError("pgBackRest stanza identity is ambiguous")
        return matches[0]

    before_stanza = one_stanza(before)
    after_stanza = one_stanza(after)
    old_labels = {
        row.get("label")
        for row in before_stanza.get("backup", [])
        if isinstance(row, dict)
    }
    new = [
        row
        for row in after_stanza.get("backup", [])
        if isinstance(row, dict) and row.get("label") not in old_labels
    ]
    if len(new) != 1:
        raise DrillError("expected exactly one new pgBackRest backup")
    backup = new[0]
    if backup.get("type") != "full" or backup.get("error") is not False:
        raise DrillError("fresh backup is not a successful full backup")
    status = after_stanza.get("status", {})
    if status.get("code") != 0:
        raise DrillError("repository status is not ok after backup")
    return backup


def archive_max(info: list[Any], stanza: str) -> str:
    matches = [
        row
        for row in info
        if isinstance(row, dict) and row.get("name") == stanza
    ]
    if len(matches) != 1:
        raise DrillError("cannot identify repository stanza")
    ranges = matches[0].get("archive", [])
    maxima = [
        str(row["max"])
        for row in ranges
        if isinstance(row, dict) and isinstance(row.get("max"), str)
    ]
    if not maxima:
        raise DrillError("repository has no archived WAL range")
    return max(maxima)


def run_pgbackrest(
    *,
    user: str,
    host: str,
    arguments: list[str],
    timeout: int,
) -> float:
    started = time.monotonic()
    ssh_command(
        user,
        host,
        ["sudo", "-n", "-iu", "postgres", "pgbackrest"] + arguments,
        timeout=timeout,
    )
    return elapsed_ms(started)


def prepare_restore_root(
    user: str,
    host: str,
    root: str,
    port: int,
) -> None:
    script = r"""
set -Eeuo pipefail
root="$1"
port="$2"
case "$root" in
  /data/pg36-ch21-restore/run_????????T??????Z_????????) ;;
  *) printf 'unexpected restore root\n' >&2; exit 64 ;;
esac
[[ ! -e "$root" ]] || {
  printf 'restore root already exists\n' >&2
  exit 73
}
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  printf 'restore TCP port is already in use\n' >&2
  exit 73
fi
install -d -o postgres -g postgres -m 0700 \
  "$root" "$root/data" "$root/socket" "$root/log" "$root/spool"
printf '%s\n' \
  'local all postgres peer' \
  'local all all reject' > "$root/pg_hba.restore.conf"
chown postgres:postgres "$root/pg_hba.restore.conf"
chmod 0600 "$root/pg_hba.restore.conf"
"""
    ssh_command(
        user,
        host,
        ["sudo", "-n", "bash", "-s", "--", root, str(port)],
        stdin=script,
        timeout=20,
    )


def start_restore(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    settings: dict[str, Any],
) -> tuple[float, str]:
    data = f"{root}/data"
    options = [
        f"-c config_file={data}/postgresql.conf",
        f"-c hba_file={root}/pg_hba.restore.conf",
        f"-c ident_file={data}/pg_ident.conf",
        "-c listen_addresses=''",
        f"-c port={port}",
        f"-c unix_socket_directories={root}/socket",
        "-c unix_socket_permissions=0700",
        "-c ssl=off",
        "-c archive_mode=off",
        "-c primary_conninfo=''",
        "-c primary_slot_name=''",
        "-c shared_preload_libraries=''",
        "-c logging_collector=off",
        "-c log_destination=stderr",
        "-c cluster_name=pg36-ch21-restore",
        "-c hot_standby=on",
        "-c shared_buffers=64MB",
    ]
    for name in (
        "max_connections",
        "max_worker_processes",
        "max_wal_senders",
        "max_prepared_transactions",
        "max_locks_per_transaction",
    ):
        value = settings.get(name)
        if not isinstance(value, int) or value < 0:
            raise DrillError(f"source recovery setting {name} is invalid")
        options.append(f"-c {name}={value}")
    started = time.monotonic()
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "/usr/lib/postgresql/18/bin/pg_ctl",
            "-D",
            data,
            "-l",
            f"{root}/log/postgresql.log",
            "-w",
            "-t",
            "30",
            "-o",
            " ".join(options),
            "start",
        ],
        timeout=40,
        check=False,
    )
    duration = elapsed_ms(started)
    if result.returncode != 0:
        details = result.stderr.strip().splitlines()
        detail = details[-1] if details else f"exit {result.returncode}"
        raise DrillError(f"isolated PostgreSQL start failed: {detail}")
    return duration, result.stdout.strip()


def isolated_psql(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    sql: str,
    timeout: int = 20,
) -> str:
    return ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "-iu",
            "postgres",
            "/usr/lib/postgresql/18/bin/psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            f"{root}/socket",
            "-p",
            str(port),
            "-U",
            "postgres",
            "-d",
            database,
            "--file=-",
        ],
        stdin=sql,
        timeout=timeout,
    ).stdout.strip()


def isolated_json(**kwargs: Any) -> Any:
    output = isolated_psql(**kwargs)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise DrillError(f"isolated SQL did not return JSON: {exc}") from exc


def wait_for_promotion(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    started: float,
    timeout_seconds: float,
) -> tuple[dict[str, Any], float]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    sql = r"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only', current_setting('transaction_read_only')::boolean,
  'archive_mode', current_setting('archive_mode'),
  'listen_addresses', current_setting('listen_addresses'),
  'port', current_setting('port')::int,
  'cluster_name', current_setting('cluster_name')
);
"""
    while time.monotonic() < deadline:
        try:
            value = isolated_json(
                user=user,
                host=host,
                root=root,
                port=port,
                database=database,
                sql=sql,
                timeout=5,
            )
        except LabError:
            time.sleep(0.05)
            continue
        if not isinstance(value, dict):
            raise DrillError("isolated state is not an object")
        last = value
        if value.get("in_recovery") is False:
            return value, round((time.monotonic() - started) * 1000, 6)
        time.sleep(0.05)
    raise DrillError(f"promotion did not complete; last state={last}")


def inspect_recovered_state(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    run_id: str,
) -> tuple[dict[str, Any], str]:
    sql = f"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only', current_setting('transaction_read_only')::boolean,
  'archive_mode', current_setting('archive_mode'),
  'listen_addresses', current_setting('listen_addresses'),
  'port', current_setting('port')::int,
  'ssl', current_setting('ssl')::boolean,
  'cluster_name', current_setting('cluster_name'),
  'shared_preload_libraries', current_setting('shared_preload_libraries'),
  'checkpoint_timeline', c.timeline_id,
  'markers', COALESCE((
    SELECT json_agg(json_build_object(
      'stage', p.stage,
      'token', p.token,
      'committed_at', p.committed_at
    ) ORDER BY CASE p.stage
      WHEN 'base' THEN 1 WHEN 'keep' THEN 2 ELSE 3 END)
    FROM pg36_ch21.recovery_probe AS p
    WHERE p.run_id = '{run_id}'
  ), '[]'::json)
)
FROM pg_control_checkpoint() AS c;
SELECT system_identifier::text FROM pg_control_system();
"""
    output = isolated_psql(
        user=user,
        host=host,
        root=root,
        port=port,
        database=database,
        sql=sql,
    )
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 2:
        raise DrillError("recovered-state query did not return two rows")
    try:
        state = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise DrillError(f"recovered-state JSON is invalid: {exc}") from exc
    return state, lines[1]


def write_probe(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
) -> bool:
    output = isolated_psql(
        user=user,
        host=host,
        root=root,
        port=port,
        database=database,
        sql=r"""
BEGIN;
CREATE TEMPORARY TABLE pg36_ch21_writable_probe(value integer);
INSERT INTO pg36_ch21_writable_probe VALUES (1);
ROLLBACK;
SELECT 'rollback-write-ok';
""",
    )
    return output == "rollback-write-ok"


def inspect_runtime_isolation(
    user: str,
    host: str,
    root: str,
    port: int,
) -> dict[str, Any]:
    script = r"""
set -Eeuo pipefail
root="$1"
port="$2"
tcp=false
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  tcp=true
fi
socket_mode=$(stat -c '%a' "$root/socket")
socket_owner=$(stat -c '%U:%G' "$root/socket")
printf '{"tcp_listener":%s,"socket_exists":%s,"socket_mode":"%s","socket_owner":"%s","postmaster_pid_exists":%s}\n' \
  "$tcp" \
  "$([[ -S "$root/socket/.s.PGSQL.${port}" ]] && printf true || printf false)" \
  "$socket_mode" "$socket_owner" \
  "$([[ -s "$root/data/postmaster.pid" ]] && printf true || printf false)"
"""
    result = ssh_command(
        user,
        host,
        ["sudo", "-n", "bash", "-s", "--", root, str(port)],
        stdin=script,
        timeout=10,
    ).stdout
    try:
        value = json.loads(result)
    except json.JSONDecodeError as exc:
        raise DrillError(f"runtime-isolation JSON is invalid: {exc}") from exc
    return value


def stop_restore(
    user: str,
    host: str,
    root: str,
    port: int,
) -> dict[str, Any]:
    script = r"""
set -Eeuo pipefail
root="$1"
port="$2"
stopped=false
if [[ -s "$root/data/postmaster.pid" ]]; then
  sudo -n -iu postgres /usr/lib/postgresql/18/bin/pg_ctl \
    -D "$root/data" -w -t 30 -m fast stop >/dev/null
  stopped=true
fi
tcp=false
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  tcp=true
fi
printf '{"stop_command_executed":%s,"postmaster_pid_exists":%s,"socket_exists":%s,"tcp_listener":%s,"restore_directory_retained":%s}\n' \
  "$stopped" \
  "$([[ -s "$root/data/postmaster.pid" ]] && printf true || printf false)" \
  "$([[ -S "$root/socket/.s.PGSQL.${port}" ]] && printf true || printf false)" \
  "$tcp" \
  "$([[ -d "$root" ]] && printf true || printf false)"
"""
    result = ssh_command(
        user,
        host,
        ["sudo", "-n", "bash", "-s", "--", root, str(port)],
        stdin=script,
        timeout=40,
    ).stdout
    try:
        value = json.loads(result)
    except json.JSONDecodeError as exc:
        raise DrillError(f"shutdown JSON is invalid: {exc}") from exc
    return value


def fixture_boundary(
    state: dict[str, Any],
    expected_tokens: dict[str, str],
) -> dict[str, Any]:
    rows = state.get("markers")
    if not isinstance(rows, list):
        raise DrillError("recovered marker evidence is missing")
    actual = {
        str(row.get("stage")): str(row.get("token"))
        for row in rows
        if isinstance(row, dict)
    }
    return {
        "base_present": actual.get("base") == expected_tokens["base"],
        "keep_present": actual.get("keep") == expected_tokens["keep"],
        "discard_present": "discard" in actual,
        "unexpected_stage_count": len(set(actual) - {"base", "keep", "discard"}),
        "observed_stages": sorted(actual),
    }


def main() -> int:
    args = parse_args()
    root: str | None = None
    shutdown: dict[str, Any] | None = None
    manifest_written = False
    try:
        requirements = read_json(args.requirements)
        require_authority(args, requirements)
        require_empty_output(args.output)

        target = requirements["target"]
        restore_contract = requirements["restore"]
        repository_contract = requirements["repository"]
        objectives = requirements["objectives"]
        source_host = str(target["source_address"])
        restore_host = str(target["restore_address"])
        stanza = str(repository_contract["stanza"])
        database = str(requirements["fixture"]["database"])
        port = int(restore_contract["port"])
        run_id = current_run_id()
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise DrillError("generated run ID failed its path policy")
        restore_point = f"pg36_ch21_{run_id}_keep"
        root = f"{restore_contract['root_prefix']}/{run_id}"
        tokens = {
            stage: f"{run_id}_{stage}"
            for stage in requirements["fixture"]["stages"]
        }

        manifest = {
            "schema": "pg36-ch21-drill-manifest-v1",
            "release": requirements["release"],
            "started_at": utc_now(),
            "run_id": run_id,
            "target": target["id"],
            "mode": "fresh-full-backup-and-isolated-named-pitr",
            "production_approval": False,
            "production_data": False,
            "production_traffic": False,
            "destructive_cleanup": False,
            "restore_root": root,
            "restore_root_preexisting": False,
            "secret_values_exported": 0,
            "raw_system_identifier_exported": False,
            "source_sha256": source_inputs(args.source_dir),
        }
        write_json(args.output / "drill-manifest.json", manifest)
        manifest_written = True

        topology_before = patroni_list(args.ssh_user, source_host)
        require_stable_source(topology_before, requirements)
        source_before, source_system_id = source_sql_state(
            args.ssh_user,
            source_host,
        )
        if source_before.get("in_recovery") is not False:
            raise DrillError("declared source primary is in recovery")
        repo_before = pgbackrest_info(
            args.ssh_user,
            source_host,
            stanza,
        )
        write_json(
            args.output / "source-before.json",
            {
                "schema": "pg36-ch21-source-state-v1",
                "phase": "before",
                "patroni": topology_before,
                "postgres": source_before,
                "repository": sanitized_repo_info(repo_before),
                "system_identifier_recorded": False,
            },
        )

        setup_sql = (args.source_dir / "setup.sql").read_text(
            encoding="utf-8"
        )
        markers = {}
        markers["base"] = insert_marker(
            user=args.ssh_user,
            host=source_host,
            database=database,
            setup_sql=setup_sql,
            run_id=run_id,
            stage="base",
            token=tokens["base"],
        )

        backup_started_at = utc_now()
        backup_ms = run_pgbackrest(
            user=args.ssh_user,
            host=source_host,
            arguments=[
                f"--stanza={stanza}",
                "--repo=1",
                "--type=full",
                "--log-level-console=info",
                "backup",
            ],
            timeout=90,
        )
        repo_after_backup = pgbackrest_info(
            args.ssh_user,
            source_host,
            stanza,
        )
        backup = choose_new_backup(repo_before, repo_after_backup, stanza)
        backup_label = str(backup["label"])

        markers["keep"] = insert_marker(
            user=args.ssh_user,
            host=source_host,
            database=database,
            setup_sql=setup_sql,
            run_id=run_id,
            stage="keep",
            token=tokens["keep"],
        )
        restore_point_row = remote_json_psql(
            args.ssh_user,
            source_host,
            database,
            rf"""
\set restore_point {restore_point}
WITH point AS MATERIALIZED (
  SELECT pg_create_restore_point(:'restore_point') AS lsn
)
SELECT json_build_object(
  'name', :'restore_point',
  'lsn', lsn::text,
  'wal_segment', pg_walfile_name(lsn),
  'created_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
)
FROM point;
""",
        )
        if not isinstance(restore_point_row, dict):
            raise DrillError("restore-point evidence is not an object")

        markers["discard"] = insert_marker(
            user=args.ssh_user,
            host=source_host,
            database=database,
            setup_sql=setup_sql,
            run_id=run_id,
            stage="discard",
            token=tokens["discard"],
        )
        switch_row = remote_json_psql(
            args.ssh_user,
            source_host,
            database,
            r"""
SELECT json_build_object(
  'switch_lsn', pg_switch_wal()::text,
  'requested_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                          'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
);
""",
        )
        check_ms = run_pgbackrest(
            user=args.ssh_user,
            host=source_host,
            arguments=[
                f"--stanza={stanza}",
                "--log-level-console=info",
                "check",
            ],
            timeout=60,
        )

        archive_deadline = time.monotonic() + 30
        repo_ready: list[Any] | None = None
        target_segment = str(restore_point_row["wal_segment"])
        while time.monotonic() < archive_deadline:
            candidate = pgbackrest_info(
                args.ssh_user,
                source_host,
                stanza,
            )
            if archive_max(candidate, stanza) >= target_segment:
                repo_ready = candidate
                break
            time.sleep(0.25)
        if repo_ready is None:
            raise DrillError("repository archive range does not cover target WAL")
        maximum_archived = archive_max(repo_ready, stanza)

        write_json(
            args.output / "fixture.json",
            {
                "schema": "pg36-ch21-fixture-v1",
                "run_id": run_id,
                "database": database,
                "markers": markers,
                "restore_point": restore_point_row,
                "wal_switch": switch_row,
            },
        )
        write_json(
            args.output / "backup.json",
            {
                "schema": "pg36-ch21-backup-v1",
                "started_at": backup_started_at,
                "command_ms": backup_ms,
                "check_ms": check_ms,
                "label": backup_label,
                "type": backup.get("type"),
                "error": backup.get("error"),
                "archive": backup.get("archive"),
                "timestamp": backup.get("timestamp"),
                "info": backup.get("info"),
                "repository_status_code": 0,
                "repository_status": "ok",
                "repository_type": repository_contract["type"],
                "repository_cipher": repository_contract["cipher"],
                "target_wal_segment": target_segment,
                "maximum_archived_wal": maximum_archived,
                "target_wal_covered": maximum_archived >= target_segment,
                "repository_snapshot": sanitized_repo_info(repo_ready),
                "secret_values_exported": 0,
            },
        )

        prepare_restore_root(
            args.ssh_user,
            restore_host,
            root,
            port,
        )
        restore_started_at = utc_now()
        restore_copy_ms = run_pgbackrest(
            user=args.ssh_user,
            host=restore_host,
            arguments=[
                f"--stanza={stanza}",
                "--repo=1",
                f"--set={backup_label}",
                "--type=name",
                f"--target={restore_point}",
                "--target-action=promote",
                "--target-timeline=latest",
                "--archive-mode=off",
                f"--pg1-path={root}/data",
                f"--spool-path={root}/spool",
                f"--log-path={root}/log",
                "--log-level-console=info",
                "restore",
            ],
            timeout=90,
        )

        recovery_started = time.monotonic()
        start_to_first_connection_ms, _start_output = start_restore(
            user=args.ssh_user,
            host=restore_host,
            root=root,
            port=port,
            settings=source_before["settings"],
        )
        first_state = isolated_json(
            user=args.ssh_user,
            host=restore_host,
            root=root,
            port=port,
            database=database,
            sql=r"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only', current_setting('transaction_read_only')::boolean,
  'observed_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                         'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
);
""",
        )
        promoted_state, start_to_promoted_ms = wait_for_promotion(
            user=args.ssh_user,
            host=restore_host,
            root=root,
            port=port,
            database=database,
            started=recovery_started,
            timeout_seconds=float(
                objectives["maximum_start_to_promoted_ms"]
            )
            / 1000,
        )
        recovered, recovered_system_id = inspect_recovered_state(
            user=args.ssh_user,
            host=restore_host,
            root=root,
            port=port,
            database=database,
            run_id=run_id,
        )
        writable = write_probe(
            user=args.ssh_user,
            host=restore_host,
            root=root,
            port=port,
            database=database,
        )
        runtime = inspect_runtime_isolation(
            args.ssh_user,
            restore_host,
            root,
            port,
        )
        boundary = fixture_boundary(recovered, tokens)

        source_timeline = int(str(source_before["current_wal_segment"])[:8], 16)
        restored_timeline = recovered.get("checkpoint_timeline")
        if not isinstance(restored_timeline, int):
            raise DrillError("restored checkpoint timeline is invalid")

        recovery = {
            "schema": "pg36-ch21-recovery-v1",
            "started_at": restore_started_at,
            "backup_label": backup_label,
            "restore_point": restore_point,
            "restore_options": {
                "type": "name",
                "target_action": "promote",
                "target_timeline": "latest",
                "archive_mode": "off",
            },
            "restore_root": root,
            "restore_copy_ms": restore_copy_ms,
            "start_to_first_connection_ms": start_to_first_connection_ms,
            "first_connection_state": first_state,
            "start_to_promoted_ms": start_to_promoted_ms,
            "first_connection_to_promoted_ms": round(
                max(0.0, start_to_promoted_ms - start_to_first_connection_ms),
                6,
            ),
            "promoted_state": promoted_state,
            "effective_state": recovered,
            "runtime_isolation": runtime,
            "rollback_write_probe": writable,
            "boundary": boundary,
            "lineage": {
                "system_identifier_relation": (
                    "matches source"
                    if recovered_system_id == source_system_id
                    else "does not match source"
                ),
                "raw_identifier_recorded": False,
                "source_timeline": source_timeline,
                "restored_timeline": restored_timeline,
                "timeline_increment": restored_timeline - source_timeline,
            },
            "recovery_settings_carried_from_source": source_before["settings"],
            "patroni_managed": False,
            "secret_values_exported": 0,
        }
        write_json(args.output / "recovery.json", recovery)

        shutdown = stop_restore(
            args.ssh_user,
            restore_host,
            root,
            port,
        )
        write_json(
            args.output / "isolated-shutdown.json",
            {
                "schema": "pg36-ch21-isolated-shutdown-v1",
                "captured_at": utc_now(),
                **shutdown,
            },
        )

        topology_after = patroni_list(args.ssh_user, source_host)
        require_stable_source(topology_after, requirements)
        source_after, source_system_after = source_sql_state(
            args.ssh_user,
            source_host,
        )
        restore_host_live = remote_json_psql(
            args.ssh_user,
            restore_host,
            "postgres",
            r"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'wal_replay_paused', pg_is_wal_replay_paused(),
  'cluster_name', current_setting('cluster_name'),
  'port', current_setting('port')::int
);
""",
        )
        write_json(
            args.output / "source-after.json",
            {
                "schema": "pg36-ch21-source-state-v1",
                "phase": "after",
                "patroni": topology_after,
                "postgres": source_after,
                "source_system_identifier_unchanged": (
                    source_system_after == source_system_id
                ),
                "restore_host_live_member": restore_host_live,
                "system_identifier_recorded": False,
            },
        )

        manifest["completed_at"] = utc_now()
        manifest["status"] = "completed"
        manifest["restore_directory_retained"] = bool(
            shutdown.get("restore_directory_retained")
        )
        manifest["source_sha256"] = source_inputs(args.source_dir)
        write_json(args.output / "drill-manifest.json", manifest)
        print("status=isolated-pitr-complete")
        print(f"run_id={run_id}")
        print(f"backup_label={backup_label}")
        print(f"restore_root={root}")
        print("isolated_postmaster=stopped")
        print("source_cluster=healthy")
        print("production_ch21_gate=pending")
        return 0
    except (LabError, KeyError, TypeError, ValueError, OSError) as error:
        if args.output.exists():
            write_json(
                args.output / "failure.json",
                {
                    "schema": "pg36-ch21-failure-v1",
                    "failed_at": utc_now(),
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "restore_root": root,
                    "production_approval": False,
                },
            )
        sys.stderr.write(f"isolated recovery drill failed: {error}\n")
        return 1
    finally:
        if root is not None and shutdown is None:
            try:
                emergency = stop_restore(
                    args.ssh_user,
                    str(
                        read_json(args.requirements)["target"][
                            "restore_address"
                        ]
                    ),
                    root,
                    int(read_json(args.requirements)["restore"]["port"]),
                )
                if args.output.exists():
                    write_json(
                        args.output / "isolated-shutdown.json",
                        {
                            "schema":
                                "pg36-ch21-isolated-shutdown-v1",
                            "captured_at": utc_now(),
                            "emergency_finally": True,
                            **emergency,
                        },
                    )
            except BaseException as stop_error:
                if manifest_written:
                    sys.stderr.write(
                        f"warning: emergency restore stop failed: "
                        f"{stop_error}\n"
                    )


if __name__ == "__main__":
    raise SystemExit(main())
