#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ch19_dir="$(cd -- "$script_dir/../ch19" && pwd -P)"
action="${1:-all}"
ssh_user="${PG36_SSH_USER:-vagrant}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch23/$(date -u +%Y%m%dT%H%M%SZ)}"
credential_inventory="${PG36_CH23_CREDENTIAL_INVENTORY:-}"
ch19_inventory="${PG36_CH19_INVENTORY:-${credential_inventory}}"

usage() {
  printf '%s\n' \
    "usage: $0 {capture|verify|review|all|drill:security|reset:fixture}" \
    "capture is read-only and writes one current-snapshot.json" \
    "verify/review/all require PG36_EVIDENCE_DIR pointing to a complete existing drill bundle" \
    "all means verify+review and never changes roles, credentials, pools, HBA, certificates, or topology" \
    "drill:security is a guarded L2 sandbox experiment; read lab-contract.md before running it" \
    "reset:fixture is destructive, separate, and never called by another action"
}

case "$action" in
  capture|verify|review|all|drill:security|reset:fixture)
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

require_drill_bundle() {
  if [[ ! -d "$evidence_dir/drill" ]]; then
    printf 'complete drill directory does not exist: %s\n' \
      "$evidence_dir/drill" >&2
    exit 66
  fi
}

capture_current() {
  mkdir -p "$evidence_dir"
  python3 "$script_dir/capture.py" \
    --requirements "$script_dir/requirements.json" \
    --output "$evidence_dir/current-snapshot.json" \
    --phase current \
    --ssh-user "$ssh_user"
}

validate_drill() {
  require_drill_bundle
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --evidence "$evidence_dir/drill" \
    --output "$evidence_dir/drill/validation-report.json"
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --evidence "$evidence_dir/drill" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$evidence_dir/drill/negative-report.json"
}

review_drill() {
  require_drill_bundle
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

require_mutation_guards() {
  if [[ "${PG36_CH23_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
     || "${PG36_CH23_NONPRODUCTION:-}" != "true" \
     || "${PG36_CH23_SYNTHETIC_DATA_ONLY:-}" != "true" \
     || "${PG36_CH23_PRODUCTION_TRAFFIC:-}" != "false" \
     || "${PG36_CH23_CONFIRM:-}" != "SECURITY_RLS_ROTATION_CH23" ]]; then
    printf '%s\n' \
      "refusing security drill: exact target, nonproduction, synthetic-data, traffic, and confirmation guards are required" >&2
    exit 77
  fi
  if [[ -z "$credential_inventory" \
     || ! -f "$credential_inventory" ]]; then
    printf 'private chapter-23 credential inventory is required\n' >&2
    exit 64
  fi
  if [[ -z "$ch19_inventory" || ! -f "$ch19_inventory" ]]; then
    printf 'private chapter-19 inventory is required\n' >&2
    exit 64
  fi
  if [[ -e "$evidence_dir" ]] \
     && [[ -n "$(find "$evidence_dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    printf 'refusing to overwrite non-empty evidence directory: %s\n' \
      "$evidence_dir" >&2
    exit 73
  fi
}

run_ch19_gate() {
  local destination="$1"
  PG36_CH19_INVENTORY="$ch19_inventory" \
  PG36_EVIDENCE_DIR="$destination" \
  PG36_SSH_USER="$ssh_user" \
    bash "$ch19_dir/task.sh" all
}

run_guarded_drill() {
  require_mutation_guards
  mkdir -p "$evidence_dir"
  run_ch19_gate "$evidence_dir/preflight-ch19"
  python3 "$script_dir/drill.py" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --credential-inventory "$credential_inventory" \
    --output "$evidence_dir/drill" \
    --ssh-user "$ssh_user" \
    --target-token "pg36-l2-vagrant/pg-test" \
    --confirmation "SECURITY_RLS_ROTATION_CH23" \
    --authority "nonproduction-synthetic-data-only"
  run_ch19_gate "$evidence_dir/postflight-ch19"
  validate_drill
  review_drill | tee "$evidence_dir/review.txt"
}

case "$action" in
  capture)
    capture_current
    printf 'status=capture-ok\n'
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  verify)
    validate_drill
    printf 'status=verify-ok\n'
    printf 'counterexamples=20-rejected\n'
    printf 'production_ch23_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_drill
    ;;
  all)
    validate_drill
    review_drill | tee "$evidence_dir/review.txt"
    printf 'mutation=none\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  drill:security)
    run_guarded_drill
    printf 'status=security-drill-ok\n'
    printf 'mutation=synthetic-fixture-retained-pool-restored-rotation-revoked\n'
    printf 'production_ch23_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  reset:fixture)
    exec bash "$script_dir/reset-fixture.sh"
    ;;
esac
