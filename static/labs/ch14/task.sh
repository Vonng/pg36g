#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch14/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} application_name=pg36-ch14-${action}"
app_connection="service=${pg_service} user=pg36_app application_name=pg36-ch14-app"
reset_worker_pid=""
reset_backend_pid=""

usage() {
  printf '%s\n' \
    "usage: $0 {setup|inventory|upgrade|behavior|dump|verify|review|reset|all}" \
    "all proves privilege failures, object upgrade, dump semantics, reset guards, and rebuild" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "database actions require PGSERVICEFILE and the ch04-v1 model"
}

case "$action" in
  setup|inventory|upgrade|behavior|dump|verify|review|reset|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in \
  bash grep pg_config pg_dump psql python3 sort
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
          AND application_name = 'pg36-ch14-active-reset';
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
    python3 - "$script_dir/baseline-v1.2-proposal.json" <<'PY'
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
    printf 'pigsty_reference=4.4\n'
    printf 'pigsty_l1=not-run\n'
    printf 'application_role=pg36_app\n'
    printf 'model_version=ch04-v1\n'
    printf 'python=%s\n' "$(python3 --version 2>&1)"
    printf 'psql_client=%s\n' "$(psql --version)"
    printf 'pg_dump_client=%s\n' "$(pg_dump --version)"
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
    while IFS= read -r source_file; do
      hash_file "$source_file"
    done < <(
      find "$script_dir" -maxdepth 1 -type f -print \
        | sort
    )
  } >"$output_dir/manifest.txt"
}

write_package_manifest() {
  local output_dir="$1"
  local sharedir
  local pkglibdir
  local server_major
  local config_major
  local support_file
  local library_name
  local library_file
  local library_suffix

  sharedir="$(pg_config --sharedir)"
  pkglibdir="$(pg_config --pkglibdir)"
  server_major="$(
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT current_setting(
                   'server_version_num'
               )::integer / 10000;
      "
  )"
  config_major="$(
    pg_config --version \
      | sed -E 's/.* ([0-9]+).*/\1/'
  )"

  if [[ "$server_major" != "$config_major" ]]; then
    printf 'pg_config major %s differs from server major %s\n' \
      "$config_major" "$server_major" >&2
    exit 1
  fi

  {
    printf 'validation_path=direct-postgresql\n'
    printf 'pigsty_l1=not-run\n'
    printf 'pg_config=%s\n' "$(command -v pg_config)"
    printf 'pg_config_version=%s\n' "$(pg_config --version)"
    printf 'server_major=%s\n' "$server_major"
    printf 'sharedir=%s\n' "$sharedir"
    printf 'pkglibdir=%s\n' "$pkglibdir"

    for support_file in \
      "$sharedir/extension/pg_trgm.control" \
      "$sharedir/extension/pg_trgm--1.3.sql" \
      "$sharedir/extension/pg_trgm--1.3--1.4.sql" \
      "$sharedir/extension/pg_trgm--1.4--1.5.sql" \
      "$sharedir/extension/pg_trgm--1.5--1.6.sql" \
      "$sharedir/extension/vector.control" \
      "$sharedir/extension/vector--0.8.4.sql"
    do
      if [[ ! -f "$support_file" ]]; then
        printf 'missing extension support file: %s\n' \
          "$support_file" >&2
        exit 1
      fi
      hash_file "$support_file"
    done

    for library_name in pg_trgm vector; do
      library_file=""
      for library_suffix in so dylib; do
        if [[ -f "$pkglibdir/${library_name}.${library_suffix}" ]]; then
          library_file="$pkglibdir/${library_name}.${library_suffix}"
          break
        fi
      done
      if [[ -z "$library_file" ]]; then
        printf 'missing shared library for %s in %s\n' \
          "$library_name" "$pkglibdir" >&2
        exit 1
      fi
      hash_file "$library_file"
    done
  } >"$output_dir/package-manifest.txt"
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
    >"$output_dir/setup-base.txt" \
    2>"$output_dir/setup-base.stderr"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/owner-create-vector.sql" \
    "owner-create-vector" \
    "42501" \
    "$output_dir"
  run_admin_sql "$script_dir/install-vector.sql" \
    >"$output_dir/install-vector.txt" \
    2>"$output_dir/install-vector.stderr"
}

run_before() {
  local output_dir="$1"

  capture_admin_csv \
    "$script_dir/available-candidates.sql" \
    "$output_dir/available-candidates-before.csv"
  capture_admin_csv \
    "$script_dir/available-versions.sql" \
    "$output_dir/available-versions-before.csv"
  capture_admin_csv \
    "$script_dir/extension-inventory.sql" \
    "$output_dir/extension-inventory-before.csv"
  capture_admin_csv \
    "$script_dir/member-catalog.sql" \
    "$output_dir/member-catalog-before.csv"
  capture_admin_csv \
    "$script_dir/update-paths.sql" \
    "$output_dir/update-paths.csv"
  capture_admin_csv \
    "$script_dir/index-catalog.sql" \
    "$output_dir/index-catalog-before.csv"
  capture_admin_csv \
    "$script_dir/security-catalog.sql" \
    "$output_dir/security-catalog-before.csv"
  capture_admin_csv \
    "$script_dir/behavior.sql" \
    "$output_dir/behavior-before.csv"

  run_admin_sql "$script_dir/trigram-plan.sql" \
    >"$output_dir/trigram-plan-before.txt" \
    2>"$output_dir/trigram-plan-before.stderr"
  run_admin_sql "$script_dir/vector-plan.sql" \
    >"$output_dir/vector-plan-before.txt" \
    2>"$output_dir/vector-plan-before.stderr"
  capture_app_csv \
    "$script_dir/app-query.sql" \
    "$output_dir/app-query.csv"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/app-alter-extension.sql" \
    "app-alter-extension" \
    "42501" \
    "$output_dir"
}

run_upgrade() {
  local output_dir="$1"
  run_admin_sql "$script_dir/upgrade.sql" \
    >"$output_dir/upgrade.txt" \
    2>"$output_dir/upgrade.stderr"
}

run_after() {
  local output_dir="$1"

  capture_admin_csv \
    "$script_dir/available-candidates.sql" \
    "$output_dir/available-candidates-after.csv"
  capture_admin_csv \
    "$script_dir/available-versions.sql" \
    "$output_dir/available-versions-after.csv"
  capture_admin_csv \
    "$script_dir/extension-inventory.sql" \
    "$output_dir/extension-inventory-after.csv"
  capture_admin_csv \
    "$script_dir/member-catalog.sql" \
    "$output_dir/member-catalog-after.csv"
  capture_admin_csv \
    "$script_dir/index-catalog.sql" \
    "$output_dir/index-catalog-after.csv"
  capture_admin_csv \
    "$script_dir/security-catalog.sql" \
    "$output_dir/security-catalog-after.csv"
  capture_admin_csv \
    "$script_dir/behavior.sql" \
    "$output_dir/behavior-after.csv"

  run_admin_sql "$script_dir/trigram-plan.sql" \
    >"$output_dir/trigram-plan-after.txt" \
    2>"$output_dir/trigram-plan-after.stderr"
  run_admin_sql "$script_dir/vector-plan.sql" \
    >"$output_dir/vector-plan-after.txt" \
    2>"$output_dir/vector-plan-after.stderr"
}

run_dump() {
  local output_dir="$1"

  PGSERVICE="$pg_service" pg_dump \
    --dbname="service=${pg_service}" \
    --schema-only \
    --no-owner \
    --no-privileges \
    >"$output_dir/database-schema.sql" \
    2>"$output_dir/database-schema.stderr"

  PGSERVICE="$pg_service" pg_dump \
    --dbname="service=${pg_service}" \
    --schema-only \
    --schema=shop_ch14 \
    --no-owner \
    --no-privileges \
    >"$output_dir/selected-schema.sql" \
    2>"$output_dir/selected-schema.stderr"

  run_admin_sql "$script_dir/portable-export.sql" \
    >"$output_dir/portable-export.csv" \
    2>"$output_dir/portable-export.stderr"
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
                'pg36-ch14-active-reset'
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
  local cancel_result

  run_reset_failure \
    "$output_dir" \
    "reset-wrong-token" \
    "P3650" \
    "WRONG" \
    "pg36_shop/shop_ch14/pg_trgm+vector"
  run_reset_failure \
    "$output_dir" \
    "reset-wrong-target" \
    "P3651" \
    "RESET_CH14_EXTENSION_LAB" \
    "pg36_shop/wrong"

  psql -X -w \
    --dbname="service=${pg_service} application_name=pg36-ch14-active-reset" \
    --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_catalog.pg_sleep(30);" \
    >"$output_dir/reset-active-worker.stdout" \
    2>"$output_dir/reset-active-worker.stderr" &
  reset_worker_pid=$!
  wait_for_reset_worker

  run_reset_failure \
    "$output_dir" \
    "reset-active-worker" \
    "P3653" \
    "RESET_CH14_EXTENSION_LAB" \
    "pg36_shop/shop_ch14/pg_trgm+vector"

  cancel_result="$(
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT pg_catalog.pg_cancel_backend(pid)
        FROM pg_catalog.pg_stat_activity
        WHERE pid = ${reset_backend_pid}
          AND datname = current_database()
          AND application_name = 'pg36-ch14-active-reset';
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
  run_before "$output_dir"
  run_upgrade "$output_dir"
  run_after "$output_dir"
  run_dump "$output_dir"
  run_verify "$output_dir"
  run_review "$output_dir"
}

write_manifest "$evidence_dir"
write_package_manifest "$evidence_dir"

case "$action" in
  setup)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    ;;
  inventory)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    run_before "$evidence_dir"
    ;;
  upgrade|behavior)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    run_before "$evidence_dir"
    run_upgrade "$evidence_dir"
    run_after "$evidence_dir"
    ;;
  dump)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    run_before "$evidence_dir"
    run_upgrade "$evidence_dir"
    run_after "$evidence_dir"
    run_dump "$evidence_dir"
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
      "RESET_CH14_EXTENSION_LAB" \
      "pg36_shop/shop_ch14/pg_trgm+vector"

    rebuild_dir="$evidence_dir/rebuild"
    mkdir -p "$rebuild_dir"
    write_manifest "$rebuild_dir"
    write_package_manifest "$rebuild_dir"
    run_cycle "$rebuild_dir"
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
