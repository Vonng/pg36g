#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch17/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} dbname=pg36_shop application_name=pg36-ch17-${action}"
maintenance_connection="service=${pg_service} dbname=postgres application_name=pg36-ch17-bootstrap"
app_connection="service=${pg_service} dbname=pg36_shop user=pg36_app application_name=pg36-ch17-app"
reset_worker_pid=""
reset_backend_pid=""
fdw_host=""
fdw_port=""

usage() {
  printf '%s\n' \
    "usage: $0 {setup|evaluate|verify|review|reset|all}" \
    "all proves four equivalent result paths, planner shapes, FDW failure boundaries, exact reset, and rebuild" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET for the coordinator; both shard schemas are verified and reset too" \
    "database actions require PGSERVICEFILE and the verified ch04 roles/database"
}

case "$action" in
  setup|evaluate|verify|review|reset|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash cmp grep psql python3 sort
do
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

cleanup() {
  if [[ -n "$reset_backend_pid" ]]; then
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT pg_catalog.pg_cancel_backend(pid)
        FROM pg_catalog.pg_stat_activity
        WHERE pid = ${reset_backend_pid}
          AND datname = current_database()
          AND application_name =
              'pg36-ch17-active-reset';
      " >/dev/null 2>&1 || true
  fi
  if [[ -n "$reset_worker_pid" ]] \
     && kill -0 "$reset_worker_pid" 2>/dev/null; then
    kill -TERM "$reset_worker_pid" 2>/dev/null || true
    wait "$reset_worker_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

hash_file() {
  local file_path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path"
  else
    shasum -a 256 "$file_path"
  fi
}

canonical_json_checksum() {
  local file_path="$1"
  python3 - "$file_path" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
encoded = json.dumps(
    document,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
print(hashlib.sha256(encoded).hexdigest())
PY
}

discover_fdw_endpoint() {
  fdw_host="$(
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="SHOW unix_socket_directories;"
  )"
  fdw_port="$(
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="SHOW port;"
  )"

  if [[ -z "$fdw_host" || -z "$fdw_port" ]]; then
    printf 'could not discover the local FDW endpoint\n' >&2
    exit 1
  fi
}

run_bootstrap_sql() {
  local sql_file="$1"
  shift
  psql -X -w \
    --dbname="$maintenance_connection" \
    --set=ON_ERROR_STOP=1 \
    "$@" \
    --file="$sql_file"
}

run_admin_sql() {
  local sql_file="$1"
  shift
  psql -X -w \
    --dbname="$admin_connection" \
    --set=ON_ERROR_STOP=1 \
    --set="fdw_host=${fdw_host}" \
    --set="fdw_port=${fdw_port}" \
    "$@" \
    --file="$sql_file"
}

remote_connection() {
  local database_name="$1"
  printf 'service=%s dbname=%s application_name=pg36-ch17-remote-%s' \
    "$pg_service" "$database_name" "$action"
}

run_remote_sql() {
  local database_name="$1"
  local remainder="$2"
  local marker="$3"
  local sql_file="$4"
  shift 4
  psql -X -w \
    --dbname="$(remote_connection "$database_name")" \
    --set=ON_ERROR_STOP=1 \
    --set="expected_database=${database_name}" \
    --set="shard_remainder=${remainder}" \
    --set="shard_marker=${marker}" \
    "$@" \
    --file="$sql_file"
}

capture_admin_csv() {
  local sql_file="$1"
  local output_file="$2"
  run_admin_sql "$sql_file" --csv --quiet \
    >"$output_file" \
    2>"${output_file%.csv}.stderr"
}

capture_admin_text() {
  local sql_file="$1"
  local output_file="$2"
  run_admin_sql "$sql_file" --quiet \
    >"$output_file" \
    2>"${output_file%.*}.stderr"
}

capture_remote_csv() {
  local database_name="$1"
  local remainder="$2"
  local marker="$3"
  local sql_file="$4"
  local output_file="$5"
  run_remote_sql \
    "$database_name" \
    "$remainder" \
    "$marker" \
    "$sql_file" \
    --csv \
    --quiet \
    >"$output_file" \
    2>"${output_file%.csv}.stderr"
}

capture_remote_text() {
  local database_name="$1"
  local remainder="$2"
  local marker="$3"
  local sql_file="$4"
  local output_file="$5"
  run_remote_sql \
    "$database_name" \
    "$remainder" \
    "$marker" \
    "$sql_file" \
    --quiet \
    >"$output_file" \
    2>"${output_file%.*}.stderr"
}

capture_app_csv() {
  local sql_file="$1"
  local output_file="$2"
  psql -X -w \
    --dbname="$app_connection" \
    --set=ON_ERROR_STOP=1 \
    --csv \
    --quiet \
    --file="$sql_file" \
    >"$output_file" \
    2>"${output_file%.csv}.stderr"
}

run_expected_failure() {
  local connection="$1"
  local sql_file="$2"
  local name="$3"
  local sqlstate="$4"
  local output_dir="$5"
  shift 5

  set +e
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --set=VERBOSITY=verbose \
    "$@" \
    --file="$sql_file" \
    >"$output_dir/${name}.stdout" \
    2>"$output_dir/${name}.stderr"
  local exit_code=$?
  set -e

  printf 'exit=%s\n' "$exit_code" \
    >"$output_dir/${name}.exit"

  if [[ "$exit_code" -ne 3 ]] \
     || ! grep -Fq "$sqlstate" \
          "$output_dir/${name}.stderr"; then
    printf '%s did not fail with SQLSTATE %s\n' \
      "$name" "$sqlstate" >&2
    exit 1
  fi
}

write_manifest() {
  local output_dir="$1"
  local release_checksum
  local fixture_checksum
  release_checksum="$(
    canonical_json_checksum \
      "$script_dir/baseline-v1.5-proposal.json"
  )"
  fixture_checksum="$(
    canonical_json_checksum \
      "$script_dir/fixture-manifest.json"
  )"

  {
    printf 'captured_at=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'service=%s\n' "$pg_service"
    printf 'validation_path=direct-postgresql-loopback-fdw\n'
    printf 'pigsty_reference=4.4\n'
    printf 'pigsty_l1=not-run\n'
    printf 'model_version=ch04-v1\n'
    printf 'fixture=ch17-analytics-v1\n'
    printf 'distribution=explicit-list-by-tenant\n'
    printf 'fdw_host=%s\n' "$fdw_host"
    printf 'fdw_port=%s\n' "$fdw_port"
    printf 'authentication=lab-only-password_required=false\n'
    printf 'release_candidate_checksum=%s\n' \
      "$release_checksum"
    printf 'fixture_manifest_checksum=%s\n' \
      "$fixture_checksum"
    printf 'python=%s\n' "$(python3 --version 2>&1)"
    printf 'psql_client=%s\n' "$(psql --version)"
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT 'server_version=' ||
               current_setting('server_version');
        SELECT 'database=' || current_database();
        SELECT 'admin_session_user=' || session_user;
        SELECT 'in_recovery=' ||
               pg_catalog.pg_is_in_recovery();
        SELECT 'postgres_fdw=' || extversion
        FROM pg_catalog.pg_extension
        WHERE extname = 'postgres_fdw';
        SELECT 'shard_databases=' ||
               pg_catalog.string_agg(
                   datname,
                   ',' ORDER BY datname
               )
        FROM pg_catalog.pg_database
        WHERE datname IN (
            'pg36_shard_a',
            'pg36_shard_b'
        );
      "
    while IFS= read -r source_file; do
      hash_file "$source_file"
    done < <(
      find "$script_dir" -maxdepth 1 -type f -print \
        | sort
    )
  } >"$output_dir/manifest.txt"
}

bootstrap_and_setup() {
  local output_dir="$1"
  mkdir -p "$output_dir"

  run_bootstrap_sql "$script_dir/bootstrap.sql" \
    >"$output_dir/bootstrap.txt" \
    2>"$output_dir/bootstrap.stderr"

  run_remote_sql \
    "pg36_shard_a" \
    "0" \
    "pg36 ch17 shard 0 lab; safe to rebuild" \
    "$script_dir/remote-setup.sql" \
    >"$output_dir/remote-a-setup.txt" \
    2>"$output_dir/remote-a-setup.stderr"

  run_remote_sql \
    "pg36_shard_b" \
    "1" \
    "pg36 ch17 shard 1 lab; safe to rebuild" \
    "$script_dir/remote-setup.sql" \
    >"$output_dir/remote-b-setup.txt" \
    2>"$output_dir/remote-b-setup.stderr"

  run_admin_sql "$script_dir/setup.sql" \
    >"$output_dir/setup.txt" \
    2>"$output_dir/setup.stderr"
}

verify_all_databases() {
  local output_dir="$1"
  mkdir -p "$output_dir"

  capture_remote_text \
    "pg36_shard_a" \
    "0" \
    "pg36 ch17 shard 0 lab; safe to rebuild" \
    "$script_dir/remote-verify.sql" \
    "$output_dir/remote-a-verify.txt"
  capture_remote_text \
    "pg36_shard_b" \
    "1" \
    "pg36 ch17 shard 1 lab; safe to rebuild" \
    "$script_dir/remote-verify.sql" \
    "$output_dir/remote-b-verify.txt"
  capture_admin_text \
    "$script_dir/verify.sql" \
    "$output_dir/verify.txt"
}

collect_cycle() {
  local output_dir="$1"
  mkdir -p "$output_dir"

  bootstrap_and_setup "$output_dir"

  capture_admin_csv \
    "$script_dir/monthly-local-export.sql" \
    "$output_dir/monthly-local.csv"
  capture_admin_csv \
    "$script_dir/monthly-summary-export.sql" \
    "$output_dir/monthly-summary.csv"
  capture_admin_csv \
    "$script_dir/monthly-distributed-export.sql" \
    "$output_dir/monthly-distributed.csv"
  capture_admin_csv \
    "$script_dir/monthly-two-stage-export.sql" \
    "$output_dir/monthly-two-stage.csv"

  for monthly_file in \
    monthly-local.csv \
    monthly-summary.csv \
    monthly-distributed.csv \
    monthly-two-stage.csv
  do
    cmp "$script_dir/frozen-monthly.csv" \
        "$output_dir/$monthly_file"
  done

  capture_admin_csv \
    "$script_dir/fixture-facts.sql" \
    "$output_dir/fixture-facts.csv"
  capture_remote_csv \
    "pg36_shard_a" \
    "0" \
    "pg36 ch17 shard 0 lab; safe to rebuild" \
    "$script_dir/remote-state.sql" \
    "$output_dir/remote-a-state.csv"
  capture_remote_csv \
    "pg36_shard_b" \
    "1" \
    "pg36 ch17 shard 1 lab; safe to rebuild" \
    "$script_dir/remote-state.sql" \
    "$output_dir/remote-b-state.csv"

  capture_admin_csv \
    "$script_dir/server-catalog.sql" \
    "$output_dir/server-catalog.csv"
  capture_admin_csv \
    "$script_dir/mapping-catalog.sql" \
    "$output_dir/mapping-catalog.csv"
  capture_admin_csv \
    "$script_dir/relation-catalog.sql" \
    "$output_dir/relation-catalog.csv"
  capture_admin_csv \
    "$script_dir/index-catalog.sql" \
    "$output_dir/index-catalog.csv"
  capture_admin_csv \
    "$script_dir/security-catalog.sql" \
    "$output_dir/security-catalog.csv"
  capture_admin_csv \
    "$script_dir/size-catalog.sql" \
    "$output_dir/size-catalog.csv"

  capture_admin_text \
    "$script_dir/local-parallel-plan.sql" \
    "$output_dir/local-parallel-plan.txt"
  capture_admin_text \
    "$script_dir/spill-low-plan.sql" \
    "$output_dir/spill-low-plan.txt"
  capture_admin_text \
    "$script_dir/spill-high-plan.sql" \
    "$output_dir/spill-high-plan.txt"
  capture_admin_text \
    "$script_dir/selective-index-plan.sql" \
    "$output_dir/selective-index-plan.txt"
  capture_admin_text \
    "$script_dir/raw-aggregate-plan.sql" \
    "$output_dir/raw-aggregate-plan.txt"
  capture_admin_text \
    "$script_dir/summary-aggregate-plan.sql" \
    "$output_dir/summary-aggregate-plan.txt"
  capture_admin_text \
    "$script_dir/tenant-pruned-plan.sql" \
    "$output_dir/tenant-pruned-plan.txt"
  capture_admin_text \
    "$script_dir/distributed-naive-plan.sql" \
    "$output_dir/distributed-naive-plan.txt"
  capture_admin_text \
    "$script_dir/distributed-two-stage-plan.sql" \
    "$output_dir/distributed-two-stage-plan.txt"
  capture_admin_text \
    "$script_dir/collocated-parent-plan.sql" \
    "$output_dir/collocated-parent-plan.txt"

  capture_app_csv \
    "$script_dir/app-query.sql" \
    "$output_dir/app-query.csv"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/app-write.sql" \
    "app-write" \
    "42501" \
    "$output_dir"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/shard-failure.sql" \
    "shard-failure" \
    "08001" \
    "$output_dir" \
    --set="fdw_host=${fdw_host}" \
    --set="fdw_port=${fdw_port}"

  if ! grep -Fq \
       "healthy_shard_tenant_2=30000" \
       "$output_dir/shard-failure.stdout"; then
    printf 'shard failure probe did not preserve the healthy shard read\n' >&2
    exit 1
  fi

  capture_admin_csv \
    "$script_dir/server-catalog.sql" \
    "$output_dir/server-catalog-after-failure.csv"
  cmp "$output_dir/server-catalog.csv" \
      "$output_dir/server-catalog-after-failure.csv"

  capture_admin_csv \
    "$script_dir/final-state.sql" \
    "$output_dir/final-state.csv"
  verify_all_databases "$output_dir"
  write_manifest "$output_dir"

  python3 "$script_dir/review.py" \
    "$output_dir" \
    --baseline "$script_dir/baseline-v1.5-proposal.json" \
    --fixture-manifest "$script_dir/fixture-manifest.json" \
    --source-dir "$script_dir" \
    >"$output_dir/review.txt"
}

run_coordinator_reset() {
  local token="$1"
  local target="$2"
  local output_file="$3"
  run_admin_sql \
    "$script_dir/reset.sql" \
    --set="reset_token=${token}" \
    --set="reset_target=${target}" \
    >"$output_file" \
    2>"${output_file%.*}.stderr"
}

run_remote_reset() {
  local database_name="$1"
  local remainder="$2"
  local marker="$3"
  local token="$4"
  local target="$5"
  local output_file="$6"
  run_remote_sql \
    "$database_name" \
    "$remainder" \
    "$marker" \
    "$script_dir/remote-reset.sql" \
    --set="reset_token=${token}" \
    --set="reset_target=${target}" \
    >"$output_file" \
    2>"${output_file%.*}.stderr"
}

run_reset_guard() {
  local name="$1"
  local token="$2"
  local target="$3"
  local sqlstate="$4"
  local output_dir="$5"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/reset.sql" \
    "$name" \
    "$sqlstate" \
    "$output_dir" \
    --set="fdw_host=${fdw_host}" \
    --set="fdw_port=${fdw_port}" \
    --set="reset_token=${token}" \
    --set="reset_target=${target}"
}

prove_active_guard() {
  local output_dir="$1"
  local attempt

  psql -X -w \
    --dbname="service=${pg_service} dbname=pg36_shop application_name=pg36-ch17-active-reset" \
    --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_catalog.pg_sleep(30);" \
    >"$output_dir/active-worker.stdout" \
    2>"$output_dir/active-worker.stderr" &
  reset_worker_pid=$!

  for attempt in $(seq 1 100); do
    reset_backend_pid="$(
      psql -X -w -qAt \
        --dbname="$admin_connection" \
        --set=ON_ERROR_STOP=1 \
        --command="
          SELECT pid
          FROM pg_catalog.pg_stat_activity
          WHERE datname = current_database()
            AND application_name =
                'pg36-ch17-active-reset'
          ORDER BY pid
          LIMIT 1;
        "
    )"
    if [[ -n "$reset_backend_pid" ]]; then
      break
    fi
    sleep 0.1
  done

  if [[ -z "$reset_backend_pid" ]]; then
    printf 'could not observe the active reset worker\n' >&2
    exit 1
  fi

  run_reset_guard \
    "reset-active-worker" \
    "RESET_CH17_ANALYTICS_FDW_LAB" \
    "pg36_shop/shop_ch17+shop_ch17_ext+fdw" \
    "P3663" \
    "$output_dir"

  psql -X -w -qAt \
    --dbname="$admin_connection" \
    --set=ON_ERROR_STOP=1 \
    --command="
      SELECT pg_catalog.pg_cancel_backend(pid)
      FROM pg_catalog.pg_stat_activity
      WHERE pid = ${reset_backend_pid}
        AND datname = current_database()
        AND application_name =
            'pg36-ch17-active-reset';
    " >/dev/null
  wait "$reset_worker_pid" || true
  reset_worker_pid=""
  reset_backend_pid=""
}

run_exact_reset() {
  local output_dir="$1"
  local coordinator_token="$2"
  local coordinator_target="$3"
  mkdir -p "$output_dir"

  # The three databases cannot share one local atomic DDL transaction.
  # Verify every target first, then perform exact per-database transactions.
  verify_all_databases "$output_dir/preflight"

  run_coordinator_reset \
    "$coordinator_token" \
    "$coordinator_target" \
    "$output_dir/coordinator-reset.txt"
  run_remote_reset \
    "pg36_shard_a" \
    "0" \
    "pg36 ch17 shard 0 lab; safe to rebuild" \
    "$coordinator_token" \
    "pg36_shard_a/shop_ch17_shard" \
    "$output_dir/remote-a-reset.txt"
  run_remote_reset \
    "pg36_shard_b" \
    "1" \
    "pg36 ch17 shard 1 lab; safe to rebuild" \
    "$coordinator_token" \
    "pg36_shard_b/shop_ch17_shard" \
    "$output_dir/remote-b-reset.txt"
}

discover_fdw_endpoint

case "$action" in
  setup)
    bootstrap_and_setup "$evidence_dir"
    printf 'status=setup-ok\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  evaluate)
    collect_cycle "$evidence_dir"
    printf 'status=ok\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    verify_all_databases "$evidence_dir"
    printf 'status=verify-ok\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    python3 "$script_dir/review.py" \
      "$evidence_dir" \
      --baseline "$script_dir/baseline-v1.5-proposal.json" \
      --fixture-manifest "$script_dir/fixture-manifest.json" \
      --source-dir "$script_dir"
    ;;
  reset)
    run_exact_reset \
      "$evidence_dir" \
      "${PG36_RESET_TOKEN:-}" \
      "${PG36_RESET_TARGET:-}"
    printf 'status=reset-ok\n'
    printf 'database_shells=retained\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  all)
    collect_cycle "$evidence_dir/cycle-1"
    run_reset_guard \
      "reset-wrong-token" \
      "WRONG" \
      "pg36_shop/shop_ch17+shop_ch17_ext+fdw" \
      "P3660" \
      "$evidence_dir"
    run_reset_guard \
      "reset-wrong-target" \
      "RESET_CH17_ANALYTICS_FDW_LAB" \
      "pg36_shop/wrong" \
      "P3661" \
      "$evidence_dir"
    prove_active_guard "$evidence_dir"
    run_exact_reset \
      "$evidence_dir/reset-exact" \
      "RESET_CH17_ANALYTICS_FDW_LAB" \
      "pg36_shop/shop_ch17+shop_ch17_ext+fdw"
    collect_cycle "$evidence_dir/cycle-2"
    printf 'status=ok\n'
    printf 'fixture=frozen-byte-identical-four-paths\n'
    printf 'single_node=parallel+index+summary+spill\n'
    printf 'distributed=tenant-pruning+fdw+two-stage\n'
    printf 'counterexamples=hash-is-not-modulo+join-not-pushed\n'
    printf 'failure=healthy-shard-read+global-08001\n'
    printf 'guards=P3660+P3661+P3663\n'
    printf 'postgres_fdw=1.2\n'
    printf 'pigsty_l1=not-run\n'
    printf 'evidence=%s\n' "$evidence_dir"
    printf 'release_candidate_checksum=%s\n' \
      "$(canonical_json_checksum \
          "$script_dir/baseline-v1.5-proposal.json")"
    ;;
esac
