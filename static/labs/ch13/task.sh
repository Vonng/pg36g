#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch13/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} application_name=pg36-ch13-${action}"
app_connection="service=${pg_service} user=pg36_app application_name=pg36-ch13-app"
reset_worker_pid=""
reset_backend_pid=""

usage() {
  printf '%s\n' \
    "usage: $0 {setup|catalog|behavior|verify|review|reset|all}" \
    "behavior rebuilds the exact fixture before running cases" \
    "all proves failure contracts, reset refusals, exact reset, and rebuild" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "database actions require PGSERVICEFILE and the ch04-v1 model"
}

case "$action" in
  setup|catalog|behavior|verify|review|reset|all)
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
          AND application_name = 'pg36-ch13-active-reset';
      " >/dev/null 2>&1 || true
  fi
  if [[ -n "$reset_worker_pid" ]] \
     && kill -0 "$reset_worker_pid" 2>/dev/null; then
    kill -TERM "$reset_worker_pid" 2>/dev/null || true
    wait "$reset_worker_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

run_admin_sql() {
  local sql_file="$1"
  shift
  psql -X -w \
    --dbname="$admin_connection" \
    --set=ON_ERROR_STOP=1 \
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

  set +e
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --set=VERBOSITY=verbose \
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
  local candidate_checksum
  candidate_checksum="$(
    python3 - "$script_dir/baseline-v1.1-proposal.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

document = json.loads(
    Path(sys.argv[1]).read_text(encoding="utf-8")
)
encoded = json.dumps(
    document,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
print(hashlib.sha256(encoded).hexdigest())
PY
  )"

  {
    printf 'captured_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'service=%s\n' "$pg_service"
    printf 'validation_path=direct-postgresql\n'
    printf 'application_role=pg36_app\n'
    printf 'model_version=ch04-v1\n'
    printf 'python=%s\n' "$(python3 --version 2>&1)"
    printf 'psql_client=%s\n' "$(psql --version)"
    printf 'release_candidate_checksum=%s\n' \
      "$candidate_checksum"
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
      "
    find "$script_dir" -maxdepth 1 -type f -print0 \
      | sort -z \
      | xargs -0 sha256sum
  } >"$output_dir/manifest.txt"
}

run_preflight() {
  local output_dir="$1"
  run_admin_sql "$script_dir/../ch05/verify.sql" \
    >"$output_dir/preflight.txt" \
    2>"$output_dir/preflight.stderr"
}

run_setup() {
  local output_dir="$1"
  run_admin_sql "$script_dir/setup.sql" \
    >"$output_dir/setup.txt" \
    2>"$output_dir/setup.stderr"
}

run_catalog() {
  local output_dir="$1"
  capture_admin_csv \
    "$script_dir/routine-catalog.sql" \
    "$output_dir/routine-catalog.csv"
  capture_admin_csv \
    "$script_dir/trigger-catalog.sql" \
    "$output_dir/trigger-catalog.csv"
  capture_admin_csv \
    "$script_dir/security-catalog.sql" \
    "$output_dir/security-catalog.csv"
  capture_admin_csv \
    "$script_dir/transition-matrix.sql" \
    "$output_dir/transition-matrix.csv"
}

run_behavior() {
  local output_dir="$1"

  capture_app_csv \
    "$script_dir/api-happy.sql" \
    "$output_dir/api-happy.csv"

  run_expected_failure \
    "$app_connection" \
    "$script_dir/invalid-transition.sql" \
    "invalid-transition" \
    "P3613" \
    "$output_dir"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/paid-without-payment.sql" \
    "paid-without-payment" \
    "P3614" \
    "$output_dir"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/version-conflict.sql" \
    "version-conflict" \
    "P3616" \
    "$output_dir"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/payment-mismatch.sql" \
    "payment-mismatch" \
    "P3618" \
    "$output_dir"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/delete-payment.sql" \
    "delete-payment" \
    "P3614" \
    "$output_dir"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/direct-write.sql" \
    "direct-write" \
    "42501" \
    "$output_dir"

  capture_admin_csv \
    "$script_dir/exception-probe.sql" \
    "$output_dir/exception-probe.csv"
  capture_admin_csv \
    "$script_dir/function-stats.sql" \
    "$output_dir/function-stats.csv"
  capture_admin_csv \
    "$script_dir/bulk-update.sql" \
    "$output_dir/bulk-update.csv"

  run_expected_failure \
    "$admin_connection" \
    "$script_dir/procedure-in-transaction.sql" \
    "procedure-in-transaction" \
    "2D000" \
    "$output_dir"

  capture_admin_csv \
    "$script_dir/procedure-run.sql" \
    "$output_dir/procedure-run.csv"
  capture_admin_csv \
    "$script_dir/procedure-rerun.sql" \
    "$output_dir/procedure-rerun.csv"
}

run_verify() {
  local output_dir="$1"
  capture_admin_csv \
    "$script_dir/final-state.sql" \
    "$output_dir/final-state.csv"
  run_admin_sql "$script_dir/verify.sql" \
    >"$output_dir/verify.txt" \
    2>"$output_dir/verify.stderr"
  run_admin_sql "$script_dir/../ch05/verify.sql" \
    >"$output_dir/model-verify-after.txt" \
    2>"$output_dir/model-verify-after.stderr"
}

run_review() {
  local output_dir="$1"
  PYTHONPYCACHEPREFIX="$output_dir/.pycache" \
    "$script_dir/review.py" \
      --evidence-dir "$output_dir" \
      --repo-root "$repo_root" \
      >"$output_dir/review.txt" \
      2>"$output_dir/review.stderr"
  cat "$output_dir/review.txt"
}

run_reset_file() {
  local output_dir="$1"
  local reset_token="$2"
  local reset_target="$3"
  run_admin_sql "$script_dir/reset.sql" \
    --set=reset_token="$reset_token" \
    --set=reset_target="$reset_target" \
    >"$output_dir/reset.txt" \
    2>"$output_dir/reset.stderr"
}

run_reset_failure() {
  local output_dir="$1"
  local name="$2"
  local sqlstate="$3"
  local reset_token="$4"
  local reset_target="$5"

  set +e
  run_admin_sql "$script_dir/reset.sql" \
    --set=VERBOSITY=verbose \
    --set=reset_token="$reset_token" \
    --set=reset_target="$reset_target" \
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

wait_for_reset_worker() {
  local attempt
  local observed_pid
  for attempt in $(seq 1 100); do
    if ! kill -0 "$reset_worker_pid" 2>/dev/null; then
      printf 'active-reset worker exited before observation\n' >&2
      exit 1
    fi
    observed_pid="$(
      psql -X -w -qAt \
        --dbname="$admin_connection" \
        --set=ON_ERROR_STOP=1 \
        --command="
          SELECT pid
          FROM pg_catalog.pg_stat_activity
          WHERE datname = current_database()
            AND application_name =
                'pg36-ch13-active-reset'
            AND query LIKE
                'SELECT pg_catalog.pg_sleep(30)%';
        "
    )"
    if [[ "$observed_pid" =~ ^[0-9]+$ ]]; then
      reset_backend_pid="$observed_pid"
      return
    fi
    sleep 0.05
  done
  printf 'active-reset worker was not observable\n' >&2
  exit 1
}

run_reset_guards() {
  local output_dir="$1"

  run_reset_failure \
    "$output_dir" \
    "reset-wrong-token" \
    "P3620" \
    "WRONG" \
    "pg36_shop/shop_ch13"
  run_reset_failure \
    "$output_dir" \
    "reset-wrong-target" \
    "P3621" \
    "RESET_CH13_ROUTINE_GUARD" \
    "pg36_shop/wrong"

  psql -X -w \
    --dbname="service=${pg_service} application_name=pg36-ch13-active-reset" \
    --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_catalog.pg_sleep(30);" \
    >"$output_dir/reset-active-worker.stdout" \
    2>"$output_dir/reset-active-worker.stderr" &
  reset_worker_pid=$!
  wait_for_reset_worker

  run_reset_failure \
    "$output_dir" \
    "reset-active-worker" \
    "P3623" \
    "RESET_CH13_ROUTINE_GUARD" \
    "pg36_shop/shop_ch13"

  cancel_result="$(
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT pg_catalog.pg_cancel_backend(pid)
        FROM pg_catalog.pg_stat_activity
        WHERE pid = ${reset_backend_pid}
          AND datname = current_database()
          AND application_name = 'pg36-ch13-active-reset';
      "
  )"
  if [[ "$cancel_result" != "t" ]]; then
    printf 'active-reset backend cancellation failed\n' >&2
    exit 1
  fi
  set +e
  wait "$reset_worker_pid"
  set -e
  reset_worker_pid=""
  reset_backend_pid=""
}

run_cycle() {
  local output_dir="$1"
  run_preflight "$output_dir"
  run_setup "$output_dir"
  run_catalog "$output_dir"
  run_behavior "$output_dir"
  run_verify "$output_dir"
  run_review "$output_dir"
}

write_manifest "$evidence_dir"

case "$action" in
  setup)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    ;;
  catalog)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    run_catalog "$evidence_dir"
    ;;
  behavior)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    run_catalog "$evidence_dir"
    run_behavior "$evidence_dir"
    run_verify "$evidence_dir"
    ;;
  verify)
    run_verify "$evidence_dir"
    ;;
  review)
    run_review "$evidence_dir"
    ;;
  reset)
    run_reset_file \
      "$evidence_dir" \
      "${PG36_RESET_TOKEN:-}" \
      "${PG36_RESET_TARGET:-}"
    ;;
  all)
    run_cycle "$evidence_dir"
    run_reset_guards "$evidence_dir"
    run_reset_file \
      "$evidence_dir" \
      "RESET_CH13_ROUTINE_GUARD" \
      "pg36_shop/shop_ch13"

    rebuild_dir="$evidence_dir/rebuild"
    mkdir -p "$rebuild_dir"
    write_manifest "$rebuild_dir"
    run_cycle "$rebuild_dir"
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
