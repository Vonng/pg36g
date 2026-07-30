#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch12/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} application_name=pg36-ch12-${action}"
default_app_database_url="service=${pg_service} user=pg36_app"
app_database_url="${PG36_APP_DATABASE_URL:-$default_app_database_url}"
if [[ -n "${PG36_APP_DATABASE_URL:-}" ]]; then
  validation_path="operator-supplied-application-endpoint"
  pooler_validation="behavior-run-config-identity-required"
  app_endpoint_source="PG36_APP_DATABASE_URL"
else
  validation_path="direct-postgresql"
  pooler_validation="not-run"
  app_endpoint_source="derived-from-admin-service"
fi
service_pid=""
service_address=""
service_url=""

usage() {
  printf '%s\n' \
    "usage: $0 {setup|build|run|verify|review|reset|all}" \
    "run rebuilds the exact fixture and executes one service suite" \
    "all additionally proves reset guards, resets, rebuilds, and reruns" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "PG36_APP_DATABASE_URL optionally selects a distinct app endpoint" \
    "database actions require PGSERVICEFILE and the ch04-v1 model"
}

case "$action" in
  setup|build|run|verify|review|reset|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash curl go grep psql python3 sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

if [[ "$action" != "build" && ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

mkdir -p "$evidence_dir"

run_sql_file() {
  local sql_file="$1"
  shift
  psql -X -w \
    --dbname="$admin_connection" \
    --set=ON_ERROR_STOP=1 \
    "$@" \
    --file="$sql_file"
}

run_preflight() {
  local output_dir="$1"
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$output_dir/preflight.txt" \
    2>"$output_dir/preflight.stderr"
}

run_setup() {
  local output_dir="$1"
  run_sql_file "$script_dir/setup.sql" \
    >"$output_dir/setup.txt" \
    2>"$output_dir/setup.stderr"
}

build_service() {
  (
    cd "$script_dir/service"
    GOWORK=off go test ./...
    GOWORK=off go vet ./...
    GOWORK=off go build \
      -mod=readonly \
      -trimpath \
      -ldflags=-buildid= \
      -o "$evidence_dir/pg36-ch12-service" \
      .
  ) >"$evidence_dir/build.txt" \
    2>"$evidence_dir/build.stderr"
}

choose_address() {
  if [[ -n "${PG36_HTTP_ADDR:-}" ]]; then
    service_address="$PG36_HTTP_ADDR"
  else
    service_address="$(
      python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind(("127.0.0.1", 0))
    print(f"127.0.0.1:{listener.getsockname()[1]}")
PY
    )"
  fi
  service_url="http://${service_address}"
}

start_service() {
  local output_dir="$1"
  choose_address
  PGSERVICEFILE="$PGSERVICEFILE" \
    PG36_DATABASE_URL="$app_database_url" \
    PG36_HTTP_ADDR="$service_address" \
    PG36_MAX_CONNS=2 \
    PG36_MIN_IDLE_CONNS=1 \
    PG36_ENABLE_FAULTS=1 \
    "$evidence_dir/pg36-ch12-service" \
      >"$output_dir/service.log" \
      2>"$output_dir/service.stderr" &
  service_pid=$!

  local attempt
  for attempt in $(seq 1 100); do
    if ! kill -0 "$service_pid" 2>/dev/null; then
      printf 'ch12 service exited during startup\n' >&2
      return 1
    fi
    if curl --silent --show-error --fail \
      --max-time 1 \
      "${service_url}/health/ready" \
      >"$output_dir/startup-ready.json" \
      2>"$output_dir/startup-ready.stderr"; then
      printf '%s\n' "$service_address" \
        >"$output_dir/service-address.txt"
      return 0
    fi
    sleep 0.05
  done
  printf 'ch12 service did not become ready\n' >&2
  return 1
}

stop_service() {
  if [[ -n "$service_pid" ]] \
     && kill -0 "$service_pid" 2>/dev/null; then
    kill -TERM "$service_pid"
    wait "$service_pid"
  fi
  service_pid=""
}

cleanup() {
  if [[ -n "$service_pid" ]] \
     && kill -0 "$service_pid" 2>/dev/null; then
    kill -TERM "$service_pid" 2>/dev/null || true
    wait "$service_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

write_manifest() {
  local output_dir="$1"
  local candidate_checksum
  candidate_checksum="$(
    python3 - "$script_dir/baseline-v1.0-rc.json" <<'PY'
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
    printf 'validation_path=%s\n' "$validation_path"
    printf 'pooler_validation=%s\n' "$pooler_validation"
    printf 'app_endpoint_source=%s\n' "$app_endpoint_source"
    printf 'runtime_user=pg36_app\n'
    printf 'query_mode=exec\n'
    printf 'go=%s\n' "$(go version)"
    printf 'psql_client=%s\n' "$(psql --version)"
    printf 'pgx_module=%s\n' "$(
      cd "$script_dir/service"
      GOWORK=off go list -m -f '{{.Path}} {{.Version}}' \
        github.com/jackc/pgx/v5
    )"
    printf 'release_candidate_checksum=%s\n' \
      "$candidate_checksum"
    psql -X -w -qAt \
      --dbname="$admin_connection" \
      --set=ON_ERROR_STOP=1 \
      --command="
        SELECT 'server_version=' ||
               current_setting('server_version');
        SELECT 'server_port=' ||
               current_setting('port');
        SELECT 'database=' || current_database();
        SELECT 'in_recovery=' ||
               pg_catalog.pg_is_in_recovery();
      "
    sha256sum "$evidence_dir/pg36-ch12-service"
    find "$script_dir" -type f \
      ! -path "$script_dir/service/.git/*" \
      -print0 \
      | sort -z \
      | xargs -0 sha256sum
  } >"$output_dir/manifest.txt"
}

run_suite() {
  local output_dir="$1"
  PYTHONPYCACHEPREFIX="$output_dir/.pycache" \
    "$script_dir/run_service_lab.py" \
      --base-url "$service_url" \
      --service "$pg_service" \
      --evidence-dir "$output_dir" \
      >"$output_dir/service-lab.txt" \
      2>"$output_dir/service-lab.stderr"

  run_sql_file "$script_dir/verify.sql" \
    >"$output_dir/verify.txt" \
    2>"$output_dir/verify.stderr"
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$output_dir/model-verify-after.txt" \
    2>"$output_dir/model-verify-after.stderr"
  write_manifest "$output_dir"
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

expect_reset_failure() {
  local label="$1"
  local token="$2"
  local target="$3"
  local expected_text="$4"
  local output_dir="$5"
  set +e
  run_sql_file "$script_dir/reset.sql" \
    --set=reset_token="$token" \
    --set=reset_target="$target" \
    >"$output_dir/reset-${label}.stdout" \
    2>"$output_dir/reset-${label}.stderr"
  local reset_exit=$?
  set -e
  if [[ "$reset_exit" -ne 3 ]] \
     || ! grep -Fq "$expected_text" \
          "$output_dir/reset-${label}.stderr"; then
    printf 'reset guard %s did not refuse as expected\n' \
      "$label" >&2
    return 1
  fi
  printf 'exit=%s\n' "$reset_exit" \
    >"$output_dir/reset-${label}.exit"
}

run_reset() {
  local output_dir="$1"
  run_sql_file "$script_dir/reset.sql" \
    --set=reset_token="${PG36_RESET_TOKEN:-}" \
    --set=reset_target="${PG36_RESET_TARGET:-}" \
    >"$output_dir/reset.txt" \
    2>"$output_dir/reset.stderr"
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$output_dir/model-verify-after-reset.txt" \
    2>"$output_dir/model-verify-after-reset.stderr"
}

run_once() {
  local output_dir="$1"
  mkdir -p "$output_dir"
  run_preflight "$output_dir"
  run_setup "$output_dir"
  start_service "$output_dir"
  run_suite "$output_dir"
  stop_service
  run_review "$output_dir"
}

run_full() {
  run_preflight "$evidence_dir"
  run_setup "$evidence_dir"
  build_service
  start_service "$evidence_dir"
  run_suite "$evidence_dir"
  expect_reset_failure \
    wrong-token \
    WRONG \
    pg36_shop/shop_ch12 \
    'invalid ch12 action token' \
    "$evidence_dir"
  expect_reset_failure \
    active-service \
    RESET_CH12_SERVICE_LAB \
    pg36_shop/shop_ch12 \
    'pg36-ch12-api still has database sessions' \
    "$evidence_dir"
  stop_service
  expect_reset_failure \
    wrong-target \
    RESET_CH12_SERVICE_LAB \
    pg36_shop/not-shop-ch12 \
    'invalid ch12 target token' \
    "$evidence_dir"

  PG36_RESET_TOKEN=RESET_CH12_SERVICE_LAB \
    PG36_RESET_TARGET=pg36_shop/shop_ch12 \
    run_reset "$evidence_dir"

  local rebuild_dir="$evidence_dir/rebuild"
  mkdir -p "$rebuild_dir"
  run_preflight "$rebuild_dir"
  run_setup "$rebuild_dir"
  start_service "$rebuild_dir"
  run_suite "$rebuild_dir"
  stop_service
  run_review "$rebuild_dir"
}

case "$action" in
  setup)
    run_preflight "$evidence_dir"
    run_setup "$evidence_dir"
    ;;
  build)
    build_service
    ;;
  run)
    build_service
    run_once "$evidence_dir"
    ;;
  verify)
    run_sql_file "$script_dir/verify.sql"
    ;;
  review)
    run_review "$evidence_dir"
    ;;
  reset)
    run_preflight "$evidence_dir"
    run_reset "$evidence_dir"
    ;;
  all)
    run_full
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
