#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch05/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch05-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {observe|transaction|blocking|verify|review|all}" \
    "required: PGSERVICEFILE points to a private PostgreSQL service file" \
    "prerequisite: the ch04-v1 model is installed and verified" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR" \
    "blocking optional: PG36_DASHBOARD_HOLD_SECONDS=0..25" \
    "note: all business writes are rolled back; this chapter has no reset"
}

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

for command_name in psql sha256sum grep; do
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
      "$script_dir/observe.sql" \
      "$script_dir/transaction-errors.sql" \
      "$script_dir/wal-rollback.sql" \
      "$script_dir/blocking-blocker.sql" \
      "$script_dir/blocking-waiter.sql" \
      "$script_dir/blocking-lab.sh" \
      "$script_dir/verify.sql" \
      "$script_dir/lab-contract.md" \
      "$script_dir/timeline.mmd" \
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

run_observe() {
  run_psql_file "$script_dir/observe.sql" \
    >"$evidence_dir/observe.txt" \
    2>"$evidence_dir/observe.stderr"
}

run_transaction() {
  run_psql_file "$script_dir/transaction-errors.sql" \
    >"$evidence_dir/transaction-errors.stdout" \
    2>"$evidence_dir/transaction-errors.stderr"

  for sqlstate in 22012 25P02 23514; do
    if [[ "$(grep -c "ERROR:  ${sqlstate}" \
              "$evidence_dir/transaction-errors.stderr")" -ne 1 ]]; then
      printf 'expected exactly one SQLSTATE %s in transaction probe\n' \
        "$sqlstate" >&2
      exit 1
    fi
  done

  if ! grep -Fxq 'state_restored=true' \
       "$evidence_dir/transaction-errors.stdout"; then
    printf 'transaction failure/savepoint probe did not restore state\n' >&2
    exit 1
  fi

  run_psql_file "$script_dir/wal-rollback.sql" \
    >"$evidence_dir/wal-rollback.txt" \
    2>"$evidence_dir/wal-rollback.stderr"

  if ! grep -Fxq 'wal_insert_advanced=t' \
       "$evidence_dir/wal-rollback.txt" \
     || ! grep -Fxq 'state_restored=t' \
       "$evidence_dir/wal-rollback.txt"; then
    printf 'WAL/rollback probe did not satisfy its invariants\n' >&2
    exit 1
  fi
}

run_blocking() {
  PGSERVICE="$pg_service" \
  PG36_EVIDENCE_DIR="$evidence_dir/blocking" \
    "$script_dir/blocking-lab.sh" \
      >"$evidence_dir/blocking.stdout" \
      2>"$evidence_dir/blocking.stderr"
}

run_verify() {
  local evidence_name="$1"
  run_psql_file "$script_dir/verify.sql" \
    >"$evidence_dir/$evidence_name" \
    2>"$evidence_dir/${evidence_name%.txt}.stderr"
}

run_full_review() {
  run_verify verify-before.txt
  run_observe
  run_transaction
  run_blocking
  run_verify verify-after.txt
}

case "$action" in
  observe)
    write_manifest
    run_verify verify-before.txt
    run_observe
    ;;
  transaction)
    write_manifest
    run_verify verify-before.txt
    run_transaction
    run_verify verify-after.txt
    ;;
  blocking)
    write_manifest
    run_verify verify-before.txt
    run_blocking
    run_verify verify-after.txt
    ;;
  verify)
    write_manifest
    run_verify verify.txt
    ;;
  review|all)
    write_manifest
    run_full_review
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
