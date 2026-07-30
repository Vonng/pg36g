#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch10/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch10-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|lost|isolation|locking|idempotency|verify|review|reset|all}" \
    "case actions rebuild the dedicated fixture before running" \
    "all/review run every interleaving, failure, final-state, and proposal assertion" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "all actions require PGSERVICEFILE and ch04-v1"
}

case "$action" in
  setup|lost|isolation|locking|idempotency|verify|review|reset|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash grep psql python3 sha256sum; do
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

run_sql_file() {
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
    printf 'python=%s\n' "$(python3 --version 2>&1)"
    printf 'psql_client=%s\n' "$(psql --version)"
    psql -X -w -qAt \
      --dbname="$connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT 'server_version=' || current_setting('server_version');
        SELECT 'database=' || current_database();
        SELECT 'user=' || current_user;
        SELECT 'in_recovery=' || pg_catalog.pg_is_in_recovery();
      "
    sha256sum "$script_dir"/*
  } >"$evidence_dir/manifest.txt"
}

run_preflight() {
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/preflight.txt" \
    2>"$evidence_dir/preflight.stderr"
}

run_setup() {
  run_sql_file "$script_dir/setup.sql" \
    >"$evidence_dir/setup.txt" \
    2>"$evidence_dir/setup.stderr"
}

run_case() {
  local case_name="$1"
  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/run_concurrency.py" \
      --case="$case_name" \
      --evidence-dir="$evidence_dir" \
      --service="$pg_service" \
      >"$evidence_dir/runner.txt" \
      2>"$evidence_dir/runner.stderr"
}

run_verify() {
  run_sql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
}

run_review() {
  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/review.py" \
      --evidence-dir="$evidence_dir" \
      --repo-root="$repo_root" \
      >"$evidence_dir/review.txt" \
      2>"$evidence_dir/review.stderr"
  cat "$evidence_dir/review.txt"
}

run_reset() {
  run_sql_file "$script_dir/reset.sql" \
    --set=reset_token="${PG36_RESET_TOKEN:-}" \
    --set=reset_target="${PG36_RESET_TARGET:-}" \
    >"$evidence_dir/reset.txt" \
    2>"$evidence_dir/reset.stderr"
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify-after-reset.txt" \
    2>"$evidence_dir/model-verify-after-reset.stderr"
}

write_manifest

case "$action" in
  setup)
    run_preflight
    run_setup
    ;;
  lost|isolation|locking|idempotency)
    run_preflight
    run_setup
    run_case "$action"
    run_sql_file "$script_dir/../ch05/verify.sql" \
      >"$evidence_dir/model-verify-after.txt" \
      2>"$evidence_dir/model-verify-after.stderr"
    ;;
  verify)
    run_verify
    ;;
  reset)
    run_preflight
    run_reset
    ;;
  review|all)
    run_preflight
    run_setup
    run_case all
    run_verify
    run_review
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
