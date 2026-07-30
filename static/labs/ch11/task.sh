#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch11/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch11-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|risk|expand|backfill|validate|partition|verify|review|reset|all}" \
    "case actions rebuild the dedicated ch11 fixture unless noted" \
    "all/review run lock, compatibility, interruption, constraint, partition, and contract assertions" \
    "reset requires PG36_RESET_TOKEN and PG36_RESET_TARGET" \
    "all actions require PGSERVICEFILE and ch04-v1"
}

case "$action" in
  setup|risk|expand|backfill|validate|partition|verify|review|reset|all)
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

capture_csv() {
  local sql_file="$1"
  local output_file="$2"
  run_sql_file "$sql_file" --csv --quiet \
    >"$output_file" \
    2>"${output_file%.csv}.stderr"
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
    for source_file in "$script_dir"/*; do
      if [[ -f "$source_file" ]]; then
        sha256sum "$source_file"
      fi
    done
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

run_risk() {
  run_sql_file "$script_dir/default-probe.sql" \
    >"$evidence_dir/default-probe.txt" \
    2>"$evidence_dir/default-probe.stderr"
  capture_csv \
    "$script_dir/default-catalog.sql" \
    "$evidence_dir/default-catalog.csv"

  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/run_lock_case.py" \
      --service "$pg_service" \
      --script-dir "$script_dir" \
      --evidence-dir "$evidence_dir" \
      >"$evidence_dir/lock-case.txt" \
      2>"$evidence_dir/lock-case.stderr"
}

run_expand() {
  run_sql_file "$script_dir/expand.sql" \
    >"$evidence_dir/expand.txt" \
    2>"$evidence_dir/expand.stderr"
  "$script_dir/online-index.sh" build \
    >"$evidence_dir/index-build.txt" \
    2>"$evidence_dir/index-build.stderr"
  run_sql_file "$script_dir/compatibility.sql" \
    >"$evidence_dir/compatibility.txt" \
    2>"$evidence_dir/compatibility.stderr"
  capture_csv \
    "$script_dir/constraint-catalog.sql" \
    "$evidence_dir/constraint-before.csv"
}

run_backfill() {
  set +e
  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/backfill.py" \
      --service "$pg_service" \
      --batch-size 5000 \
      --max-batches 2 \
      --output "$evidence_dir/backfill-interrupted.json" \
      >"$evidence_dir/backfill-interrupted.txt" \
      2>"$evidence_dir/backfill-interrupted.stderr"
  interrupted_exit=$?
  set -e
  if [[ "$interrupted_exit" -ne 75 ]]; then
    printf 'backfill interruption exited %s, expected 75\n' \
      "$interrupted_exit" >&2
    exit 1
  fi

  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/backfill.py" \
      --service "$pg_service" \
      --batch-size 5000 \
      --output "$evidence_dir/backfill-resumed.json" \
      >"$evidence_dir/backfill-resumed.txt" \
      2>"$evidence_dir/backfill-resumed.stderr"
}

run_validate() {
  run_sql_file "$script_dir/validate.sql" \
    >"$evidence_dir/validate.txt" \
    2>"$evidence_dir/validate.stderr"
  capture_csv \
    "$script_dir/constraint-catalog.sql" \
    "$evidence_dir/constraint-after.csv"
  "$script_dir/online-index.sh" drop \
    >"$evidence_dir/index-drop.txt" \
    2>"$evidence_dir/index-drop.stderr"
  run_sql_file "$script_dir/switch.sql" \
    >"$evidence_dir/switch.txt" \
    2>"$evidence_dir/switch.stderr"
}

run_contract_refusal() {
  set +e
  run_sql_file "$script_dir/contract-gate.sql" \
    --set=VERBOSITY=verbose \
    >"$evidence_dir/contract-gate.stdout" \
    2>"$evidence_dir/contract-gate.stderr"
  contract_exit=$?
  set -e
  printf 'exit=%s\n' "$contract_exit" \
    >"$evidence_dir/contract-gate.exit"
  if [[ "$contract_exit" -ne 3 ]] \
     || ! grep -Fq 'P3612' \
          "$evidence_dir/contract-gate.stderr"; then
    printf 'contract gate did not refuse with P3612\n' >&2
    exit 1
  fi
}

run_partition() {
  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/partition_lab.py" \
      --service "$pg_service" \
      --script-dir "$script_dir" \
      --evidence-dir "$evidence_dir" \
      >"$evidence_dir/partition-lab.txt" \
      2>"$evidence_dir/partition-lab.stderr"
}

run_verify() {
  run_sql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify-after.txt" \
    2>"$evidence_dir/model-verify-after.stderr"
}

run_review() {
  PYTHONPYCACHEPREFIX="$evidence_dir/.pycache" \
    "$script_dir/review.py" \
      --evidence-dir "$evidence_dir" \
      --repo-root "$repo_root" \
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
    >"$evidence_dir/model-verify-after.txt" \
    2>"$evidence_dir/model-verify-after.stderr"
}

run_full() {
  run_preflight
  run_setup
  run_risk
  run_expand
  run_backfill
  run_validate
  run_contract_refusal
  run_partition
  run_verify
  run_review
}

write_manifest

case "$action" in
  setup)
    run_preflight
    run_setup
    ;;
  risk)
    run_preflight
    run_setup
    run_risk
    ;;
  expand)
    run_preflight
    run_setup
    run_risk
    run_expand
    ;;
  backfill)
    run_preflight
    run_setup
    run_risk
    run_expand
    run_backfill
    ;;
  validate)
    run_preflight
    run_setup
    run_risk
    run_expand
    run_backfill
    run_validate
    ;;
  partition)
    run_preflight
    run_setup
    run_partition
    ;;
  verify)
    run_verify
    ;;
  reset)
    run_preflight
    run_reset
    ;;
  review|all)
    run_full
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
