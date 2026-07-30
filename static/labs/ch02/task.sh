#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch02/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch02-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|verify|baseline|inject-error|all|reset}" \
    "required: PGSERVICEFILE points to a private PostgreSQL service file" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR" \
    "reset only: PG36_RESET_TOKEN=RESET_CH02_FIXTURE"
}

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

for command_name in psql pgbench sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

mkdir -p "$evidence_dir"

run_psql_file() {
  local sql_file="$1"
  shift
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    "$@" \
    --file="$sql_file"
}

write_manifest() {
  {
    printf 'captured_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'service=%s\n' "$pg_service"
    printf 'psql_client=%s\n' "$(psql --version)"
    printf 'pgbench_client=%s\n' "$(pgbench --version)"
    sha256sum \
      "$script_dir/context.sql" \
      "$script_dir/setup.sql" \
      "$script_dir/verify.sql" \
      "$script_dir/workload.sql" \
      "$script_dir/broken.sql" \
      "$script_dir/reset.sql" \
      "$script_dir/task.sh"
    psql -X -w \
      --dbname="$connection" \
      --set=ON_ERROR_STOP=1 \
      --tuples-only \
      --no-align \
      --command="
        SELECT 'server_version=' || current_setting('server_version')
        UNION ALL
        SELECT 'database=' || current_database()
        UNION ALL
        SELECT 'session_user=' || session_user
        UNION ALL
        SELECT 'in_recovery=' || pg_is_in_recovery();
      "
  } >"$evidence_dir/manifest.txt"
}

run_setup() {
  run_psql_file "$script_dir/setup.sql" \
    >"$evidence_dir/setup.stdout" \
    2>"$evidence_dir/setup.stderr"
}

run_verify() {
  run_psql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
}

run_baseline() {
  pgbench \
    --random-seed=20260729 \
    --no-vacuum \
    --client=1 \
    --jobs=1 \
    --transactions=20 \
    --report-per-command \
    --file="$script_dir/workload.sql" \
    "$connection" \
    >"$evidence_dir/pgbench.txt" \
    2>"$evidence_dir/pgbench.stderr"
}

run_error_injection() {
  local exit_code
  local marker_count

  set +e
  psql -X -w \
    --single-transaction \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --file="$script_dir/broken.sql" \
    >"$evidence_dir/broken.stdout" \
    2>"$evidence_dir/broken.stderr"
  exit_code=$?
  set -e

  printf 'exit_code=%s\n' "$exit_code" >"$evidence_dir/broken.status"
  if [[ "$exit_code" -ne 3 ]]; then
    printf 'expected psql exit code 3, got %s\n' "$exit_code" >&2
    exit 70
  fi

  marker_count="$(
    psql -X -w \
      --dbname="$connection" \
      --set=ON_ERROR_STOP=1 \
      --tuples-only \
      --no-align \
      --command="
        SELECT count(*)
        FROM shop.ch02_fixture
        WHERE fixture_id = 999;
      "
  )"

  if [[ "$marker_count" != "0" ]]; then
    printf 'rollback verification failed: marker_count=%s\n' "$marker_count" >&2
    exit 70
  fi
  printf 'rollback_marker_count=%s\n' "$marker_count" \
    >>"$evidence_dir/broken.status"
}

case "$action" in
  setup)
    write_manifest
    run_setup
    ;;
  verify)
    write_manifest
    run_verify
    ;;
  baseline)
    write_manifest
    run_verify
    run_baseline
    ;;
  inject-error)
    write_manifest
    run_verify
    run_error_injection
    ;;
  all)
    write_manifest
    run_setup
    run_verify
    run_baseline
    run_error_injection
    ;;
  reset)
    if [[ "${PG36_RESET_TOKEN:-}" != "RESET_CH02_FIXTURE" ]]; then
      printf '%s\n' \
        'reset refused: set PG36_RESET_TOKEN=RESET_CH02_FIXTURE' >&2
      exit 64
    fi
    write_manifest
    run_psql_file "$script_dir/reset.sql" \
      --set=confirm_reset="$PG36_RESET_TOKEN" \
      >"$evidence_dir/reset.stdout" \
      2>"$evidence_dir/reset.stderr"
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
