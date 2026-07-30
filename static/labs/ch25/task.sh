#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
upstream_root="$(cd -- "$script_dir/.." && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch25/$(date -u +%Y%m%dT%H%M%SZ)}"
ssh_user="${PG36_SSH_USER:-vagrant}"
bastion="${PG36_BASTION:-10.10.10.10}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|exercise|verify|review|all}" \
    "capture is L0 and read-only; exercise is L1-ephemeral on the l2 sandbox bastion" \
    "no action deploys live rules, submits a live alert, creates a silence, changes PostgreSQL, or contacts a real receiver" \
    "capture/all require PG36_EVIDENCE_DIR to be absent or empty" \
    "exercise/verify/review require PG36_EVIDENCE_DIR to point to an existing evidence bundle"
}

case "$action" in
  lint|capture|exercise|verify|review|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3 ssh scp
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

require_capture() {
  if [[ ! -f "$evidence_dir/observability-evidence.json" ]]; then
    printf 'observability evidence does not exist: %s\n' \
      "$evidence_dir/observability-evidence.json" >&2
    exit 66
  fi
}

require_complete() {
  require_capture
  if [[ ! -f "$evidence_dir/isolated-exercise.txt" ]]; then
    printf 'isolated exercise log does not exist: %s\n' \
      "$evidence_dir/isolated-exercise.txt" >&2
    exit 66
  fi
}

capture_live() {
  python3 "$script_dir/capture.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --ssh-user "$ssh_user" \
    --output "$evidence_dir/observability-evidence.json"
}

exercise_isolated() {
  require_capture
  python3 "$script_dir/exercise.py" \
    --source-dir "$script_dir" \
    --ssh-user "$ssh_user" \
    --bastion "$bastion" \
    --output "$evidence_dir/isolated-exercise.txt"
}

validate_complete() {
  require_complete
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --evidence "$evidence_dir/observability-evidence.json" \
    --isolated-log "$evidence_dir/isolated-exercise.txt" \
    --output "$evidence_dir/validation-report.json"
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$evidence_dir/negative-report.json"
}

review_complete() {
  require_complete
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch25-lint.XXXXXX")"
  trap 'case "$lint_dir" in "${TMPDIR:-/tmp}"/pg36-ch25-lint.*) rm -rf -- "$lint_dir";; esac' RETURN
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --output "$lint_dir/validation-report.json"
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$lint_dir/negative-report.json"
  printf 'status=lint-ok\n'
  printf 'recording_rules=18\n'
  printf 'alert_rules=13\n'
  printf 'accepted_alerts=7\n'
  printf 'proposed_alerts=6\n'
  printf 'counterexamples=25-rejected\n'
  printf 'live_deployment=false\n'
  printf 'production_ch25_gate=pending\n'
}

case "$action" in
  lint)
    lint_contracts
    ;;
  capture)
    require_new_evidence_dir
    capture_live
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  exercise)
    exercise_isolated
    printf 'status=exercise-ok\n'
    printf 'live_deployment=false\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    validate_complete
    printf 'status=verify-ok\n'
    printf 'counterexamples=25-rejected\n'
    printf 'production_ch25_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_complete
    ;;
  all)
    require_new_evidence_dir
    capture_live
    exercise_isolated
    validate_complete
    review_complete | tee "$evidence_dir/review.txt"
    chmod 0600 "$evidence_dir/review.txt"
    printf 'status=all-ok\n'
    printf 'mutation=live-none,isolated-ephemeral-cleaned\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
