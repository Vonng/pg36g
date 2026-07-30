#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch35/$(date -u +%Y%m%dT%H%M%SZ)}"
ssh_user="${PG36_SSH_USER:-vagrant}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|verify|review|all|drill:forensics}" \
    "capture is read-only against the declared Pigsty sandbox" \
    "verify/review/all consume an existing evidence bundle and never mutate PostgreSQL" \
    "drill:forensics mutates only disposable stopped/working clones under an exact temporary root" \
    "drill:forensics never modifies managed PGDATA, deletes pg_wal, uses dangerous recovery GUCs, or executes reset:host"
}

case "$action" in
  lint|capture|verify|review|all|drill:forensics)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3 ssh
do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

require_new_evidence_dir() {
  if [[ -e "$evidence_dir" ]] \
     && [[ -n "$(find "$evidence_dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    printf 'refusing to overwrite non-empty evidence directory: %s\n' \
      "$evidence_dir" >&2
    exit 73
  fi
  mkdir -p -- "$evidence_dir"
  chmod 0700 "$evidence_dir"
}

require_complete_bundle() {
  local name
  for name in before.json after.json classification.json
  do
    if [[ ! -f "$evidence_dir/$name" ]]; then
      printf 'evidence file does not exist: %s\n' \
        "$evidence_dir/$name" >&2
      exit 66
    fi
  done
  for name in \
    exercise-evidence.json \
    blind-packets.json \
    hidden-answers.json \
    cleanup.json \
    source-manifest.json \
    run-manifest.json
  do
    if [[ ! -f "$evidence_dir/exercise/$name" ]]; then
      printf 'evidence file does not exist: %s\n' \
        "$evidence_dir/exercise/$name" >&2
      exit 66
    fi
  done
}

require_mutation_guards() {
  if [[ "${PG36_CH35_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
     || "${PG36_CH35_NONPRODUCTION:-}" != "true" \
     || "${PG36_CH35_PRODUCTION_DATA:-}" != "false" \
     || "${PG36_CH35_PRODUCTION_TRAFFIC:-}" != "false" \
     || "${PG36_CH35_CONFIRM:-}" != "CLONE_CLASSIFY_RECOVER_CH35" ]]; then
    printf '%s\n' \
      "refusing chapter 35 drill: exact target, nonproduction, data, traffic, and confirmation guards are required" >&2
    exit 77
  fi
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch35-lint.XXXXXX")"
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$lint_dir/validation-report.json"
  case "$lint_dir" in
    "${TMPDIR:-/tmp}"/pg36-ch35-lint.*)
      rm -rf -- "$lint_dir"
      ;;
  esac
  printf 'status=lint-ok\n'
  printf 'declared_counterexamples=35-schema-valid\n'
  printf 'source_files_hash_bound=13\n'
  printf 'managed_reset_host_executed=false\n'
  printf 'production_ch35_gate=pending\n'
}

capture_current() {
  require_new_evidence_dir
  python3 "$script_dir/capture.py" \
    --requirements "$script_dir/requirements.json" \
    --output "$evidence_dir/current.json" \
    --phase current \
    --ssh-user "$ssh_user"
}

verify_bundle() {
  require_complete_bundle
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --evidence-dir "$evidence_dir" \
    --negative-output "$evidence_dir/negative-report.json" \
    --public-summary "$evidence_dir/public-summary.json" \
    --output "$evidence_dir/validation-report.json"
}

review_bundle() {
  require_complete_bundle
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

run_drill() {
  require_mutation_guards
  require_new_evidence_dir
  python3 "$script_dir/capture.py" \
    --requirements "$script_dir/requirements.json" \
    --output "$evidence_dir/before.json" \
    --phase before \
    --ssh-user "$ssh_user"
  python3 "$script_dir/exercise.py" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --output "$evidence_dir/exercise" \
    --ssh-user "$ssh_user" \
    --target-token "pg36-l2-vagrant/pg-test" \
    --confirmation "CLONE_CLASSIFY_RECOVER_CH35" \
    --authority "nonproduction-no-data-no-traffic"
  python3 "$script_dir/classify.py" \
    --contract "$script_dir/classification-contract.json" \
    --packets "$evidence_dir/exercise/blind-packets.json" \
    --output "$evidence_dir/classification.json"
  python3 "$script_dir/capture.py" \
    --requirements "$script_dir/requirements.json" \
    --output "$evidence_dir/after.json" \
    --phase after \
    --ssh-user "$ssh_user"
  verify_bundle
  review_bundle | tee "$evidence_dir/review.txt"
  chmod 0600 "$evidence_dir/review.txt"
}

case "$action" in
  lint)
    lint_contracts
    ;;
  capture)
    capture_current
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    verify_bundle
    printf 'status=verify-ok\n'
    printf 'counterexamples=35-rejected\n'
    printf 'production_ch35_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_bundle
    ;;
  all)
    verify_bundle
    review_bundle | tee "$evidence_dir/review.txt"
    chmod 0600 "$evidence_dir/review.txt"
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  drill:forensics)
    run_drill
    printf 'status=clone-only-forensic-drill-ok\n'
    printf 'mutation=disposable-heap-byte-and-collation-metadata-only\n'
    printf 'managed_pgdata_mutated=false\n'
    printf 'managed_reset_host_executed=false\n'
    printf 'production_ch35_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
