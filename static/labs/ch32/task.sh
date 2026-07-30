#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch32/$(date -u +%Y%m%dT%H%M%SZ)}"
ssh_user="${PG36_SSH_USER:-vagrant}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|verify|review|all|drill:pitr}" \
    "capture is read-only against the declared Pigsty sandbox" \
    "verify/review/all use an existing complete evidence bundle and do not mutate PostgreSQL" \
    "drill:pitr creates a bounded fixture, fresh full backup, two isolated side restores, and an exact cleanup" \
    "drill:pitr requires the five PG36_CH32_* guard variables documented in lab-contract.md"
}

case "$action" in
  lint|capture|verify|review|all|drill:pitr)
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
  local evidence_file
  for evidence_file in \
    preflight-evidence.json \
    exercise-manifest.json \
    source-before.json \
    fixture.json \
    backup.json \
    inclusive-plan.json \
    inclusive-recovery.json \
    exclusive-plan.json \
    exclusive-recovery.json \
    reconciliation.json \
    source-after.json \
    cleanup.json
  do
    if [[ ! -f "$evidence_dir/$evidence_file" ]]; then
      printf 'evidence file does not exist: %s\n' \
        "$evidence_dir/$evidence_file" >&2
      exit 66
    fi
  done
}

require_mutation_guards() {
  if [[ "${PG36_CH32_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
     || "${PG36_CH32_NONPRODUCTION:-}" != "true" \
     || "${PG36_CH32_PRODUCTION_DATA:-}" != "false" \
     || "${PG36_CH32_PRODUCTION_TRAFFIC:-}" != "false" \
     || "${PG36_CH32_CONFIRM:-}" != "RANDOM_XID_PITR_RECONCILE_CH32" ]]; then
    printf '%s\n' \
      "refusing chapter 32 drill: exact target, nonproduction, data, traffic, and confirmation guards are required" >&2
    exit 77
  fi
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch32-lint.XXXXXX")"
  trap 'case "$lint_dir" in "${TMPDIR:-/tmp}"/pg36-ch32-lint.*) rm -rf -- "$lint_dir";; esac' RETURN
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --negative-output "$lint_dir/negative-report.json" \
    --output "$lint_dir/validation-report.json"
  printf 'status=lint-ok\n'
  printf 'declared_counterexamples=32-schema-valid\n'
  printf 'source_files_hash_bound=12\n'
  printf 'production_ch32_gate=pending\n'
}

capture_preflight() {
  python3 "$script_dir/capture.py" \
    --source-dir "$script_dir" \
    --ssh-user "$ssh_user" \
    --output "$evidence_dir/preflight-evidence.json"
}

run_exercise() {
  local seed_args=()
  if [[ -n "${PG36_CH32_SEED:-}" ]]; then
    seed_args=(--seed "$PG36_CH32_SEED")
  fi
  python3 "$script_dir/exercise.py" \
    --source-dir "$script_dir" \
    --evidence-dir "$evidence_dir" \
    --ssh-user "$ssh_user" \
    --target-token "$PG36_CH32_TARGET" \
    --confirmation "$PG36_CH32_CONFIRM" \
    --authority "nonproduction-no-data-no-traffic" \
    "${seed_args[@]}"
}

verify_bundle() {
  require_complete_bundle
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --evidence-dir "$evidence_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --negative-output "$evidence_dir/negative-report.json" \
    --output "$evidence_dir/validation-report.json" \
    --public-summary "$evidence_dir/public-summary.json"
}

review_bundle() {
  require_complete_bundle
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

case "$action" in
  lint)
    lint_contracts
    ;;
  capture)
    require_new_evidence_dir
    capture_preflight
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    verify_bundle
    printf 'status=verify-ok\n'
    printf 'counterexamples=32-rejected\n'
    printf 'production_ch32_gate=pending\n'
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
  drill:pitr)
    require_mutation_guards
    require_new_evidence_dir
    capture_preflight
    run_exercise
    verify_bundle
    review_bundle | tee "$evidence_dir/review.txt"
    chmod 0600 "$evidence_dir/review.txt"
    printf 'status=drill-ok\n'
    printf 'mutation=bounded-fixture-backup-side-pitr-reconciliation\n'
    printf 'source_fixture=removed\n'
    printf 'restore_roots=removed\n'
    printf 'fresh_backup=retained\n'
    printf 'production_ch32_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
