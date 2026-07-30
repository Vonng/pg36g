#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
upstream_root="$(cd -- "$script_dir/.." && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch30/$(date -u +%Y%m%dT%H%M%SZ)}"
ssh_user="${PG36_SSH_USER:-vagrant}"
bastion="${PG36_BASTION:-10.10.10.10}"
old_bin="${PG36_CH30_OLD_BIN:-/usr/lib/postgresql/17/bin}"
old_share="${PG36_CH30_OLD_SHARE:-/usr/share/postgresql/17}"
new_bin="${PG36_CH30_NEW_BIN:-/usr/lib/postgresql/18/bin}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|exercise|verify|review|all}" \
    "capture is L0 read-only; exercise/all are L2 private temporary-cluster experiments" \
    "the runner never downloads or installs PostgreSQL binaries" \
    "set PG36_CH30_OLD_BIN, PG36_CH30_OLD_SHARE, and PG36_CH30_NEW_BIN before capture" \
    "no Pigsty-managed data directory, service, traffic, inventory, or route is touched"
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

require_preflight() {
  if [[ ! -f "$evidence_dir/preflight-evidence.json" ]]; then
    printf 'preflight evidence does not exist: %s\n' \
      "$evidence_dir/preflight-evidence.json" >&2
    exit 66
  fi
}

require_exercise() {
  require_preflight
  for evidence_file in \
    "$evidence_dir/remote/upgrade-evidence.json" \
    "$evidence_dir/remote/fixture-cleanup.json" \
    "$evidence_dir/remote-cleanup.json"
  do
    if [[ ! -f "$evidence_file" ]]; then
      printf 'exercise evidence does not exist: %s\n' \
        "$evidence_file" >&2
      exit 66
    fi
  done
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch30-lint.XXXXXX")"
  trap 'case "$lint_dir" in "${TMPDIR:-/tmp}"/pg36-ch30-lint.*) rm -rf -- "$lint_dir";; esac' RETURN
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --requirements "$script_dir/requirements.json" \
    --contract "$script_dir/upgrade-contract.json" \
    --negative-cases "$script_dir/negative-cases.json" \
    --negative-output "$lint_dir/negative-report.json" \
    --output "$lint_dir/validation-report.json"
  printf 'status=lint-ok\n'
  printf 'declared_counterexamples=30-schema-valid\n'
  printf 'upgrade_method=copy-only\n'
  printf 'production_ch30_gate=pending\n'
}

capture_preflight() {
  python3 "$script_dir/capture.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --requirements "$script_dir/requirements.json" \
    --contract "$script_dir/upgrade-contract.json" \
    --old-bin "$old_bin" \
    --old-share "$old_share" \
    --new-bin "$new_bin" \
    --ssh-user "$ssh_user" \
    --bastion "$bastion" \
    --output "$evidence_dir/preflight-evidence.json"
}

exercise_bounded() {
  require_preflight
  python3 "$script_dir/exercise.py" \
    --source-dir "$script_dir" \
    --evidence-dir "$evidence_dir" \
    --old-bin "$old_bin" \
    --old-share "$old_share" \
    --new-bin "$new_bin" \
    --ssh-user "$ssh_user" \
    --bastion "$bastion"
}

verify_complete() {
  require_exercise
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --upstream-root "$upstream_root" \
    --requirements "$script_dir/requirements.json" \
    --contract "$script_dir/upgrade-contract.json" \
    --negative-cases "$script_dir/negative-cases.json" \
    --preflight "$evidence_dir/preflight-evidence.json" \
    --upgrade "$evidence_dir/remote/upgrade-evidence.json" \
    --fixture-cleanup "$evidence_dir/remote/fixture-cleanup.json" \
    --remote-cleanup "$evidence_dir/remote-cleanup.json" \
    --negative-output "$evidence_dir/negative-report.json" \
    --output "$evidence_dir/validation-report.json" \
    --public-summary "$evidence_dir/public-summary.json"
}

review_complete() {
  require_exercise
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
  exercise)
    exercise_bounded
    printf 'status=exercise-ok\n'
    printf 'upgrade_method=copy\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    verify_complete
    printf 'status=verify-ok\n'
    printf 'declared_counterexamples=30-rejected\n'
    printf 'live_mutants=20-rejected\n'
    printf 'production_ch30_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_complete
    ;;
  all)
    require_new_evidence_dir
    capture_preflight
    exercise_bounded
    verify_complete
    review_complete | tee "$evidence_dir/review.txt"
    chmod 0600 "$evidence_dir/review.txt"
    printf 'status=all-ok\n'
    printf 'mutation=marker-bound-private-pg17-to-pg18-fixture-only\n'
    printf 'managed_pigsty_cluster_changed=false\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
