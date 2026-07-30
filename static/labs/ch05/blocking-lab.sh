#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PGTZ=UTC

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch05/blocking-$(date -u +%Y%m%dT%H%M%SZ)}"
run_tag="$(date -u +%Y%m%dT%H%M%SZ)-$$"
blocker_app="pg36-ch05-blocker-${run_tag}"
waiter_app="pg36-ch05-waiter-${run_tag}"
controller_app="pg36-ch05-controller-${run_tag}"
target_order_id=1002
dashboard_hold_seconds="${PG36_DASHBOARD_HOLD_SECONDS:-0}"
blocker_os_pid=''
waiter_os_pid=''
blocker_backend_pid=''
waiter_backend_pid=''

usage() {
  printf '%s\n' \
    "usage: $0" \
    "required: PGSERVICEFILE points to a private PostgreSQL service file" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR" \
    "optional: PG36_DASHBOARD_HOLD_SECONDS=0..25 (default 0)"
}

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

if [[ ! "$dashboard_hold_seconds" =~ ^[0-9]+$ ]] \
   || ((dashboard_hold_seconds > 25)); then
  printf 'PG36_DASHBOARD_HOLD_SECONDS must be an integer from 0 to 25\n' >&2
  exit 64
fi

for command_name in psql sleep grep; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

mkdir -p "$evidence_dir"

controller_psql() {
  psql -X -w \
    --dbname="service=${pg_service} application_name=${controller_app}" \
    --set=ON_ERROR_STOP=1 \
    "$@"
}

query_scalar() {
  local sql="$1"
  controller_psql --no-align --tuples-only --quiet <<<"$sql"
}

cleanup() {
  local exit_status=$?
  trap - EXIT
  set +e

  controller_psql --quiet >/dev/null 2>&1 <<SQL
SELECT pg_catalog.pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE pid <> pg_catalog.pg_backend_pid()
  AND datname = current_database()
  AND application_name IN (
      '${blocker_app}',
      '${waiter_app}'
  );
SQL

  if [[ -n "$blocker_os_pid" ]]; then
    wait "$blocker_os_pid" >/dev/null 2>&1
  fi
  if [[ -n "$waiter_os_pid" ]]; then
    wait "$waiter_os_pid" >/dev/null 2>&1
  fi

  exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

baseline_fingerprint="$(
  query_scalar "
    SET ROLE pg36_owner;
    SELECT request_fingerprint
    FROM shop.sales_order
    WHERE order_id = ${target_order_id};
  "
)"

if [[ -z "$baseline_fingerprint" ]]; then
  printf 'could not read baseline order %s\n' "$target_order_id" >&2
  exit 1
fi

psql -X -w \
  --dbname="service=${pg_service} application_name=${blocker_app}" \
  --set=ON_ERROR_STOP=1 \
  --set=target_order_id="$target_order_id" \
  --set=hold_seconds=45 \
  --file="$script_dir/blocking-blocker.sql" \
  >"$evidence_dir/blocker.stdout" \
  2>"$evidence_dir/blocker.stderr" &
blocker_os_pid=$!

for ((attempt = 1; attempt <= 200; attempt++)); do
  blocker_backend_pid="$(
    query_scalar "
      SELECT pid
      FROM pg_catalog.pg_stat_activity
      WHERE datname = current_database()
        AND application_name = '${blocker_app}'
        AND state = 'active'
        AND wait_event_type = 'Timeout'
        AND wait_event = 'PgSleep';
    "
  )"
  if [[ "$blocker_backend_pid" =~ ^[0-9]+$ ]]; then
    break
  fi
  sleep 0.05
done

if [[ ! "$blocker_backend_pid" =~ ^[0-9]+$ ]]; then
  printf 'blocker never reached the controlled hold point\n' >&2
  exit 1
fi

reader_fingerprint="$(
  query_scalar "
    SET statement_timeout = '1s';
    SET ROLE pg36_owner;
    SELECT request_fingerprint
    FROM shop.sales_order
    WHERE order_id = ${target_order_id};
  "
)"

if [[ "$reader_fingerprint" != "$baseline_fingerprint" ]]; then
  printf 'plain reader did not see the previous committed tuple version\n' >&2
  exit 1
fi

psql -X -w \
  --dbname="service=${pg_service} application_name=${waiter_app}" \
  --set=ON_ERROR_STOP=1 \
  --set=target_order_id="$target_order_id" \
  --file="$script_dir/blocking-waiter.sql" \
  >"$evidence_dir/waiter.stdout" \
  2>"$evidence_dir/waiter.stderr" &
waiter_os_pid=$!

waiter_observation=''
for ((attempt = 1; attempt <= 200; attempt++)); do
  waiter_observation="$(
    query_scalar "
      SELECT
          pid::text || '|' ||
          pg_catalog.array_to_string(
              pg_catalog.pg_blocking_pids(pid),
              ','
          ) || '|' ||
          COALESCE(wait_event_type, '<none>') || '|' ||
          COALESCE(wait_event, '<none>')
      FROM pg_catalog.pg_stat_activity
      WHERE datname = current_database()
        AND application_name = '${waiter_app}'
        AND state = 'active'
        AND wait_event_type = 'Lock';
    "
  )"
  if [[ -n "$waiter_observation" ]]; then
    IFS='|' read -r waiter_backend_pid blockers \
      waiter_wait_type waiter_wait_event <<<"$waiter_observation"
    if [[ "$waiter_backend_pid" =~ ^[0-9]+$ ]] \
       && [[ "$blockers" = "$blocker_backend_pid" ]]; then
      break
    fi
  fi
  sleep 0.05
done

if [[ ! "$waiter_backend_pid" =~ ^[0-9]+$ ]] \
   || [[ "${blockers:-}" != "$blocker_backend_pid" ]] \
   || [[ "${waiter_wait_type:-}" != 'Lock' ]]; then
  printf 'waiter did not produce the expected one-edge blocking chain\n' >&2
  exit 1
fi

controller_psql --csv >"$evidence_dir/activity.csv" <<SQL
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    backend_xid,
    backend_xmin,
    pg_catalog.pg_blocking_pids(pid) AS blocking_pids,
    pg_catalog.left(
        pg_catalog.regexp_replace(query, '[[:space:]]+', ' ', 'g'),
        160
    ) AS query
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
  AND application_name IN (
      '${blocker_app}',
      '${waiter_app}'
  )
ORDER BY application_name;
SQL

controller_psql --csv >"$evidence_dir/locks.csv" <<SQL
SELECT
    a.application_name,
    l.pid,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::pg_catalog.regclass AS relation,
    l.page,
    l.tuple,
    l.transactionid,
    l.virtualxid,
    l.fastpath,
    l.waitstart
FROM pg_catalog.pg_locks AS l
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = l.pid
WHERE a.datname = current_database()
  AND a.application_name IN (
      '${blocker_app}',
      '${waiter_app}'
  )
ORDER BY a.application_name, l.granted, l.locktype, l.mode;
SQL

if ((dashboard_hold_seconds > 0)); then
  sleep "$dashboard_hold_seconds"
fi

cancel_result="$(
  query_scalar "
    SELECT pg_catalog.pg_cancel_backend(pid)
    FROM pg_catalog.pg_stat_activity
    WHERE pid = ${blocker_backend_pid}
      AND datname = current_database()
      AND application_name = '${blocker_app}';
  "
)"

if [[ "$cancel_result" != 't' ]]; then
  printf 'refused: exact blocker PID/application identity was not cancelled\n' >&2
  exit 1
fi

if wait "$blocker_os_pid"; then
  blocker_exit=0
else
  blocker_exit=$?
fi
blocker_os_pid=''

if [[ "$blocker_exit" -ne 3 ]] \
   || ! grep -Fq 'ERROR:  57014' "$evidence_dir/blocker.stderr"; then
  printf 'blocker did not exit through the expected SQLSTATE 57014 path\n' >&2
  exit 1
fi

if wait "$waiter_os_pid"; then
  waiter_exit=0
else
  waiter_exit=$?
fi
waiter_os_pid=''

if [[ "$waiter_exit" -ne 0 ]]; then
  printf 'waiter did not acquire the row after blocker rollback\n' >&2
  exit 1
fi

final_fingerprint="$(
  query_scalar "
    SET ROLE pg36_owner;
    SELECT request_fingerprint
    FROM shop.sales_order
    WHERE order_id = ${target_order_id};
  "
)"

remaining_workers="$(
  query_scalar "
    SELECT count(*)
    FROM pg_catalog.pg_stat_activity
    WHERE datname = current_database()
      AND application_name IN (
          '${blocker_app}',
          '${waiter_app}'
      );
  "
)"

if [[ "$final_fingerprint" != "$baseline_fingerprint" ]]; then
  printf 'blocking lab changed persistent order state\n' >&2
  exit 1
fi

if [[ "$remaining_workers" != '0' ]]; then
  printf 'blocking lab left worker sessions connected\n' >&2
  exit 1
fi

{
  printf 'status=ok\n'
  printf 'target_order_id=%s\n' "$target_order_id"
  printf 'blocker_pid=%s\n' "$blocker_backend_pid"
  printf 'waiter_pid=%s\n' "$waiter_backend_pid"
  printf 'reader_visible_fingerprint=%s\n' "$reader_fingerprint"
  printf 'reader_saw_previous_committed_version=true\n'
  printf 'waiter_blocked_by=%s\n' "$blockers"
  printf 'waiter_wait_event_type=%s\n' "$waiter_wait_type"
  printf 'waiter_wait_event=%s\n' "$waiter_wait_event"
  printf 'dashboard_hold_seconds=%s\n' "$dashboard_hold_seconds"
  printf 'cancel_exact_blocker=%s\n' "$cancel_result"
  printf 'blocker_expected_nonzero_exit=%s\n' "$blocker_exit"
  printf 'waiter_exit=%s\n' "$waiter_exit"
  printf 'state_restored=true\n'
  printf 'remaining_workers=%s\n' "$remaining_workers"
} >"$evidence_dir/summary.txt"

printf 'status=ok evidence=%s\n' "$evidence_dir"
