#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch18/$(date -u +%Y%m%dT%H%M%SZ)}"
admin_connection="service=${pg_service} dbname=pg36_shop application_name=pg36-ch18-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {capture|verify|review|all}" \
    "chapter 18 is a read-only audit: it never creates, alters, or removes database objects" \
    "all verifies chapters 04 and 13-17, captures two deterministic cycles, validates policy counterexamples, and compares state" \
    "database actions require PGSERVICEFILE and the retained upper-volume fixtures"
}

case "$action" in
  capture|verify|review|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash cmp psql python3 sort
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

capture_csv() {
  local sql_file="$1"
  local output_file="$2"
  psql -X -w \
    --dbname="$admin_connection" \
    --set=ON_ERROR_STOP=1 \
    --csv \
    --quiet \
    --file="$sql_file" \
    >"$output_file" \
    2>"${output_file%.csv}.stderr"
}

write_manifest() {
  local output_dir="$1"
  {
    printf 'captured_at=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'action=%s\n' "$action"
    printf 'service=%s\n' "$pg_service"
    printf 'validation_path=read-only-postgresql-catalog+cross-document-policy\n'
    printf 'pigsty_reference=4.4\n'
    printf 'pigsty_l1=not-run\n'
    printf 'model_version=ch04-v1\n'
    printf 'mutation=none\n'
    printf 'upper_volume_preflight=ch04+ch13+ch14+ch15+ch16+ch17\n'
    for name in \
      baseline-v1.6-proposal.json \
      service-catalog.json \
      external-data-contracts.json \
      lower-volume-gates.json \
      negative-cases.json
    do
      printf '%s_canonical_sha256=%s\n' \
        "$name" \
        "$(canonical_json_checksum "$script_dir/$name")"
    done
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
      "
    while IFS= read -r source_file; do
      hash_file "$source_file"
    done < <(
      find "$script_dir" -maxdepth 1 -type f -print \
        | sort
    )
  } >"$output_dir/manifest.txt"
}

run_policy_validation() {
  local output_dir="$1"
  python3 "$script_dir/validate.py" \
    --blueprint "$script_dir/baseline-v1.6-proposal.json" \
    --catalog "$script_dir/service-catalog.json" \
    --contracts "$script_dir/external-data-contracts.json" \
    --gates "$script_dir/lower-volume-gates.json" \
    --output "$output_dir/validation-report.json"
  python3 "$script_dir/validate.py" \
    --blueprint "$script_dir/baseline-v1.6-proposal.json" \
    --catalog "$script_dir/service-catalog.json" \
    --contracts "$script_dir/external-data-contracts.json" \
    --gates "$script_dir/lower-volume-gates.json" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$output_dir/negative-report.json"
}

run_upper_volume_preflight() {
  local output_dir="$1"
  local chapter
  mkdir -p "$output_dir"
  for chapter in ch04 ch13 ch14 ch15 ch16 ch17
  do
    PG36_EVIDENCE_DIR="$output_dir/$chapter" \
      bash "$repo_dir/static/labs/$chapter/task.sh" verify \
      >"$output_dir/${chapter}.stdout" \
      2>"$output_dir/${chapter}.stderr"
  done
  {
    printf 'status=ok\n'
    printf 'chapters=ch04,ch13,ch14,ch15,ch16,ch17\n'
    printf 'mode=retained-fixture-read-only-verification\n'
  } >"$output_dir/summary.txt"
}

capture_cycle() {
  local output_dir="$1"
  mkdir -p "$output_dir"
  capture_csv \
    "$script_dir/platform-state.sql" \
    "$output_dir/platform-state.csv"
  capture_csv \
    "$script_dir/extension-catalog.sql" \
    "$output_dir/extension-catalog.csv"
  capture_csv \
    "$script_dir/schema-catalog.sql" \
    "$output_dir/schema-catalog.csv"
  capture_csv \
    "$script_dir/role-catalog.sql" \
    "$output_dir/role-catalog.csv"
  capture_csv \
    "$script_dir/capability-snapshot.sql" \
    "$output_dir/capability-snapshot.csv"
  run_policy_validation "$output_dir"
  write_manifest "$output_dir"
  python3 "$script_dir/review.py" \
    "$output_dir" \
    --source-dir "$script_dir" \
    >"$output_dir/review.txt"
}

compare_cycles() {
  local first="$1"
  local second="$2"
  local name
  for name in \
    platform-state.csv \
    extension-catalog.csv \
    schema-catalog.csv \
    role-catalog.csv \
    capability-snapshot.csv \
    validation-report.json \
    negative-report.json \
    review.txt
  do
    cmp "$first/$name" "$second/$name"
  done
}

case "$action" in
  capture)
    run_upper_volume_preflight "$evidence_dir/preflight"
    capture_cycle "$evidence_dir/cycle"
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    run_upper_volume_preflight "$evidence_dir/preflight"
    run_policy_validation "$evidence_dir"
    printf 'status=verify-ok\n'
    printf 'pigsty_l1=not-run\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    python3 "$script_dir/review.py" \
      "$evidence_dir" \
      --source-dir "$script_dir"
    ;;
  all)
    run_upper_volume_preflight "$evidence_dir/preflight"
    capture_cycle "$evidence_dir/cycle-1"
    capture_cycle "$evidence_dir/cycle-2"
    compare_cycles \
      "$evidence_dir/cycle-1" \
      "$evidence_dir/cycle-2"
    {
      printf 'status=ok\n'
      printf 'preflight=ch04+ch13+ch14+ch15+ch16+ch17\n'
      printf 'cycles=2-byte-identical\n'
      printf 'documents=catalog+contracts+blueprint+18-pending-gates\n'
      printf 'counterexamples=7-rejected\n'
      printf 'pigsty_l1=not-run\n'
      printf 'mutation=none\n'
    } >"$evidence_dir/final-state.txt"
    cat "$evidence_dir/final-state.txt"
    printf 'evidence=%s\n' "$evidence_dir"
    printf 'release_candidate_checksum=%s\n' \
      "$(canonical_json_checksum \
          "$script_dir/baseline-v1.6-proposal.json")"
    ;;
esac
