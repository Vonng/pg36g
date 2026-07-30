#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/../../.." && pwd -P)"
action="${1:-all}"
pg_service="${PGSERVICE:-pg36-admin}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch08/$(date -u +%Y%m%dT%H%M%SZ)}"
connection="service=${pg_service} application_name=pg36-ch08-${action}"

usage() {
  printf '%s\n' \
    "usage: $0 {setup|estimate|lock|client|mystery|diagnose|reveal|verify|review|all}" \
    "all/review test all three causes, blind diagnosis, negative reveal, and restoration" \
    "mystery/diagnose/reveal reuse the same PG36_EVIDENCE_DIR" \
    "required: PGSERVICEFILE; optional PGSERVICE, PG36_CASE_SEED"
}

case "$action" in
  setup|estimate|lock|client|mystery|diagnose|reveal|verify|review|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

if [[ "$action" != diagnose && "$action" != reveal ]]; then
  for command_name in psql sha256sum; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      printf 'missing required command: %s\n' "$command_name" >&2
      exit 69
    fi
  done
  if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
    usage >&2
    exit 64
  fi
fi

mkdir -p "$evidence_dir"

run_sql_file() {
  local sql_file="$1"
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --file="$sql_file"
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
    sha256sum "$script_dir"/*
  } >"$evidence_dir/manifest.txt"
}

run_preflight() {
  run_sql_file "$script_dir/../ch05/verify.sql" \
    >"$evidence_dir/preflight.txt" \
    2>"$evidence_dir/preflight.stderr"
}

ensure_ch07_fixture() {
  if psql -X -w \
      --dbname="$connection" \
      --set=ON_ERROR_STOP=1 \
      --file="$script_dir/../ch07/verify.sql" \
      >"$evidence_dir/ch07-verify.txt" \
      2>"$evidence_dir/ch07-verify.stderr"; then
    printf 'fixture=reused\n' >"$evidence_dir/ch07-fixture.txt"
  else
    mkdir -p "$evidence_dir/ch07-rebuild"
    PG36_EVIDENCE_DIR="$evidence_dir/ch07-rebuild" \
      "$script_dir/../ch07/task.sh" all \
      >"$evidence_dir/ch07-rebuild.stdout" \
      2>"$evidence_dir/ch07-rebuild.stderr"
    printf 'fixture=controlled-rebuild\n' \
      >"$evidence_dir/ch07-fixture.txt"
  fi
}

run_direct_case() {
  local mode="$1"
  mkdir -p "$evidence_dir/$mode"
  PG36_EVIDENCE_DIR="$evidence_dir/$mode" \
    "$script_dir/${mode}-case.sh" \
    >"$evidence_dir/${mode}.stdout" \
    2>"$evidence_dir/${mode}.stderr"
  "$script_dir/diagnose.py" \
    --signals "$evidence_dir/$mode/signals.json" \
    --output "$evidence_dir/$mode/diagnosis.json" \
    >"$evidence_dir/${mode}-diagnose.txt" \
    2>"$evidence_dir/${mode}-diagnose.stderr"
}

run_mystery_only() {
  PG36_EVIDENCE_DIR="$evidence_dir" \
    "$script_dir/mystery.sh" run
}

diagnose_mystery() {
  PG36_EVIDENCE_DIR="$evidence_dir" \
    "$script_dir/mystery.sh" diagnose
}

reveal_mystery() {
  PG36_EVIDENCE_DIR="$evidence_dir" \
    "$script_dir/mystery.sh" reveal
}

run_verify() {
  run_sql_file "$script_dir/verify.sql" \
    >"$evidence_dir/verify.txt" \
    2>"$evidence_dir/verify.stderr"
}

run_full_review() {
  run_preflight
  ensure_ch07_fixture
  run_direct_case estimate
  run_direct_case lock
  run_direct_case client

  mkdir -p "$evidence_dir/mystery"
  PG36_CASE_SEED="${PG36_CASE_SEED:-pg36-ch08-review-seed}" \
  PG36_EVIDENCE_DIR="$evidence_dir/mystery" \
    "$script_dir/mystery.sh" run \
    >"$evidence_dir/mystery-run.txt" \
    2>"$evidence_dir/mystery-run.stderr"

  PG36_WRONG_DIAGNOSIS_FILE="$evidence_dir/mystery/public/wrong-diagnosis.json" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["PG36_WRONG_DIAGNOSIS_FILE"]).write_text(
    json.dumps(
        {
            "status": "deliberately-wrong",
            "diagnosis": "wrong-answer-for-negative-control",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

  if PG36_EVIDENCE_DIR="$evidence_dir/mystery" \
     PG36_DIAGNOSIS_FILE="$evidence_dir/mystery/public/wrong-diagnosis.json" \
     PG36_REVEAL_FILE="$evidence_dir/mystery/public/negative-reveal.json" \
       "$script_dir/mystery.sh" reveal \
       >"$evidence_dir/mystery/negative-reveal.txt" \
       2>"$evidence_dir/mystery/negative-reveal.stderr"; then
    printf 'wrong mystery diagnosis unexpectedly passed reveal\n' >&2
    exit 1
  fi

  PG36_EVIDENCE_DIR="$evidence_dir/mystery" \
    "$script_dir/mystery.sh" diagnose \
    >"$evidence_dir/mystery/diagnose.txt" \
    2>"$evidence_dir/mystery/diagnose.stderr"
  PG36_EVIDENCE_DIR="$evidence_dir/mystery" \
    "$script_dir/mystery.sh" reveal \
    >"$evidence_dir/mystery/reveal.txt" \
    2>"$evidence_dir/mystery/reveal.stderr"

  run_verify
  "$script_dir/review.py" \
    --evidence-dir "$evidence_dir" \
    --repo-root "$repo_root" \
    >"$evidence_dir/review.txt" \
    2>"$evidence_dir/review.stderr"
  cat "$evidence_dir/review.txt"
}

if [[ "$action" != diagnose && "$action" != reveal ]]; then
  write_manifest
fi

case "$action" in
  setup)
    run_preflight
    ensure_ch07_fixture
    ;;
  estimate|lock|client)
    run_preflight
    if [[ "$action" == estimate ]]; then
      ensure_ch07_fixture
    fi
    run_direct_case "$action"
    run_verify
    cat "$evidence_dir/$action/diagnosis.json"
    ;;
  mystery)
    run_preflight
    ensure_ch07_fixture
    run_mystery_only
    ;;
  diagnose)
    diagnose_mystery
    ;;
  reveal)
    reveal_mystery
    ;;
  verify)
    run_verify
    ;;
  review|all)
    run_full_review
    ;;
esac

printf 'action=%s evidence=%s\n' "$action" "$evidence_dir"
