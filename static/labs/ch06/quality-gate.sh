#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch06/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch06-${action}"
static_status=skipped
live_status=skipped
negative_status=skipped

usage() {
  printf '%s\n' \
    "usage: $0 {static|live|negative|review|all}" \
    "static does not connect to PostgreSQL" \
    "live/negative/review/all require PGSERVICEFILE" \
    "prerequisite for live checks: ch04-v1 model" \
    "optional: PGSERVICE (default pg36-admin), PG36_EVIDENCE_DIR"
}

case "$action" in
  static|live|negative|review|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash find python3 sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

if [[ "$action" != 'static' ]]; then
  if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
    usage >&2
    exit 64
  fi
  for command_name in psql grep; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      printf 'missing required command: %s\n' "$command_name" >&2
      exit 69
    fi
  done
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

write_manifest() {
  {
    printf 'captured_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'service=%s\n' "$pg_service"
    printf 'python=%s\n' "$(python3 --version 2>&1)"
    if command -v psql >/dev/null 2>&1; then
      printf 'psql_client=%s\n' "$(psql --version)"
    fi
    sha256sum \
      "$script_dir/baseline-schema.json" \
      "$script_dir/baseline-v0.1.json" \
      "$script_dir/baseline-guide.md" \
      "$script_dir/delivery-manifest.json" \
      "$script_dir/change-template.md" \
      "$script_dir/waiver-template.md" \
      "$script_dir/evidence-ledger.md" \
      "$script_dir/context.sql" \
      "$script_dir/session-profile.sql" \
      "$script_dir/wrong-session.sql" \
      "$script_dir/query-contract.sql" \
      "$script_dir/pigsty-declaration.example.yml" \
      "$script_dir/check_baseline.py" \
      "$script_dir/quality-gate.sh"
  } >"$evidence_dir/manifest.txt"
}

run_static() {
  "$script_dir/check_baseline.py" \
    --repo-root "$repo_root" \
    >"$evidence_dir/baseline-check.txt" \
    2>"$evidence_dir/baseline-check.stderr"

  PYTHONPYCACHEPREFIX="$evidence_dir/pycache" \
    python3 -m py_compile "$script_dir/check_baseline.py"

  local shell_count=0
  : >"$evidence_dir/shell-syntax.txt"
  while IFS= read -r -d '' shell_file; do
    bash -n "$shell_file"
    printf '%s\n' "${shell_file#"$repo_root/"}" \
      >>"$evidence_dir/shell-syntax.txt"
    shell_count=$((shell_count + 1))
  done < <(
    find "$repo_root/static/labs" \
      -maxdepth 2 \
      -type f \
      -name '*.sh' \
      -print0
  )

  if [[ "$shell_count" -eq 0 ]]; then
    printf 'no shell scripts found for syntax validation\n' >&2
    exit 1
  fi
  printf 'shell_script_count=%s\n' "$shell_count" \
    >>"$evidence_dir/shell-syntax.txt"
  static_status=pass
}

run_live() {
  run_psql_file "$script_dir/session-profile.sql" \
    >"$evidence_dir/session-profile.txt" \
    2>"$evidence_dir/session-profile.stderr"

  run_psql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/model-verify.txt" \
    2>"$evidence_dir/model-verify.stderr"

  run_psql_file "$script_dir/query-contract.sql" \
    >"$evidence_dir/query-contract.txt" \
    2>"$evidence_dir/query-contract.stderr"

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
    " >"$evidence_dir/server-facts.txt"

  live_status=pass
}

run_negative() {
  local wrong_session_exit
  local wrong_target_exit

  set +e
  run_psql_file "$script_dir/wrong-session.sql" \
    >"$evidence_dir/wrong-session.stdout" \
    2>"$evidence_dir/wrong-session.stderr"
  wrong_session_exit=$?
  set -e

  if [[ "$wrong_session_exit" -ne 3 ]] \
     || [[ "$(grep -c 'ERROR:  P0601' \
               "$evidence_dir/wrong-session.stderr")" -ne 1 ]]; then
    printf 'wrong-session fixture did not fail exactly with P0601\n' >&2
    exit 1
  fi

  set +e
  run_psql_file "$script_dir/session-profile.sql" \
    --set=expected_db=definitely_not_pg36_shop \
    --set=VERBOSITY=sqlstate \
    >"$evidence_dir/wrong-target.stdout" \
    2>"$evidence_dir/wrong-target.stderr"
  wrong_target_exit=$?
  set -e

  if [[ "$wrong_target_exit" -ne 3 ]] \
     || [[ "$(grep -c 'ERROR:  P0001' \
               "$evidence_dir/wrong-target.stderr")" -ne 1 ]]; then
    printf 'wrong-target fixture did not fail exactly with P0001\n' >&2
    exit 1
  fi

  {
    printf 'status=ok\n'
    printf 'wrong_session_exit=%s\n' "$wrong_session_exit"
    printf 'wrong_session_sqlstate=P0601\n'
    printf 'wrong_target_exit=%s\n' "$wrong_target_exit"
    printf 'wrong_target_sqlstate=P0001\n'
  } >"$evidence_dir/negative-summary.txt"

  negative_status=pass
}

write_summary() {
  local baseline_checksum=''
  local model_checksum=''

  if [[ -f "$evidence_dir/baseline-check.txt" ]]; then
    baseline_checksum="$(
      grep '^baseline_checksum=' \
        "$evidence_dir/baseline-check.txt" \
        | head -1 \
        | cut -d= -f2-
    )"
  fi
  if [[ -f "$evidence_dir/model-verify.txt" ]]; then
    model_checksum="$(
      grep 'relation_checksum=' \
        "$evidence_dir/model-verify.txt" \
        | tail -1 \
        | sed 's/^[[:space:]]*//' \
        | cut -d= -f2-
    )"
  fi

  {
    printf 'status=ok\n'
    printf 'gate_version=ch06-v0.1\n'
    printf 'action=%s\n' "$action"
    printf 'static=%s\n' "$static_status"
    printf 'live=%s\n' "$live_status"
    printf 'negative=%s\n' "$negative_status"
    if [[ -n "$baseline_checksum" ]]; then
      printf 'baseline_checksum=%s\n' "$baseline_checksum"
    fi
    if [[ -n "$model_checksum" ]]; then
      printf 'relation_checksum=%s\n' "$model_checksum"
    fi
  } >"$evidence_dir/gate-summary.txt"
}

write_manifest

case "$action" in
  static)
    run_static
    ;;
  live)
    run_live
    ;;
  negative)
    run_negative
    ;;
  review|all)
    run_static
    run_live
    run_negative
    ;;
esac

write_summary
printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
