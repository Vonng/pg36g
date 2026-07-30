#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch08/client-$(date -u +%Y%m%dT%H%M%SZ)}"
pg_service="${PGSERVICE:-pg36-admin}"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
worker_app="pg36-ch08-client-${run_id}"
observer_app="pg36-ch08-observer-${run_id}"
worker_connection="service=${pg_service} application_name=${worker_app}"
observer_connection="service=${pg_service} application_name=${observer_app}"
pipeline_pid=''
backend_pid=''
observed=false

usage() {
  printf '%s\n' \
    "usage: $0" \
    "requires PGSERVICEFILE and a writable ch04-v1 L1" \
    "optional: PGSERVICE, PG36_EVIDENCE_DIR"
}

for command_name in bash grep psql python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

mkdir -p "$evidence_dir"

observe_scalar() {
  local sql="$1"
  psql -X -w -qAt \
    --dbname="$observer_connection" \
    --set=ON_ERROR_STOP=1 \
    --command="$sql"
}

cleanup() {
  local original_exit=$?
  set +e
  if [[ -n "$worker_app" ]]; then
    psql -X -w -qAt \
      --dbname="$observer_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT pg_catalog.pg_terminate_backend(pid)
        FROM pg_catalog.pg_stat_activity
        WHERE datname = 'pg36_shop'
          AND application_name = '${worker_app}'
          AND pid <> pg_catalog.pg_backend_pid();
      " >/dev/null 2>&1
  fi
  if [[ -n "$pipeline_pid" ]]; then
    wait "$pipeline_pid" >/dev/null 2>&1
  fi
  exit "$original_exit"
}
trap cleanup EXIT INT TERM

psql -X -w -qAt \
  --dbname="$observer_connection" \
  --set=ON_ERROR_STOP=1 \
  --file="$script_dir/../ch07/context.sql" \
  >"$evidence_dir/preflight.txt" \
  2>"$evidence_dir/preflight.stderr"

set +e
(
  psql -X -w -qAt \
    --dbname="$worker_connection" \
    --set=ON_ERROR_STOP=1 \
    --command="
      COPY (
        SELECT pg_catalog.repeat('x', 8192)
        FROM pg_catalog.generate_series(1, 50000)
      ) TO STDOUT;
    " \
    2>"$evidence_dir/worker.stderr" \
  | "$script_dir/slow-reader.py" \
      --chunk-bytes 4096 \
      --delay-ms 100 \
      2>"$evidence_dir/reader.stderr"
) &
pipeline_pid=$!
set -e

for _ in $(seq 1 160); do
  snapshot="$(
    psql -X -w -qAt -F '|' \
      --dbname="$observer_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT
            pid,
            extract(epoch FROM backend_start)::bigint,
            state,
            coalesce(wait_event_type, ''),
            coalesce(wait_event, ''),
            cardinality(pg_catalog.pg_blocking_pids(pid))
        FROM pg_catalog.pg_stat_activity
        WHERE datname = 'pg36_shop'
          AND application_name = '${worker_app}';
      "
  )"
  if [[ -n "$snapshot" ]]; then
    IFS='|' read -r backend_pid backend_start_epoch state wait_type wait_event blocker_count \
      <<<"$snapshot"
    if [[ "$state" == 'active' \
       && "$wait_type" == 'Client' \
       && "$wait_event" == 'ClientWrite' \
       && "$blocker_count" == '0' ]]; then
      observed=true
      printf '%s\n' "$snapshot" >"$evidence_dir/observed.txt"
      break
    fi
  fi
  sleep 0.05
done

if [[ "$observed" != true ]]; then
  printf 'did not observe Client/ClientWrite within the polling window\n' >&2
  exit 1
fi

if [[ ! "$backend_pid" =~ ^[0-9]+$ \
   || ! "$backend_start_epoch" =~ ^[0-9]+$ ]]; then
  printf 'invalid backend identity captured\n' >&2
  exit 1
fi

psql -X -w --csv \
  --dbname="$observer_connection" \
  --set=ON_ERROR_STOP=1 \
  --command="
    SELECT
        clock_timestamp() AT TIME ZONE 'UTC' AS captured_at_utc,
        pid,
        backend_start,
        state,
        wait_event_type,
        wait_event,
        pg_catalog.pg_blocking_pids(pid) AS blocking_pids,
        query_start,
        left(query, 160) AS query_excerpt
    FROM pg_catalog.pg_stat_activity
    WHERE datname = 'pg36_shop'
      AND application_name = '${worker_app}';
  " >"$evidence_dir/activity.csv"

cancelled="$(
  psql -X -w -qAt \
    --dbname="$observer_connection" \
    --set=ON_ERROR_STOP=1 \
    --command="
      SELECT CASE
        WHEN count(*) = 1
        THEN pg_catalog.pg_cancel_backend(max(pid))
        ELSE false
      END
      FROM pg_catalog.pg_stat_activity
      WHERE pid = ${backend_pid}::integer
        AND extract(epoch FROM backend_start)::bigint
            = ${backend_start_epoch}::bigint
        AND datname = 'pg36_shop'
        AND application_name = '${worker_app}';
    "
)"

if [[ "$cancelled" != 't' ]]; then
  printf 'refused to cancel: exact client worker identity no longer matches\n' >&2
  exit 1
fi

set +e
wait "$pipeline_pid"
pipeline_exit=$?
set -e
pipeline_pid=''

remaining="$(
  observe_scalar "
    SELECT count(*)
    FROM pg_catalog.pg_stat_activity
    WHERE datname = 'pg36_shop'
      AND application_name = '${worker_app}';
  "
)"

if [[ "$remaining" != '0' ]]; then
  printf 'client worker remained after cancellation\n' >&2
  exit 1
fi

{
  printf 'status=ok\n'
  printf 'fixture=ch08-client-backpressure\n'
  printf 'state=active\n'
  printf 'wait_event_type=Client\n'
  printf 'wait_event=ClientWrite\n'
  printf 'blocking_pid_count=0\n'
  printf 'cancel_exact_worker=true\n'
  printf 'pipeline_nonzero_after_cancel=%s\n' \
    "$([[ "$pipeline_exit" -ne 0 ]] && printf true || printf false)"
  printf 'remaining_workers=%s\n' "$remaining"
} >"$evidence_dir/summary.txt"

cat "$evidence_dir/summary.txt"
trap - EXIT INT TERM
