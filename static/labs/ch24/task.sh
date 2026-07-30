#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
upstream_root="$(cd -- "$script_dir/.." && pwd -P)"
ch19_dir="$upstream_root/ch19"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch24/$(date -u +%Y%m%dT%H%M%SZ)}"
inventory="${PG36_CH19_INVENTORY:-}"
ssh_user="${PG36_SSH_USER:-vagrant}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|verify|review|all}" \
    "all actions are L0: this chapter never changes databases, pools, topology, credentials, alert routes, or data" \
    "capture/all run the chapter-19 read-only gate and require a private mode-0600 PG36_CH19_INVENTORY" \
    "capture/all require PG36_EVIDENCE_DIR to be absent or empty" \
    "verify/review require PG36_EVIDENCE_DIR to point to an existing complete evidence bundle"
}

case "$action" in
  lint|capture|verify|review|all)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3
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
}

require_existing_evidence() {
  if [[ ! -f "$evidence_dir/governance-evidence.json" ]]; then
    printf 'governance evidence does not exist: %s\n' \
      "$evidence_dir/governance-evidence.json" >&2
    exit 66
  fi
}

capture_evidence() {
  require_new_evidence_dir
  if [[ -z "$inventory" || ! -f "$inventory" ]]; then
    usage >&2
    exit 64
  fi
  mkdir -p "$evidence_dir"
  PG36_CH19_INVENTORY="$inventory" \
  PG36_EVIDENCE_DIR="$evidence_dir/ch19" \
  PG36_SSH_USER="$ssh_user" \
    bash "$ch19_dir/task.sh" all
  python3 "$script_dir/build_evidence.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --ch19-evidence "$evidence_dir/ch19" \
    --output "$evidence_dir/governance-evidence.json"
}

validate_evidence() {
  require_existing_evidence
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --evidence "$evidence_dir/governance-evidence.json" \
    --output "$evidence_dir/validation-report.json"
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --evidence "$evidence_dir/governance-evidence.json" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$evidence_dir/negative-report.json"
}

review_evidence() {
  require_existing_evidence
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch24-lint.XXXXXX")"
  trap 'rm -rf -- "$lint_dir"' RETURN
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
  printf 'counterexamples=20-rejected\n'
  printf 'mutation=none\n'
  printf 'production_ch24_gate=pending\n'
}

case "$action" in
  lint)
    lint_contracts
    ;;
  capture)
    capture_evidence
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    validate_evidence
    printf 'status=verify-ok\n'
    printf 'counterexamples=20-rejected\n'
    printf 'production_ch24_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_evidence
    ;;
  all)
    capture_evidence
    validate_evidence
    review_evidence | tee "$evidence_dir/review.txt"
    printf 'status=all-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
