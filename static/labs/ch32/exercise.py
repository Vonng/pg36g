#!/usr/bin/env python3
"""Run the guarded XID-PITR and reconciliation exercise for chapter 32."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from common import (
    LabError,
    archive_max,
    choose_new_backup,
    json_from_output,
    patroni_list,
    pgbackrest_info,
    read_json,
    remote_json_psql,
    remote_psql,
    require_stable_source,
    sanitized_repo_info,
    source_hashes,
    source_sql_state,
    ssh_command,
    utc_now,
    write_json,
)


RUN_ID_PATTERN = re.compile(
    r"^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$"
)


class ExerciseError(LabError):
    """Raised when the bounded recovery exercise violates its contract."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--ssh-user", default="vagrant")
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--seed")
    return parser.parse_args()


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 6)


def current_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def require_authority(
    args: argparse.Namespace,
    requirements: dict[str, Any],
) -> None:
    target = requirements["target"]
    risk = requirements["risk"]
    if (
        args.target_token != target["id"]
        or args.confirmation
        != "RANDOM_XID_PITR_RECONCILE_CH32"
        or args.authority != "nonproduction-no-data-no-traffic"
        or target.get("production_data_permitted") is not False
        or target.get("production_traffic_permitted") is not False
        or risk.get("managed_pgdata_permitted") is not False
        or risk.get("patroni_change_permitted") is not False
        or risk.get("dcs_change_permitted") is not False
        or risk.get("service_route_change_permitted") is not False
    ):
        raise ExerciseError(
            "exact sandbox target, authority and confirmation are required"
        )


def require_evidence_boundary(
    evidence_dir: Path,
    preflight: dict[str, Any],
    source_dir: Path,
) -> None:
    if not evidence_dir.is_dir():
        raise ExerciseError("evidence directory does not exist")
    allowed = {"preflight-evidence.json"}
    unexpected = {
        path.name
        for path in evidence_dir.iterdir()
        if path.name not in allowed
    }
    if unexpected:
        raise ExerciseError(
            f"refusing non-empty exercise evidence: {sorted(unexpected)}"
        )
    if preflight.get("schema") != "pg36-ch32-preflight-v1":
        raise ExerciseError("preflight schema is invalid")
    if preflight.get("mutation") != "none":
        raise ExerciseError("preflight was not read-only")
    if preflight.get("source_sha256") != source_hashes(source_dir):
        raise ExerciseError("lab source changed after preflight")


def run_pgbackrest(
    user: str,
    host: str,
    arguments: list[str],
    *,
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


def prepare_candidate(
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
  /data/pg36-ch32-restore/run_????????T??????Z_????????/inclusive|\
  /data/pg36-ch32-restore/run_????????T??????Z_????????/exclusive) ;;
  *) printf 'unexpected restore root\n' >&2; exit 64 ;;
esac
base="${root%/*}"
prefix="${base%/*}"
[[ "$prefix" == "/data/pg36-ch32-restore" ]] || exit 64
for path in "$prefix" "$base" "$root"; do
  [[ ! -L "$path" ]] || {
    printf 'refusing symlink restore path\n' >&2
    exit 64
  }
done
[[ ! -e "$root" ]] || {
  printf 'restore candidate already exists\n' >&2
  exit 73
}
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  printf 'restore TCP port is already in use\n' >&2
  exit 73
fi
install -d -o postgres -g postgres -m 0700 \
  "$prefix" "$base" "$root" "$root/data" "$root/socket" \
  "$root/log" "$root/spool"
printf '%s\n' \
  'local all postgres peer' \
  'local all all reject' > "$root/pg_hba.restore.conf"
chown postgres:postgres "$root/pg_hba.restore.conf"
chmod 0600 "$root/pg_hba.restore.conf"
"""
    ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "bash",
            "-s",
            "--",
            root,
            str(port),
        ],
        stdin=script,
        timeout=20,
    )


def pig_pitr(
    *,
    user: str,
    host: str,
    stanza: str,
    backup_label: str,
    damage_xid: str,
    root: str,
    exclusive: bool,
    plan: bool,
) -> tuple[Any, float]:
    command = [
        "sudo",
        "-n",
        "-iu",
        "postgres",
        "pig",
        "pitr",
        "-s",
        stanza,
        "-r",
        "1",
        "-b",
        backup_label,
        "--xid",
        damage_xid,
        "--target-action=promote",
        "--target-timeline=current",
        "-D",
        f"{root}/data",
        "--no-restart",
        "-o",
        "json",
    ]
    if exclusive:
        command.append("--exclusive")
    command.append("--plan" if plan else "--yes")
    command.extend(
        [
            "--",
            "--archive-mode=off",
            f"--spool-path={root}/spool",
            f"--log-path={root}/log",
        ]
    )
    started = time.monotonic()
    result = ssh_command(
        user,
        host,
        command,
        timeout=45 if plan else 240,
    )
    duration = elapsed_ms(started)
    return json_from_output(result.stdout, "pig pitr"), duration


def start_candidate(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    label: str,
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
        f"-c cluster_name=pg36-ch32-{label}",
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
            raise ExerciseError(
                f"source recovery setting {name} is invalid"
            )
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
            "60",
            "-o",
            " ".join(options),
            "start",
        ],
        timeout=75,
        check=False,
    )
    duration = elapsed_ms(started)
    if result.returncode != 0:
        details = result.stderr.strip().splitlines()
        detail = details[-1] if details else f"exit {result.returncode}"
        raise ExerciseError(
            f"isolated {label} PostgreSQL start failed: {detail}"
        )
    return duration, result.stdout.strip()


def isolated_psql(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    sql: str,
    timeout: int = 30,
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
    return json_from_output(
        isolated_psql(**kwargs),
        "isolated SQL",
    )


def wait_for_promotion(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    started: float,
    label: str,
    timeout_seconds: float = 90,
) -> tuple[dict[str, Any], float]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    sql = r"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only',
      current_setting('transaction_read_only')::boolean,
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
            time.sleep(0.1)
            continue
        if not isinstance(value, dict):
            raise ExerciseError("isolated state is not an object")
        last = value
        if value.get("in_recovery") is False:
            return value, elapsed_ms(started)
        time.sleep(0.1)
    raise ExerciseError(
        f"{label} promotion did not finish; last state={last}"
    )


def inspect_candidate(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    run_id: str,
    victim_start: int,
    victim_count: int,
    post_count: int,
) -> dict[str, Any]:
    victim_end = victim_start + victim_count - 1
    post_end = victim_start + post_count - 1
    sql = f"""
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'transaction_read_only',
      current_setting('transaction_read_only')::boolean,
  'archive_mode', current_setting('archive_mode'),
  'listen_addresses', current_setting('listen_addresses'),
  'port', current_setting('port')::int,
  'ssl', current_setting('ssl')::boolean,
  'cluster_name', current_setting('cluster_name'),
  'shared_preload_libraries',
      current_setting('shared_preload_libraries'),
  'timeline', (SELECT timeline_id FROM pg_control_checkpoint()),
  'run_marker_count', (
    SELECT count(*) FROM pg36_ch32.run_marker
    WHERE run_id = '{run_id}'
  ),
  'audits', COALESCE((
    SELECT json_agg(json_build_object(
      'stage', stage,
      'xact_id', xact_id,
      'wal_lsn', wal_lsn::text
    ) ORDER BY observed_at)
    FROM pg36_ch32.incident_audit
    WHERE run_id = '{run_id}'
  ), '[]'::json),
  'safe_ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'safe-before'
  ),
  'post_ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'post-target'
  ),
  'pending_outbox_count', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'pending'
  ),
  'canceled_outbox_count', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'canceled'
  ),
  'victims', (
    SELECT json_build_object(
      'count', count(*),
      'balance_cents', sum(balance_cents),
      'active', count(*) FILTER (WHERE status = 'active'),
      'mispriced', count(*) FILTER (WHERE status = 'mispriced')
    )
    FROM pg36_ch32.accounts
    WHERE account_id BETWEEN {victim_start} AND {victim_end}
  ),
  'post_subset', (
    SELECT json_build_object(
      'count', count(*),
      'balance_cents', sum(balance_cents),
      'active', count(*) FILTER (WHERE status = 'active'),
      'mispriced', count(*) FILTER (WHERE status = 'mispriced')
    )
    FROM pg36_ch32.accounts
    WHERE account_id BETWEEN {victim_start} AND {post_end}
  )
);
"""
    value = isolated_json(
        user=user,
        host=host,
        root=root,
        port=port,
        database=database,
        sql=sql,
    )
    if not isinstance(value, dict):
        raise ExerciseError("candidate inspection is not an object")
    return value


def extract_recovered_accounts(
    *,
    user: str,
    host: str,
    root: str,
    port: int,
    database: str,
    victim_start: int,
    victim_count: int,
) -> list[dict[str, Any]]:
    victim_end = victim_start + victim_count - 1
    value = isolated_json(
        user=user,
        host=host,
        root=root,
        port=port,
        database=database,
        sql=f"""
SELECT COALESCE(json_agg(json_build_object(
  'account_id', account_id,
  'balance_cents', balance_cents,
  'status', status
) ORDER BY account_id), '[]'::json)
FROM pg36_ch32.accounts
WHERE account_id BETWEEN {victim_start} AND {victim_end};
""",
    )
    if not isinstance(value, list):
        raise ExerciseError("recovered account export is not an array")
    return value


def runtime_isolation(
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
printf '{"tcp_listener":%s,"socket_exists":%s,"socket_mode":"%s","socket_owner":"%s","postmaster_pid_exists":%s}\n' \
  "$tcp" \
  "$([[ -S "$root/socket/.s.PGSQL.${port}" ]] && printf true || printf false)" \
  "$(stat -c '%a' "$root/socket")" \
  "$(stat -c '%U:%G' "$root/socket")" \
  "$([[ -s "$root/data/postmaster.pid" ]] && printf true || printf false)"
"""
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "bash",
            "-s",
            "--",
            root,
            str(port),
        ],
        stdin=script,
        timeout=15,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExerciseError("runtime-isolation output is invalid") from exc
    return value


def stop_and_remove_candidate(
    user: str,
    host: str,
    root: str,
    port: int,
) -> dict[str, Any]:
    script = r"""
set -Eeuo pipefail
root="$1"
port="$2"
case "$root" in
  /data/pg36-ch32-restore/run_????????T??????Z_????????/inclusive|\
  /data/pg36-ch32-restore/run_????????T??????Z_????????/exclusive) ;;
  *) printf 'refusing unexpected restore path\n' >&2; exit 64 ;;
esac
[[ ! -L "$root" ]] || {
  printf 'refusing symlink restore root\n' >&2
  exit 64
}
stopped=false
if [[ -s "$root/data/postmaster.pid" ]]; then
  sudo -n -iu postgres /usr/lib/postgresql/18/bin/pg_ctl \
    -D "$root/data" -w -t 45 -m fast stop >/dev/null
  stopped=true
fi
pid_exists=false
[[ -s "$root/data/postmaster.pid" ]] && pid_exists=true
socket_exists=false
[[ -S "$root/socket/.s.PGSQL.${port}" ]] && socket_exists=true
tcp=false
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  tcp=true
fi
if [[ "$pid_exists" == true || "$socket_exists" == true ]]; then
  printf 'refusing to remove a running restore\n' >&2
  exit 73
fi
[[ "$tcp" == false ]] || {
  printf 'unexpected TCP listener remains; refusing cleanup\n' >&2
  exit 73
}
removed=false
if [[ -d "$root" ]]; then
  rm -rf -- "$root"
  removed=true
fi
base="${root%/*}"
rmdir -- "$base" 2>/dev/null || true
rmdir -- "${base%/*}" 2>/dev/null || true
printf '{"stop_command_executed":%s,"postmaster_pid_exists":false,"socket_exists":false,"tcp_listener":false,"root_removed":%s}\n' \
  "$stopped" "$removed"
"""
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "bash",
            "-s",
            "--",
            root,
            str(port),
        ],
        stdin=script,
        timeout=60,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExerciseError("candidate cleanup output is invalid") from exc
    return value


def restore_prefix_state(
    user: str,
    host: str,
    prefix: str,
    port: int,
) -> dict[str, Any]:
    script = r"""
set -Eeuo pipefail
prefix="$1"
port="$2"
[[ "$prefix" == "/data/pg36-ch32-restore" ]] || exit 64
entries=0
[[ -d "$prefix" ]] && \
  entries=$(find "$prefix" -mindepth 1 -maxdepth 2 -print | wc -l)
tcp=false
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
  tcp=true
fi
printf '{"entries":%s,"tcp_listener":%s}\n' "$entries" "$tcp"
"""
    result = ssh_command(
        user,
        host,
        [
            "sudo",
            "-n",
            "bash",
            "-s",
            "--",
            prefix,
            str(port),
        ],
        stdin=script,
        timeout=15,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExerciseError("restore-prefix output is invalid") from exc


def audit_map(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        str(row.get("stage")): str(row.get("xact_id"))
        for row in candidate.get("audits", [])
        if isinstance(row, dict)
    }


def validate_inclusive_candidate(
    candidate: dict[str, Any],
    *,
    damage_xid: str,
    victim_count: int,
) -> None:
    audits = audit_map(candidate)
    if (
        candidate.get("in_recovery") is not False
        or candidate.get("run_marker_count") != 1
        or audits.get("damage") != damage_xid
        or set(audits) != {"base", "safe-before", "damage"}
        or candidate.get("safe_ledger_count") != victim_count
        or candidate.get("post_ledger_count") != 0
        or candidate.get("pending_outbox_count") != victim_count
        or candidate.get("canceled_outbox_count") != 0
        or candidate.get("victims", {}).get("mispriced")
        != victim_count
    ):
        raise ExerciseError(
            "inclusive candidate did not demonstrate target inclusion"
        )


def validate_exclusive_candidate(
    candidate: dict[str, Any],
    *,
    victim_start: int,
    victim_count: int,
    safe_delta: int,
) -> None:
    audits = audit_map(candidate)
    victim_end = victim_start + victim_count - 1
    base_sum = sum(100000 + account_id for account_id in range(
        victim_start,
        victim_end + 1,
    ))
    expected_sum = base_sum + safe_delta * victim_count
    if (
        candidate.get("in_recovery") is not False
        or candidate.get("run_marker_count") != 1
        or set(audits) != {"base", "safe-before"}
        or candidate.get("safe_ledger_count") != victim_count
        or candidate.get("post_ledger_count") != 0
        or candidate.get("pending_outbox_count") != 0
        or candidate.get("canceled_outbox_count") != 0
        or candidate.get("victims", {}).get("count") != victim_count
        or candidate.get("victims", {}).get("active") != victim_count
        or candidate.get("victims", {}).get("mispriced") != 0
        or candidate.get("victims", {}).get("balance_cents")
        != expected_sum
    ):
        raise ExerciseError(
            "exclusive candidate failed the pre-damage boundary"
        )


def execute_fixture_transaction(
    user: str,
    host: str,
    database: str,
    sql: str,
) -> dict[str, Any]:
    value = remote_json_psql(
        user,
        host,
        database,
        sql,
        timeout=45,
    )
    if not isinstance(value, dict):
        raise ExerciseError("fixture transaction did not return an object")
    return value


def safe_transaction_sql(
    run_id: str,
    victim_start: int,
    victim_count: int,
    delta: int,
) -> str:
    victim_end = victim_start + victim_count - 1
    return f"""
BEGIN;
WITH changed AS (
  UPDATE pg36_ch32.accounts
  SET balance_cents = balance_cents + {delta},
      updated_at = clock_timestamp()
  WHERE account_id BETWEEN {victim_start} AND {victim_end}
  RETURNING account_id
)
INSERT INTO pg36_ch32.ledger (
  run_id, account_id, amount_cents, stage
)
SELECT '{run_id}', account_id, {delta}, 'safe-before'
FROM changed;
INSERT INTO pg36_ch32.incident_audit (
  run_id, stage, xact_id, wal_lsn, details
)
VALUES (
  '{run_id}',
  'safe-before',
  pg_current_xact_id()::text,
  pg_current_wal_lsn(),
  jsonb_build_object(
    'victim_start', {victim_start},
    'victim_count', {victim_count},
    'delta_cents', {delta}
  )
);
COMMIT;
SELECT json_build_object(
  'stage', stage,
  'xact_id', xact_id,
  'wal_lsn', wal_lsn::text,
  'victim_count', details->'victim_count',
  'delta_cents', details->'delta_cents',
  'ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'safe-before'
  )
)
FROM pg36_ch32.incident_audit
WHERE run_id = '{run_id}' AND stage = 'safe-before';
"""


def damage_transaction_sql(
    run_id: str,
    victim_start: int,
    victim_count: int,
) -> str:
    victim_end = victim_start + victim_count - 1
    return f"""
BEGIN;
UPDATE pg36_ch32.accounts
SET balance_cents = 0,
    status = 'mispriced',
    updated_at = clock_timestamp()
WHERE account_id BETWEEN {victim_start} AND {victim_end};
INSERT INTO pg36_ch32.outbox (
  run_id, account_id, event_kind, state
)
SELECT
  '{run_id}',
  account_id,
  'wrong-balance-notification',
  'pending'
FROM generate_series({victim_start}, {victim_end}) AS account_id;
INSERT INTO pg36_ch32.incident_audit (
  run_id, stage, xact_id, wal_lsn, details
)
VALUES (
  '{run_id}',
  'damage',
  pg_current_xact_id()::text,
  pg_current_wal_lsn(),
  jsonb_build_object(
    'victim_start', {victim_start},
    'victim_count', {victim_count},
    'wrong_outbox_events', {victim_count},
    'external_dispatch_enabled', false
  )
);
COMMIT;
SELECT json_build_object(
  'stage', stage,
  'xact_id', xact_id,
  'wal_lsn', wal_lsn::text,
  'victim_count', details->'victim_count',
  'pending_outbox_count', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'pending'
  ),
  'external_dispatch_count', 0
)
FROM pg36_ch32.incident_audit
WHERE run_id = '{run_id}' AND stage = 'damage';
"""


def post_target_transaction_sql(
    run_id: str,
    victim_start: int,
    post_count: int,
    delta: int,
) -> str:
    post_end = victim_start + post_count - 1
    return f"""
BEGIN;
WITH changed AS (
  UPDATE pg36_ch32.accounts
  SET balance_cents = balance_cents + {delta},
      updated_at = clock_timestamp()
  WHERE account_id BETWEEN {victim_start} AND {post_end}
  RETURNING account_id
)
INSERT INTO pg36_ch32.ledger (
  run_id, account_id, amount_cents, stage
)
SELECT '{run_id}', account_id, {delta}, 'post-target'
FROM changed;
INSERT INTO pg36_ch32.incident_audit (
  run_id, stage, xact_id, wal_lsn, details
)
VALUES (
  '{run_id}',
  'post-target',
  pg_current_xact_id()::text,
  pg_current_wal_lsn(),
  jsonb_build_object(
    'account_start', {victim_start},
    'account_count', {post_count},
    'delta_cents', {delta}
  )
);
COMMIT;
SELECT json_build_object(
  'stage', stage,
  'xact_id', xact_id,
  'wal_lsn', wal_lsn::text,
  'account_count', details->'account_count',
  'delta_cents', details->'delta_cents',
  'ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'post-target'
  )
)
FROM pg36_ch32.incident_audit
WHERE run_id = '{run_id}' AND stage = 'post-target';
"""


def source_incident_boundary(
    user: str,
    host: str,
    database: str,
    run_id: str,
) -> dict[str, Any]:
    value = remote_json_psql(
        user,
        host,
        database,
        f"""
SELECT json_build_object(
  'run_id', '{run_id}',
  'damage_xid', (
    SELECT xact_id FROM pg36_ch32.incident_audit
    WHERE run_id = '{run_id}' AND stage = 'damage'
  ),
  'damage_audit_lsn', (
    SELECT wal_lsn::text FROM pg36_ch32.incident_audit
    WHERE run_id = '{run_id}' AND stage = 'damage'
  ),
  'post_target_xid', (
    SELECT xact_id FROM pg36_ch32.incident_audit
    WHERE run_id = '{run_id}' AND stage = 'post-target'
  ),
  'required_lsn', pg_current_wal_lsn()::text,
  'required_wal_segment',
      pg_walfile_name(pg_current_wal_lsn()),
  'observed_at', to_char(clock_timestamp() AT TIME ZONE 'UTC',
                         'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
);
""",
    )
    if (
        not isinstance(value, dict)
        or not str(value.get("damage_xid", "")).isdigit()
        or not str(value.get("post_target_xid", "")).isdigit()
    ):
        raise ExerciseError("source audit did not yield XID boundary")
    return value


def post_target_rows(
    user: str,
    host: str,
    database: str,
    run_id: str,
) -> list[dict[str, Any]]:
    value = remote_json_psql(
        user,
        host,
        database,
        f"""
SELECT COALESCE(json_agg(json_build_object(
  'account_id', account_id,
  'amount_cents', amount_cents
) ORDER BY account_id), '[]'::json)
FROM pg36_ch32.ledger
WHERE run_id = '{run_id}' AND stage = 'post-target';
""",
    )
    if not isinstance(value, list):
        raise ExerciseError("post-target audit is not an array")
    return value


def reconciliation_sql(
    *,
    run_id: str,
    rows: list[dict[str, int]],
    victim_count: int,
    outbox_count: int,
) -> str:
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return f"""
BEGIN;
CREATE TEMPORARY TABLE pg36_ch32_recovered AS
SELECT *
FROM jsonb_to_recordset($pg36${payload}$pg36$::jsonb) AS r(
  account_id integer,
  recovered_balance_cents bigint,
  post_delta_cents bigint,
  expected_current_balance_cents bigint
);
DO $pg36block$
DECLARE
  actual integer;
BEGIN
  SELECT count(*) INTO actual FROM pg36_ch32_recovered;
  IF actual <> {victim_count} THEN
    RAISE EXCEPTION 'recovered row count mismatch: %', actual;
  END IF;
  SELECT count(*) INTO actual
  FROM pg36_ch32.accounts AS a
  JOIN pg36_ch32_recovered AS r USING (account_id)
  WHERE a.balance_cents = r.expected_current_balance_cents
    AND a.status = 'mispriced';
  IF actual <> {victim_count} THEN
    RAISE EXCEPTION 'source conditional preimage mismatch: %', actual;
  END IF;
  UPDATE pg36_ch32.accounts AS a
  SET balance_cents =
        r.recovered_balance_cents + r.post_delta_cents,
      status = 'active',
      updated_at = clock_timestamp()
  FROM pg36_ch32_recovered AS r
  WHERE a.account_id = r.account_id
    AND a.balance_cents = r.expected_current_balance_cents
    AND a.status = 'mispriced';
  GET DIAGNOSTICS actual = ROW_COUNT;
  IF actual <> {victim_count} THEN
    RAISE EXCEPTION 'conditional repair row count mismatch: %', actual;
  END IF;
  UPDATE pg36_ch32.outbox
  SET state = 'canceled'
  WHERE run_id = '{run_id}'
    AND event_kind = 'wrong-balance-notification'
    AND state = 'pending';
  GET DIAGNOSTICS actual = ROW_COUNT;
  IF actual <> {outbox_count} THEN
    RAISE EXCEPTION 'outbox cancellation row count mismatch: %', actual;
  END IF;
END
$pg36block$;
COMMIT;
SELECT json_build_object(
  'recovered_rows', {victim_count},
  'conditional_rows_repaired', (
    SELECT count(*) FROM pg36_ch32.accounts AS a
    JOIN pg36_ch32_recovered AS r USING (account_id)
  ),
  'wrong_outbox_canceled', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'canceled'
  )
);
"""


def source_manifest(
    user: str,
    host: str,
    database: str,
    run_id: str,
    victim_start: int,
    victim_count: int,
    post_count: int,
) -> dict[str, Any]:
    victim_end = victim_start + victim_count - 1
    post_end = victim_start + post_count - 1
    value = remote_json_psql(
        user,
        host,
        database,
        f"""
SELECT json_build_object(
  'run_id', '{run_id}',
  'accounts', (SELECT count(*) FROM pg36_ch32.accounts),
  'total_balance_cents', (
    SELECT sum(balance_cents) FROM pg36_ch32.accounts
  ),
  'victims', (
    SELECT json_build_object(
      'count', count(*),
      'balance_cents', sum(balance_cents),
      'active', count(*) FILTER (WHERE status = 'active'),
      'mispriced', count(*) FILTER (WHERE status = 'mispriced')
    )
    FROM pg36_ch32.accounts
    WHERE account_id BETWEEN {victim_start} AND {victim_end}
  ),
  'post_subset', (
    SELECT json_build_object(
      'count', count(*),
      'balance_cents', sum(balance_cents),
      'active', count(*) FILTER (WHERE status = 'active')
    )
    FROM pg36_ch32.accounts
    WHERE account_id BETWEEN {victim_start} AND {post_end}
  ),
  'safe_ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'safe-before'
  ),
  'post_ledger_count', (
    SELECT count(*) FROM pg36_ch32.ledger
    WHERE run_id = '{run_id}' AND stage = 'post-target'
  ),
  'pending_outbox_count', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'pending'
  ),
  'canceled_outbox_count', (
    SELECT count(*) FROM pg36_ch32.outbox
    WHERE run_id = '{run_id}' AND state = 'canceled'
  ),
  'audit_stages', (
    SELECT json_agg(stage ORDER BY observed_at)
    FROM pg36_ch32.incident_audit
    WHERE run_id = '{run_id}'
  ),
  'external_dispatch_count', 0
);
""",
    )
    if not isinstance(value, dict):
        raise ExerciseError("source manifest is not an object")
    return value


def cleanup_fixture(
    user: str,
    host: str,
    database: str,
    run_id: str,
) -> dict[str, Any]:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ExerciseError("cleanup run marker is invalid")
    value = remote_json_psql(
        user,
        host,
        database,
        f"""
DO $pg36cleanup$
DECLARE
  marker_count integer;
  owned_count integer;
BEGIN
  IF to_regnamespace('pg36_ch32') IS NOT NULL THEN
    IF to_regclass('pg36_ch32.run_marker') IS NULL THEN
      RAISE EXCEPTION 'fixture schema has no ownership marker';
    END IF;
    SELECT count(*), count(*) FILTER (WHERE run_id = '{run_id}')
      INTO marker_count, owned_count
    FROM pg36_ch32.run_marker;
    IF marker_count <> 1 OR owned_count <> 1 THEN
      RAISE EXCEPTION
        'fixture ownership mismatch: total %, owned %',
        marker_count, owned_count;
    END IF;
    DROP SCHEMA pg36_ch32 CASCADE;
  END IF;
END
$pg36cleanup$;
SELECT json_build_object(
  'run_id', '{run_id}',
  'schema_exists', to_regnamespace('pg36_ch32') IS NOT NULL,
  'exact_marker_cleanup', true
);
""",
        timeout=30,
    )
    if not isinstance(value, dict):
        raise ExerciseError("fixture cleanup is not an object")
    return value


def backup_is_retained(
    repository: list[Any],
    stanza: str,
    label: str,
) -> bool:
    return any(
        backup.get("label") == label
        for row in repository
        if isinstance(row, dict) and row.get("name") == stanza
        for backup in row.get("backup", [])
        if isinstance(backup, dict)
    )


def hash_recovered_rows(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        rows,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    args = parse_args()
    run_id: str | None = None
    candidate_roots: list[str] = []
    cleaned_roots: set[str] = set()
    fixture_created = False
    fixture_cleaned = False
    manifest: dict[str, Any] | None = None
    try:
        requirements = read_json(args.source_dir / "requirements.json")
        require_authority(args, requirements)
        preflight_path = args.evidence_dir / "preflight-evidence.json"
        preflight = read_json(preflight_path)
        require_evidence_boundary(
            args.evidence_dir,
            preflight,
            args.source_dir,
        )

        target = requirements["target"]
        fixture = requirements["fixture"]
        repository_contract = requirements["repository"]
        restore_contract = requirements["restore"]
        source_host = str(target["source_address"])
        restore_host = str(target["restore_address"])
        database = str(fixture["database"])
        schema = str(fixture["schema"])
        stanza = str(repository_contract["stanza"])
        port = int(restore_contract["port"])
        run_id = current_run_id()
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ExerciseError("generated run ID failed path policy")

        account_count = int(fixture["account_count"])
        victim_count = int(fixture["victim_count"])
        post_count = int(fixture["post_target_legitimate_count"])
        safe_delta = int(fixture["safe_delta_cents"])
        post_delta = int(fixture["post_target_delta_cents"])
        maximum_start = account_count - victim_count + 1
        rng = (
            random.Random(args.seed)
            if args.seed is not None
            else secrets.SystemRandom()
        )
        victim_start = rng.randint(1, maximum_start)
        victim_end = victim_start + victim_count - 1
        post_end = victim_start + post_count - 1
        root_base = f"{restore_contract['root_prefix']}/{run_id}"
        inclusive_root = f"{root_base}/inclusive"
        exclusive_root = f"{root_base}/exclusive"
        candidate_roots.extend([inclusive_root, exclusive_root])

        manifest = {
            "schema": "pg36-ch32-exercise-manifest-v1",
            "started_at": utc_now(),
            "run_id": run_id,
            "preflight_run_id": preflight["run_id"],
            "target": target["id"],
            "mode": "random-xid-pitr-and-reconciliation",
            "victim_selection_method": (
                "seeded-random" if args.seed is not None else "system-random"
            ),
            "production_approval": False,
            "production_data": False,
            "production_traffic": False,
            "business_cutover_performed": False,
            "external_dispatch_enabled": False,
            "managed_pgdata_touched": False,
            "patroni_changed": False,
            "dcs_changed": False,
            "route_changed": False,
            "backup_expired": False,
            "source_sha256": source_hashes(args.source_dir),
        }
        write_json(
            args.evidence_dir / "exercise-manifest.json",
            manifest,
        )

        topology_before = patroni_list(args.ssh_user, source_host)
        require_stable_source(topology_before, requirements)
        source_before, source_system_id = source_sql_state(
            args.ssh_user,
            source_host,
            database,
            schema,
        )
        if (
            source_before.get("in_recovery") is not False
            or source_before.get("fixture_schema_exists") is not False
        ):
            raise ExerciseError("source precondition changed after capture")
        repo_before = pgbackrest_info(
            args.ssh_user,
            source_host,
            stanza,
        )
        write_json(
            args.evidence_dir / "source-before.json",
            {
                "schema": "pg36-ch32-source-state-v1",
                "phase": "before",
                "topology": topology_before,
                "postgres": source_before,
                "repository": sanitized_repo_info(repo_before),
                "system_identifier_recorded": False,
            },
        )

        setup_sql = (args.source_dir / "setup.sql").read_text(
            encoding="utf-8"
        )
        setup = remote_json_psql(
            args.ssh_user,
            source_host,
            database,
            setup_sql,
            variables={
                "run_id": run_id,
                "account_count": str(account_count),
            },
            timeout=45,
        )
        fixture_created = True
        if (
            not isinstance(setup, dict)
            or setup.get("run_id") != run_id
            or setup.get("accounts") != account_count
            or setup.get("active") != account_count
        ):
            raise ExerciseError("fixture setup manifest is invalid")

        backup_started_at = utc_now()
        backup_ms = run_pgbackrest(
            args.ssh_user,
            source_host,
            [
                f"--stanza={stanza}",
                "--repo=1",
                "--type=full",
                "--log-level-console=info",
                "backup",
            ],
            timeout=240,
        )
        repo_after_backup = pgbackrest_info(
            args.ssh_user,
            source_host,
            stanza,
        )
        backup = choose_new_backup(
            repo_before,
            repo_after_backup,
            stanza,
        )
        backup_label = str(backup["label"])

        safe = execute_fixture_transaction(
            args.ssh_user,
            source_host,
            database,
            safe_transaction_sql(
                run_id,
                victim_start,
                victim_count,
                safe_delta,
            ),
        )
        damage = execute_fixture_transaction(
            args.ssh_user,
            source_host,
            database,
            damage_transaction_sql(
                run_id,
                victim_start,
                victim_count,
            ),
        )
        post_target = execute_fixture_transaction(
            args.ssh_user,
            source_host,
            database,
            post_target_transaction_sql(
                run_id,
                victim_start,
                post_count,
                post_delta,
            ),
        )
        boundary_started = time.monotonic()
        boundary = source_incident_boundary(
            args.ssh_user,
            source_host,
            database,
            run_id,
        )
        target_identification_ms = elapsed_ms(boundary_started)
        damage_xid = str(boundary["damage_xid"])
        if damage_xid != str(damage.get("xact_id")):
            raise ExerciseError(
                "source audit XID does not match damage transaction"
            )

        switch = remote_json_psql(
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
            args.ssh_user,
            source_host,
            [
                f"--stanza={stanza}",
                "--log-level-console=info",
                "check",
            ],
            timeout=90,
        )
        archive_deadline = time.monotonic() + 60
        repository_ready: list[Any] | None = None
        required_segment = str(boundary["required_wal_segment"])
        while time.monotonic() < archive_deadline:
            candidate = pgbackrest_info(
                args.ssh_user,
                source_host,
                stanza,
            )
            if archive_max(candidate, stanza) >= required_segment:
                repository_ready = candidate
                break
            time.sleep(0.25)
        if repository_ready is None:
            raise ExerciseError(
                "archive does not cover the incident boundary"
            )
        maximum_archived = archive_max(repository_ready, stanza)

        write_json(
            args.evidence_dir / "fixture.json",
            {
                "schema": "pg36-ch32-fixture-v1",
                "run_id": run_id,
                "database": database,
                "schema_name": schema,
                "account_count": account_count,
                "victim_start": victim_start,
                "victim_end": victim_end,
                "victim_count": victim_count,
                "post_target_start": victim_start,
                "post_target_end": post_end,
                "post_target_count": post_count,
                "safe_delta_cents": safe_delta,
                "post_target_delta_cents": post_delta,
                "setup": setup,
                "safe_transaction": safe,
                "damage_transaction": damage,
                "post_target_transaction": post_target,
                "incident_boundary": boundary,
                "target_identification_ms": target_identification_ms,
                "wal_switch": switch,
                "external_dispatch_count": 0,
            },
        )
        write_json(
            args.evidence_dir / "backup.json",
            {
                "schema": "pg36-ch32-backup-v1",
                "started_at": backup_started_at,
                "command_ms": backup_ms,
                "check_ms": check_ms,
                "label": backup_label,
                "type": backup.get("type"),
                "error": backup.get("error"),
                "archive": backup.get("archive"),
                "info": backup.get("info"),
                "timestamp": backup.get("timestamp"),
                "repository_status_code": 0,
                "required_wal_segment": required_segment,
                "maximum_archived_wal": maximum_archived,
                "archive_covered": maximum_archived >= required_segment,
                "retained": True,
                "expire_executed": False,
                "repository_snapshot": sanitized_repo_info(
                    repository_ready
                ),
            },
        )

        prepare_candidate(
            args.ssh_user,
            restore_host,
            inclusive_root,
            port,
        )
        inclusive_plan, inclusive_plan_ms = pig_pitr(
            user=args.ssh_user,
            host=restore_host,
            stanza=stanza,
            backup_label=backup_label,
            damage_xid=damage_xid,
            root=inclusive_root,
            exclusive=False,
            plan=True,
        )
        write_json(
            args.evidence_dir / "inclusive-plan.json",
            {
                "schema": "pg36-ch32-pitr-plan-v1",
                "candidate": "inclusive",
                "backup_label": backup_label,
                "target_type": "xid",
                "target": damage_xid,
                "target_inclusive": True,
                "target_timeline": "current",
                "target_action": "promote",
                "side_restore": True,
                "no_restart": True,
                "archive_mode": "off",
                "plan_ms": inclusive_plan_ms,
                "plan": inclusive_plan,
            },
        )
        inclusive_restore_result, inclusive_restore_ms = pig_pitr(
            user=args.ssh_user,
            host=restore_host,
            stanza=stanza,
            backup_label=backup_label,
            damage_xid=damage_xid,
            root=inclusive_root,
            exclusive=False,
            plan=False,
        )
        recovery_started = time.monotonic()
        inclusive_start_ms, _ = start_candidate(
            user=args.ssh_user,
            host=restore_host,
            root=inclusive_root,
            port=port,
            label="inclusive",
            settings=source_before["settings"],
        )
        inclusive_promoted, inclusive_replay_ms = wait_for_promotion(
            user=args.ssh_user,
            host=restore_host,
            root=inclusive_root,
            port=port,
            database=database,
            started=recovery_started,
            label="inclusive",
        )
        inclusive_validation_started = time.monotonic()
        inclusive = inspect_candidate(
            user=args.ssh_user,
            host=restore_host,
            root=inclusive_root,
            port=port,
            database=database,
            run_id=run_id,
            victim_start=victim_start,
            victim_count=victim_count,
            post_count=post_count,
        )
        validate_inclusive_candidate(
            inclusive,
            damage_xid=damage_xid,
            victim_count=victim_count,
        )
        inclusive_runtime = runtime_isolation(
            args.ssh_user,
            restore_host,
            inclusive_root,
            port,
        )
        inclusive_validation_ms = elapsed_ms(
            inclusive_validation_started
        )
        write_json(
            args.evidence_dir / "inclusive-recovery.json",
            {
                "schema": "pg36-ch32-recovery-candidate-v1",
                "candidate": "inclusive",
                "backup_label": backup_label,
                "damage_xid": damage_xid,
                "target_inclusive": True,
                "accepted": False,
                "rejection_reason":
                    "the target damage transaction is present",
                "restore_copy_ms": inclusive_restore_ms,
                "start_to_first_connection_ms": inclusive_start_ms,
                "start_to_promoted_ms": inclusive_replay_ms,
                "validation_ms": inclusive_validation_ms,
                "promoted_state": inclusive_promoted,
                "effective_state": inclusive,
                "runtime_isolation": inclusive_runtime,
                "pig_result": inclusive_restore_result,
                "patroni_managed": False,
            },
        )
        inclusive_cleanup = stop_and_remove_candidate(
            args.ssh_user,
            restore_host,
            inclusive_root,
            port,
        )
        cleaned_roots.add(inclusive_root)

        prepare_candidate(
            args.ssh_user,
            restore_host,
            exclusive_root,
            port,
        )
        exclusive_plan, exclusive_plan_ms = pig_pitr(
            user=args.ssh_user,
            host=restore_host,
            stanza=stanza,
            backup_label=backup_label,
            damage_xid=damage_xid,
            root=exclusive_root,
            exclusive=True,
            plan=True,
        )
        write_json(
            args.evidence_dir / "exclusive-plan.json",
            {
                "schema": "pg36-ch32-pitr-plan-v1",
                "candidate": "exclusive",
                "backup_label": backup_label,
                "target_type": "xid",
                "target": damage_xid,
                "target_inclusive": False,
                "target_timeline": "current",
                "target_action": "promote",
                "side_restore": True,
                "no_restart": True,
                "archive_mode": "off",
                "plan_ms": exclusive_plan_ms,
                "plan": exclusive_plan,
            },
        )
        exclusive_restore_result, exclusive_restore_ms = pig_pitr(
            user=args.ssh_user,
            host=restore_host,
            stanza=stanza,
            backup_label=backup_label,
            damage_xid=damage_xid,
            root=exclusive_root,
            exclusive=True,
            plan=False,
        )
        recovery_started = time.monotonic()
        exclusive_start_ms, _ = start_candidate(
            user=args.ssh_user,
            host=restore_host,
            root=exclusive_root,
            port=port,
            label="exclusive",
            settings=source_before["settings"],
        )
        exclusive_promoted, exclusive_replay_ms = wait_for_promotion(
            user=args.ssh_user,
            host=restore_host,
            root=exclusive_root,
            port=port,
            database=database,
            started=recovery_started,
            label="exclusive",
        )
        exclusive_validation_started = time.monotonic()
        exclusive = inspect_candidate(
            user=args.ssh_user,
            host=restore_host,
            root=exclusive_root,
            port=port,
            database=database,
            run_id=run_id,
            victim_start=victim_start,
            victim_count=victim_count,
            post_count=post_count,
        )
        validate_exclusive_candidate(
            exclusive,
            victim_start=victim_start,
            victim_count=victim_count,
            safe_delta=safe_delta,
        )
        recovered_rows = extract_recovered_accounts(
            user=args.ssh_user,
            host=restore_host,
            root=exclusive_root,
            port=port,
            database=database,
            victim_start=victim_start,
            victim_count=victim_count,
        )
        if len(recovered_rows) != victim_count:
            raise ExerciseError("exclusive export row count is invalid")
        exclusive_runtime = runtime_isolation(
            args.ssh_user,
            restore_host,
            exclusive_root,
            port,
        )
        exclusive_validation_ms = elapsed_ms(
            exclusive_validation_started
        )
        write_json(
            args.evidence_dir / "exclusive-recovery.json",
            {
                "schema": "pg36-ch32-recovery-candidate-v1",
                "candidate": "exclusive",
                "backup_label": backup_label,
                "damage_xid": damage_xid,
                "target_inclusive": False,
                "accepted": True,
                "acceptance_reason":
                    "safe transaction present; damage and later writes absent",
                "restore_copy_ms": exclusive_restore_ms,
                "start_to_first_connection_ms": exclusive_start_ms,
                "start_to_promoted_ms": exclusive_replay_ms,
                "validation_ms": exclusive_validation_ms,
                "promoted_state": exclusive_promoted,
                "effective_state": exclusive,
                "runtime_isolation": exclusive_runtime,
                "pig_result": exclusive_restore_result,
                "recovered_account_count": len(recovered_rows),
                "recovered_accounts_sha256":
                    hash_recovered_rows(recovered_rows),
                "patroni_managed": False,
            },
        )
        exclusive_cleanup = stop_and_remove_candidate(
            args.ssh_user,
            restore_host,
            exclusive_root,
            port,
        )
        cleaned_roots.add(exclusive_root)

        audited_post = post_target_rows(
            args.ssh_user,
            source_host,
            database,
            run_id,
        )
        expected_post_ids = set(range(victim_start, post_end + 1))
        post_map = {
            int(row["account_id"]): int(row["amount_cents"])
            for row in audited_post
            if isinstance(row, dict)
        }
        if (
            set(post_map) != expected_post_ids
            or any(value != post_delta for value in post_map.values())
        ):
            raise ExerciseError("post-target audit set is incomplete")

        reconciliation_rows: list[dict[str, int]] = []
        recovered_ids: set[int] = set()
        for row in recovered_rows:
            account_id = int(row["account_id"])
            recovered_balance = int(row["balance_cents"])
            if row.get("status") != "active":
                raise ExerciseError("recovered account is not active")
            recovered_ids.add(account_id)
            delta = post_map.get(account_id, 0)
            reconciliation_rows.append(
                {
                    "account_id": account_id,
                    "recovered_balance_cents": recovered_balance,
                    "post_delta_cents": delta,
                    "expected_current_balance_cents": delta,
                }
            )
        if recovered_ids != set(range(victim_start, victim_end + 1)):
            raise ExerciseError("recovered account identity set drifted")

        reconciliation_started = time.monotonic()
        repair = execute_fixture_transaction(
            args.ssh_user,
            source_host,
            database,
            reconciliation_sql(
                run_id=run_id,
                rows=reconciliation_rows,
                victim_count=victim_count,
                outbox_count=int(fixture["wrong_outbox_events"]),
            ),
        )
        reconciliation_ms = elapsed_ms(reconciliation_started)
        final_manifest = source_manifest(
            args.ssh_user,
            source_host,
            database,
            run_id,
            victim_start,
            victim_count,
            post_count,
        )
        base_total = account_count * 100000 + (
            account_count * (account_count + 1) // 2
        )
        expected_total = (
            base_total
            + victim_count * safe_delta
            + post_count * post_delta
        )
        if (
            final_manifest.get("accounts") != account_count
            or final_manifest.get("total_balance_cents")
            != expected_total
            or final_manifest.get("victims", {}).get("active")
            != victim_count
            or final_manifest.get("victims", {}).get("mispriced") != 0
            or final_manifest.get("safe_ledger_count") != victim_count
            or final_manifest.get("post_ledger_count") != post_count
            or final_manifest.get("pending_outbox_count") != 0
            or final_manifest.get("canceled_outbox_count")
            != int(fixture["wrong_outbox_events"])
            or final_manifest.get("external_dispatch_count") != 0
        ):
            raise ExerciseError("reconciled source manifest is invalid")

        write_json(
            args.evidence_dir / "reconciliation.json",
            {
                "schema": "pg36-ch32-reconciliation-v1",
                "run_id": run_id,
                "method":
                    "exclusive-history-plus-audited-post-target-delta",
                "recovered_rows": len(recovered_rows),
                "audited_post_target_rows": len(audited_post),
                "conditional_rows_repaired": victim_count,
                "wrong_outbox_canceled":
                    int(fixture["wrong_outbox_events"]),
                "external_dispatch_count": 0,
                "raw_exclusive_missing_legitimate_writes": post_count,
                "reconciled_fixture_data_loss_rows": 0,
                "business_cutover_performed": False,
                "reconciliation_ms": reconciliation_ms,
                "repair_result": repair,
                "expected_manifest": {
                    "accounts": account_count,
                    "total_balance_cents": expected_total,
                    "victims_active": victim_count,
                    "safe_ledger_count": victim_count,
                    "post_ledger_count": post_count,
                    "pending_outbox_count": 0,
                    "canceled_outbox_count":
                        int(fixture["wrong_outbox_events"]),
                },
                "actual_manifest": final_manifest,
            },
        )

        cleanup = cleanup_fixture(
            args.ssh_user,
            source_host,
            database,
            run_id,
        )
        fixture_cleaned = True
        topology_after = patroni_list(args.ssh_user, source_host)
        require_stable_source(topology_after, requirements)
        source_after, source_system_after = source_sql_state(
            args.ssh_user,
            source_host,
            database,
            schema,
        )
        repository_after = pgbackrest_info(
            args.ssh_user,
            source_host,
            stanza,
        )
        prefix_after = restore_prefix_state(
            args.ssh_user,
            restore_host,
            str(restore_contract["root_prefix"]),
            port,
        )
        if (
            source_after.get("fixture_schema_exists") is not False
            or source_system_after != source_system_id
            or prefix_after.get("entries") != 0
            or prefix_after.get("tcp_listener") is not False
            or not backup_is_retained(
                repository_after,
                stanza,
                backup_label,
            )
        ):
            raise ExerciseError("postflight cleanup or retention failed")

        write_json(
            args.evidence_dir / "source-after.json",
            {
                "schema": "pg36-ch32-source-state-v1",
                "phase": "after",
                "topology": topology_after,
                "postgres": source_after,
                "source_system_identifier_unchanged": True,
                "repository": sanitized_repo_info(repository_after),
                "backup_label": backup_label,
                "backup_retained": True,
                "system_identifier_recorded": False,
            },
        )
        write_json(
            args.evidence_dir / "cleanup.json",
            {
                "schema": "pg36-ch32-cleanup-v1",
                "run_id": run_id,
                "fixture": cleanup,
                "inclusive": inclusive_cleanup,
                "exclusive": exclusive_cleanup,
                "restore_prefix": prefix_after,
                "exact_restore_roots_removed": True,
                "fixture_schema_removed": True,
                "backup_retained": True,
                "backup_expired": False,
                "archived_wal_deleted": False,
                "unrelated_process_terminated": False,
                "patroni_changed": False,
                "dcs_changed": False,
                "route_changed": False,
            },
        )

        manifest.update(
            {
                "completed_at": utc_now(),
                "status": "completed",
                "damage_xid_source": "pg36_ch32.incident_audit",
                "inclusive_candidate": "rejected",
                "exclusive_candidate": "accepted",
                "reconciliation": "completed",
                "cleanup": "completed",
                "fresh_backup_retained": True,
                "production_ch32_gate": "pending",
                "source_sha256": source_hashes(args.source_dir),
            }
        )
        write_json(
            args.evidence_dir / "exercise-manifest.json",
            manifest,
        )
        print("status=random-xid-pitr-reconciliation-complete")
        print(f"run_id={run_id}")
        print(f"backup_label={backup_label}")
        print("inclusive_candidate=rejected")
        print("exclusive_candidate=accepted")
        print("post_target_writes_preserved=100")
        print("fixture_schema=removed")
        print("restore_roots=removed")
        print("production_ch32_gate=pending")
        return 0
    except (LabError, KeyError, TypeError, ValueError, OSError) as exc:
        if args.evidence_dir.exists():
            write_json(
                args.evidence_dir / "failure.json",
                {
                    "schema": "pg36-ch32-failure-v1",
                    "failed_at": utc_now(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "run_id": run_id,
                    "production_approval": False,
                },
            )
        sys.stderr.write(f"chapter 32 exercise failed: {exc}\n")
        return 1
    finally:
        for root in candidate_roots:
            if root in cleaned_roots:
                continue
            try:
                stop_and_remove_candidate(
                    args.ssh_user,
                    str(
                        read_json(args.source_dir / "requirements.json")[
                            "target"
                        ]["restore_address"]
                    ),
                    root,
                    int(
                        read_json(args.source_dir / "requirements.json")[
                            "restore"
                        ]["port"]
                    ),
                )
            except BaseException as stop_error:
                sys.stderr.write(
                    "warning: emergency candidate cleanup failed: "
                    f"{stop_error}\n"
                )
        if (
            fixture_created
            and not fixture_cleaned
            and run_id is not None
        ):
            try:
                requirements = read_json(
                    args.source_dir / "requirements.json"
                )
                cleanup_fixture(
                    args.ssh_user,
                    str(requirements["target"]["source_address"]),
                    str(requirements["fixture"]["database"]),
                    run_id,
                )
            except BaseException as cleanup_error:
                sys.stderr.write(
                    "warning: exact fixture cleanup failed: "
                    f"{cleanup_error}\n"
                )


if __name__ == "__main__":
    raise SystemExit(main())
