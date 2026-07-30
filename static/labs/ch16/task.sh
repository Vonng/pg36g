#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch16/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} application_name=pg36-ch16-${action}"
app_connection="service=${pg_service} user=pg36_app application_name=pg36-ch16-app"
reset_worker_pid=""
reset_backend_pid=""

usage() {
  printf '%s\n' \
    "usage: $0 {setup|evaluate|verify|review|reset|all}" \
    "all proves frozen exports, time/space semantics, plans, privileges, reset guards, and rebuild" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
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
              'pg36-ch16-active-reset';
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

capture_admin_text() {
  local sql_file="$1"
  local output_file="$2"
  run_admin_sql "$sql_file" --quiet \
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
      "$script_dir/baseline-v1.4-proposal.json"
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
    printf 'validation_path=direct-postgresql\n'
    printf 'pigsty_reference=4.4\n'
    printf 'pigsty_l1=not-run\n'
    printf 'model_version=ch04-v1\n'
    printf 'partition_timezone=UTC\n'
    printf 'coordinate_contract=EPSG:4326-synthetic\n'
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
        SELECT 'extension_versions=' ||
               pg_catalog.string_agg(
                   extname || ':' || extversion,
                   ',' ORDER BY extname
               )
        FROM pg_catalog.pg_extension
        WHERE extname IN ('btree_gist', 'postgis');
        SELECT 'preserved_ch14_extensions=' ||
               pg_catalog.string_agg(
                   extname || ':' || extversion,
                   ',' ORDER BY extname
               )
        FROM pg_catalog.pg_extension
        WHERE extname IN ('pg_trgm', 'vector');
      "
    while IFS= read -r source_file; do
      hash_file "$source_file"
    done < <(
      find "$script_dir" -maxdepth 1 -type f -print \
        | sort
    )
  } >"$output_dir/manifest.txt"
}

collect_cycle() {
  local output_dir="$1"
  mkdir -p "$output_dir"

  run_admin_sql "$script_dir/setup.sql" \
    >"$output_dir/setup.txt" \
    2>"$output_dir/setup.stderr"

  capture_admin_csv \
    "$script_dir/attempts-export.sql" \
    "$output_dir/attempts.csv"
  capture_admin_csv \
    "$script_dir/geofences-export.sql" \
    "$output_dir/geofences.csv"
  capture_admin_csv \
    "$script_dir/hubs-export.sql" \
    "$output_dir/hubs.csv"

  cmp "$script_dir/frozen-attempts.csv" \
      "$output_dir/attempts.csv"
  cmp "$script_dir/frozen-geofences.csv" \
      "$output_dir/geofences.csv"
  cmp "$script_dir/frozen-hubs.csv" \
      "$output_dir/hubs.csv"

  capture_admin_csv \
    "$script_dir/temporal-analysis.sql" \
    "$output_dir/temporal-analysis.csv"
  capture_admin_csv \
    "$script_dir/partition-catalog.sql" \
    "$output_dir/partition-catalog.csv"
  capture_admin_csv \
    "$script_dir/time-buckets.sql" \
    "$output_dir/time-buckets.csv"
  capture_admin_csv \
    "$script_dir/zone-membership.sql" \
    "$output_dir/zone-membership.csv"
  capture_admin_csv \
    "$script_dir/boundary-semantics.sql" \
    "$output_dir/boundary-semantics.csv"
  capture_admin_csv \
    "$script_dir/distance-semantics.sql" \
    "$output_dir/distance-semantics.csv"
  capture_admin_csv \
    "$script_dir/extension-catalog.sql" \
    "$output_dir/extension-catalog.csv"
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
    "$script_dir/time-pruned-plan.sql" \
    "$output_dir/time-pruned-plan.txt"
  capture_admin_text \
    "$script_dir/time-wrapped-plan.sql" \
    "$output_dir/time-wrapped-plan.txt"
  capture_admin_text \
    "$script_dir/spatial-gist-plan.sql" \
    "$output_dir/spatial-gist-plan.txt"
  capture_admin_text \
    "$script_dir/spatial-spgist-plan.sql" \
    "$output_dir/spatial-spgist-plan.txt"
  capture_admin_text \
    "$script_dir/joint-plan.sql" \
    "$output_dir/joint-plan.txt"

  capture_app_csv \
    "$script_dir/app-query.sql" \
    "$output_dir/app-query.csv"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/srid-mismatch.sql" \
    "srid-mismatch" \
    "XX000" \
    "$output_dir"
  run_expected_failure \
    "$admin_connection" \
    "$script_dir/overlap-geofence.sql" \
    "overlap-geofence" \
    "23P01" \
    "$output_dir"
  run_expected_failure \
    "$app_connection" \
    "$script_dir/app-write.sql" \
    "app-write" \
    "42501" \
    "$output_dir"

  capture_admin_csv \
    "$script_dir/final-state.sql" \
    "$output_dir/final-state.csv"
  capture_admin_text \
    "$script_dir/verify.sql" \
    "$output_dir/verify.txt"
  write_manifest "$output_dir"

  python3 "$script_dir/review.py" \
    "$output_dir" \
    --baseline "$script_dir/baseline-v1.4-proposal.json" \
    --fixture-manifest "$script_dir/fixture-manifest.json" \
    --source-dir "$script_dir" \
    >"$output_dir/review.txt"
}

run_reset() {
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
    --set="reset_token=${token}" \
    --set="reset_target=${target}"
}

prove_active_guard() {
  local output_dir="$1"
  local attempt

  psql -X -w \
    --dbname="service=${pg_service} application_name=pg36-ch16-active-reset" \
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
                'pg36-ch16-active-reset'
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
    "RESET_CH16_SPATIOTEMPORAL_LAB" \
    "pg36_shop/shop_ch16+shop_ch16_ext" \
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
            'pg36-ch16-active-reset';
    " >/dev/null
  wait "$reset_worker_pid" || true
  reset_worker_pid=""
  reset_backend_pid=""
}

case "$action" in
  setup)
    run_admin_sql "$script_dir/setup.sql"
    ;;
  evaluate)
    collect_cycle "$evidence_dir"
    printf 'status=ok\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    run_admin_sql "$script_dir/verify.sql"
    ;;
  review)
    python3 "$script_dir/review.py" \
      "$evidence_dir" \
      --baseline "$script_dir/baseline-v1.4-proposal.json" \
      --fixture-manifest "$script_dir/fixture-manifest.json" \
      --source-dir "$script_dir"
    ;;
  reset)
    run_reset \
      "${PG36_RESET_TOKEN:-}" \
      "${PG36_RESET_TARGET:-}" \
      "$evidence_dir/reset.txt"
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  all)
    collect_cycle "$evidence_dir/cycle-1"
    run_reset_guard \
      "reset-wrong-token" \
      "WRONG" \
      "pg36_shop/shop_ch16+shop_ch16_ext" \
      "P3660" \
      "$evidence_dir"
    run_reset_guard \
      "reset-wrong-target" \
      "RESET_CH16_SPATIOTEMPORAL_LAB" \
      "pg36_shop/wrong" \
      "P3661" \
      "$evidence_dir"
    prove_active_guard "$evidence_dir"
    run_reset \
      "RESET_CH16_SPATIOTEMPORAL_LAB" \
      "pg36_shop/shop_ch16+shop_ch16_ext" \
      "$evidence_dir/reset-exact.txt"
    collect_cycle "$evidence_dir/cycle-2"
    printf 'status=ok\n'
    printf 'fixture=frozen-byte-identical\n'
    printf 'time=event+ingest+validity+dst\n'
    printf 'space=geometry+geography+srid+boundary\n'
    printf 'plans=pruning+gist+spgist+joint\n'
    printf 'guards=P3660+P3661+P3663\n'
    printf 'extensions=btree_gist:1.8+postgis:3.6.4\n'
    printf 'pigsty_l1=not-run\n'
    printf 'evidence=%s\n' "$evidence_dir"
    printf 'release_candidate_checksum=%s\n' \
      "$(canonical_json_checksum \
          "$script_dir/baseline-v1.4-proposal.json")"
    ;;
esac
