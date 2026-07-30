#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch04/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch04-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {install|migrate|seed|verify|negative|constraints|review|all|reset}" \
    "required: PGSERVICEFILE points to a private PostgreSQL service file" \
    "all/migrate prerequisite: the ch03-v0 model is installed" \
    "install: fresh schema-v1 install plus deterministic v1 seed" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR" \
    "reset only: PG36_RESET_TOKEN=RESET_CH04_MODEL"
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
      "$script_dir/schema-v1.sql" \
      "$script_dir/migrate-v0-to-v1.sql" \
      "$script_dir/seed-v1.sql" \
      "$script_dir/verify-v1.sql" \
      "$script_dir/negative-cases.sql" \
      "$script_dir/constraint-lab.sql" \
      "$script_dir/physical-decisions.md" \
      "$script_dir/partition-adr.md" \
      "$script_dir/model-v1.mmd" \
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

run_migrate() {
  run_psql_file "$script_dir/migrate-v0-to-v1.sql" \
    >"$evidence_dir/migrate.stdout" \
    2>"$evidence_dir/migrate.stderr"
}

run_schema() {
  run_psql_file "$script_dir/schema-v1.sql" \
    >"$evidence_dir/schema.stdout" \
    2>"$evidence_dir/schema.stderr"
}

run_seed() {
  run_psql_file "$script_dir/seed-v1.sql" \
    >"$evidence_dir/seed.stdout" \
    2>"$evidence_dir/seed.stderr"
}

run_verify() {
  run_psql_file "$script_dir/verify-v1.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
}

run_negative() {
  run_psql_file "$script_dir/negative-cases.sql" \
    >"$evidence_dir/negative.txt" \
    2>"$evidence_dir/negative.stderr"
}

run_constraints() {
  run_psql_file "$script_dir/constraint-lab.sql" \
    >"$evidence_dir/constraints.txt" \
    2>"$evidence_dir/constraints.stderr"
}

case "$action" in
  install)
    write_manifest
    run_schema
    run_seed
    run_verify
    run_negative
    run_constraints
    ;;
  migrate)
    write_manifest
    run_migrate
    ;;
  seed)
    write_manifest
    run_seed
    ;;
  verify)
    write_manifest
    run_verify
    ;;
  negative)
    write_manifest
    run_verify
    run_negative
    ;;
  constraints)
    write_manifest
    run_constraints
    ;;
  review)
    write_manifest
    run_verify
    run_negative
    run_constraints
    ;;
  all)
    write_manifest
    run_migrate
    run_verify
    run_negative
    run_constraints
    ;;
  reset)
    if [[ "${PG36_RESET_TOKEN:-}" != "RESET_CH04_MODEL" ]]; then
      printf '%s\n' \
        'reset refused: set PG36_RESET_TOKEN=RESET_CH04_MODEL' >&2
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
