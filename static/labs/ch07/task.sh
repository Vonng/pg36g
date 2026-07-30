#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch07/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch07-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|stats|parameters|partition|verify|review|reset|all}" \
    "all/review rebuild the dedicated fixture and leave it for inspection" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "all actions require PGSERVICEFILE and ch04-v1"
}

case "$action" in
  setup|stats|parameters|partition|verify|review|reset|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3 psql sha256sum; do
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

run_psql_file() {
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
    sha256sum "$script_dir"/*
  } >"$evidence_dir/manifest.txt"
}

run_preflight() {
  run_psql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify-before.txt" \
    2>"$evidence_dir/model-verify-before.stderr"
}

run_setup() {
  run_psql_file "$script_dir/setup.sql" \
    >"$evidence_dir/setup.txt" \
    2>"$evidence_dir/setup.stderr"
}

run_stats() {
  capture_plan \
    "$script_dir/correlation-present.sql" \
    "$evidence_dir/stats-before-present.json"
  capture_plan \
    "$script_dir/correlation-impossible.sql" \
    "$evidence_dir/stats-before-impossible.json"

  run_psql_file "$script_dir/apply-extended-statistics.sql" \
    >"$evidence_dir/apply-extended-statistics.txt" \
    2>"$evidence_dir/apply-extended-statistics.stderr"

  capture_plan \
    "$script_dir/correlation-present.sql" \
    "$evidence_dir/stats-after-present.json"
  capture_plan \
    "$script_dir/correlation-impossible.sql" \
    "$evidence_dir/stats-after-impossible.json"
}

run_parameters() {
  capture_plan \
    "$script_dir/parameter-plan.sql" \
    "$evidence_dir/parameter-custom-hot.json" \
    --set=plan_mode=force_custom_plan \
    --set=tenant_id=1
  capture_plan \
    "$script_dir/parameter-plan.sql" \
    "$evidence_dir/parameter-custom-cold.json" \
    --set=plan_mode=force_custom_plan \
    --set=tenant_id=1001
  capture_plan \
    "$script_dir/parameter-plan.sql" \
    "$evidence_dir/parameter-generic-hot.json" \
    --set=plan_mode=force_generic_plan \
    --set=tenant_id=1
  capture_plan \
    "$script_dir/parameter-plan.sql" \
    "$evidence_dir/parameter-generic-cold.json" \
    --set=plan_mode=force_generic_plan \
    --set=tenant_id=1001
}

run_partition() {
  psql -X -w -qAt \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --command="
      SELECT count(*)
      FROM pg_catalog.pg_stats
      WHERE schemaname = 'shop_private'
        AND tablename = 'ch07_event_probe';
    " >"$evidence_dir/partition-parent-stats-before.txt"

  capture_plan \
    "$script_dir/partition-constant.sql" \
    "$evidence_dir/partition-constant.json"
  capture_plan \
    "$script_dir/partition-wrapped.sql" \
    "$evidence_dir/partition-wrapped.json"
  capture_plan \
    "$script_dir/partition-generic.sql" \
    "$evidence_dir/partition-generic.json"

  run_psql_file "$script_dir/analyze-partition-parent.sql" \
    >"$evidence_dir/analyze-partition-parent.txt" \
    2>"$evidence_dir/analyze-partition-parent.stderr"

  psql -X -w -qAt \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --command="
      SELECT count(*)
      FROM pg_catalog.pg_stats
      WHERE schemaname = 'shop_private'
        AND tablename = 'ch07_event_probe';
    " >"$evidence_dir/partition-parent-stats-after.txt"
}

run_analysis() {
  local scope="$1"
  "$script_dir/analyze_plans.py" \
    --evidence-dir "$evidence_dir" \
    --repo-root "$repo_root" \
    --scope "$scope" \
    >"$evidence_dir/plan-summary-${scope}.txt" \
    2>"$evidence_dir/plan-summary-${scope}.stderr"
}

run_verify() {
  run_psql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
  run_psql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify-after.txt" \
    2>"$evidence_dir/model-verify-after.stderr"
}

run_reset() {
  run_psql_file "$script_dir/reset.sql" \
    --set=reset_token="${PG36_RESET_TOKEN:-}" \
    --set=reset_target="${PG36_RESET_TARGET:-}" \
    >"$evidence_dir/reset.txt" \
    2>"$evidence_dir/reset.stderr"
  run_psql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify-after-reset.txt" \
    2>"$evidence_dir/model-verify-after-reset.stderr"
}

write_manifest

case "$action" in
  setup)
    run_preflight
    run_setup
    ;;
  stats)
    run_preflight
    run_stats
    run_analysis stats
    ;;
  parameters)
    run_preflight
    run_parameters
    run_analysis parameters
    ;;
  partition)
    run_preflight
    run_partition
    run_analysis partition
    ;;
  verify)
    run_preflight
    run_verify
    ;;
  reset)
    run_preflight
    run_reset
    ;;
  review|all)
    run_preflight
    run_setup
    run_stats
    run_parameters
    run_partition
    run_analysis all
    run_verify
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
