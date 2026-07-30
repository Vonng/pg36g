#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
ssh_user="${PG36_SSH_USER:-vagrant}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch19/$(date -u +%Y%m%dT%H%M%SZ)}"
inventory="${PG36_CH19_INVENTORY:-}"

usage() {
  printf '%s\n' \
    "usage: $0 {project|capture|verify|review|all|reset:cluster}" \
    "normal actions are read-only against pg36-l2-vagrant; all never deploys, fails over, restores, or resets" \
    "project/capture/all require PG36_CH19_INVENTORY pointing to a private mode-0600 Pigsty inventory" \
    "verify/review require PG36_EVIDENCE_DIR pointing to an existing capture" \
    "reset:cluster is destructive, separate, and guarded; read lab-contract.md before considering it"
}

case "$action" in
  project|capture|verify|review|all|reset:cluster)
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

require_inventory() {
  if [[ -z "$inventory" || ! -f "$inventory" ]]; then
    usage >&2
    exit 64
  fi
}

project_inventory() {
  local output_dir="$1"
  require_inventory
  mkdir -p "$output_dir"
  python3 "$script_dir/inventory_projection.py" \
    "$inventory" \
    --output "$output_dir/inventory-projection.json"
}

capture_bundle() {
  require_inventory
  mkdir -p "$evidence_dir"
  python3 "$script_dir/capture.py" \
    --inventory "$inventory" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --output "$evidence_dir" \
    --ssh-user "$ssh_user"
}

validate_bundle() {
  if [[ ! -d "$evidence_dir" ]]; then
    printf 'evidence directory does not exist: %s\n' "$evidence_dir" >&2
    exit 66
  fi
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --baseline "$script_dir/baseline-v2.0-sandbox.json" \
    --evidence "$evidence_dir" \
    --output "$evidence_dir/validation-report.json"
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --baseline "$script_dir/baseline-v2.0-sandbox.json" \
    --evidence "$evidence_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$evidence_dir/negative-report.json"
}

review_bundle() {
  python3 "$script_dir/review.py" \
    "$evidence_dir" \
    --source-dir "$script_dir"
}

case "$action" in
  project)
    project_inventory "$evidence_dir"
    printf 'status=projection-ok\n'
    printf 'secrets=redacted\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  capture)
    capture_bundle
    ;;
  verify)
    validate_bundle
    printf 'status=verify-ok\n'
    printf 'counterexamples=9-rejected\n'
    printf 'production_ch19_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  review)
    review_bundle
    ;;
  all)
    capture_bundle
    validate_bundle
    review_bundle | tee "$evidence_dir/review.txt"
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  reset:cluster)
    exec bash "$script_dir/reset-cluster.sh"
    ;;
esac
