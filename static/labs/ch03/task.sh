#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch03/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch03-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|seed|verify|review|all|reset}" \
    "required: PGSERVICEFILE points to a private PostgreSQL service file" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR" \
    "reset only: PG36_RESET_TOKEN=RESET_CH03_MODEL"
}

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

for command_name in psql sha256sum; do
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
    sha256sum \
      "$script_dir/context.sql" \
      "$script_dir/setup.sql" \
      "$script_dir/seed.sql" \
      "$script_dir/verify.sql" \
      "$script_dir/review.sql" \
      "$script_dir/reset.sql" \
      "$script_dir/requirements.md" \
      "$script_dir/open-decisions.md" \
      "$script_dir/model.mmd" \
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

run_seed() {
  run_psql_file "$script_dir/seed.sql" \
    >"$evidence_dir/seed.stdout" \
    2>"$evidence_dir/seed.stderr"
}

run_verify() {
  run_psql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
}

run_review() {
  run_psql_file "$script_dir/review.sql" \
    >"$evidence_dir/review.txt" \
    2>"$evidence_dir/review.stderr"
}

case "$action" in
  setup)
    write_manifest
    run_setup
    ;;
  seed)
    write_manifest
    run_seed
    ;;
  verify)
    write_manifest
    run_verify
    ;;
  review)
    write_manifest
    run_verify
    run_review
    ;;
  all)
    write_manifest
    run_setup
    run_seed
    run_verify
    run_review
    ;;
  reset)
    if [[ "${PG36_RESET_TOKEN:-}" != "RESET_CH03_MODEL" ]]; then
      printf '%s\n' \
        'reset refused: set PG36_RESET_TOKEN=RESET_CH03_MODEL' >&2
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
