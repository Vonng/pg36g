#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch09/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch09-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|candidates|write|concurrent|verify|review|reset|all}" \
    "candidates/write/concurrent rebuild their dedicated fixture first" \
    "all/review run every read, write, failure, cleanup, and proposal assertion" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "all actions require PGSERVICEFILE and ch04-v1"
}

case "$action" in
  setup|candidates|write|concurrent|verify|review|reset|all)
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

capture_plan() {
  local sql_file="$1"
  local output_file="$2"
  shift 2
  psql -X -w -qAt \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    "$@" \
    --file="$sql_file" \
    >"$output_file"
  python3 -m json.tool "$output_file" >/dev/null
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

run_candidates() {
  capture_plan \
    "$script_dir/order-query.sql" \
    "$evidence_dir/order-before.json"
  capture_plan \
    "$script_dir/inventory-query.sql" \
    "$evidence_dir/inventory-before.json"
  capture_plan \
    "$script_dir/search-query.sql" \
    "$evidence_dir/search-before.json"
  capture_plan \
    "$script_dir/event-query.sql" \
    "$evidence_dir/event-before.json"

  "$script_dir/create-candidates.sh" primary \
    >"$evidence_dir/create-primary.txt" \
    2>"$evidence_dir/create-primary.stderr"
  run_sql_file "$script_dir/vacuum-candidates.sql" \
    >"$evidence_dir/vacuum-candidates.txt" \
    2>"$evidence_dir/vacuum-candidates.stderr"

  capture_plan \
    "$script_dir/order-query.sql" \
    "$evidence_dir/order-after.json"
  capture_plan \
    "$script_dir/inventory-query.sql" \
    "$evidence_dir/inventory-after.json"
  capture_plan \
    "$script_dir/search-query.sql" \
    "$evidence_dir/search-after.json"
  capture_plan \
    "$script_dir/event-query.sql" \
    "$evidence_dir/event-brin.json"
  capture_plan \
    "$script_dir/order-parameter.sql" \
    "$evidence_dir/order-custom.json" \
    --set=plan_mode=force_custom_plan
  capture_plan \
    "$script_dir/order-parameter.sql" \
    "$evidence_dir/order-generic.json" \
    --set=plan_mode=force_generic_plan

  "$script_dir/create-candidates.sh" event-btree \
    >"$evidence_dir/create-event-btree.txt" \
    2>"$evidence_dir/create-event-btree.stderr"
  capture_plan \
    "$script_dir/event-query.sql" \
    "$evidence_dir/event-btree.json"

  run_sql_file "$script_dir/catalog.sql" --csv --quiet \
    >"$evidence_dir/catalog-before-rejection.csv" \
    2>"$evidence_dir/catalog-before-rejection.stderr"
  "$script_dir/create-candidates.sh" drop-event-btree \
    >"$evidence_dir/drop-event-btree.txt" \
    2>"$evidence_dir/drop-event-btree.stderr"
  run_sql_file "$script_dir/catalog.sql" --csv --quiet \
    >"$evidence_dir/catalog-final.csv" \
    2>"$evidence_dir/catalog-final.stderr"
}

run_write() {
  capture_plan \
    "$script_dir/write-base.sql" \
    "$evidence_dir/write-base.json"
  capture_plan \
    "$script_dir/write-indexed.sql" \
    "$evidence_dir/write-indexed.json"
  run_sql_file "$script_dir/write-stats.sql" --csv --quiet \
    >"$evidence_dir/write-stats.csv" \
    2>"$evidence_dir/write-stats.stderr"
  run_sql_file "$script_dir/restore-write.sql" \
    >"$evidence_dir/restore-write.txt" \
    2>"$evidence_dir/restore-write.stderr"
}

run_concurrent() {
  mkdir -p "$evidence_dir/concurrent-failure"
  PG36_EVIDENCE_DIR="$evidence_dir/concurrent-failure" \
    "$script_dir/concurrent-failure.sh" \
    >"$evidence_dir/concurrent-failure.txt" \
    2>"$evidence_dir/concurrent-failure.stderr"
}

run_verify() {
  run_sql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
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

run_analysis() {
  "$script_dir/analyze_indexes.py" \
    --evidence-dir "$evidence_dir" \
    --repo-root "$repo_root" \
    >"$evidence_dir/index-summary.txt" \
    2>"$evidence_dir/index-summary.stderr"
  cat "$evidence_dir/index-summary.txt"
}

write_manifest

case "$action" in
  setup)
    run_preflight
    run_setup
    ;;
  candidates)
    run_preflight
    run_setup
    run_candidates
    run_verify
    ;;
  write)
    run_preflight
    run_setup
    run_write
    run_sql_file "$script_dir/../ch05/verify.sql" \
      >"$evidence_dir/model-verify-after.txt" \
      2>"$evidence_dir/model-verify-after.stderr"
    ;;
  concurrent)
    run_preflight
    run_setup
    run_concurrent
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
    run_candidates
    run_write
    run_concurrent
    run_verify
    run_analysis
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
