#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ch19_dir="$(cd -- "$script_dir/../ch19" && pwd -P)"
action="${1:-all}"
ssh_user="${PG36_SSH_USER:-vagrant}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch20/$(date -u +%Y%m%dT%H%M%SZ)}"
inventory="${PG36_CH19_INVENTORY:-}"
private_service_dir=""

usage() {
  printf '%s\n' \
    "usage: $0 {capture|verify|review|all|drill:switchover|reset:fixture}" \
    "capture is read-only and writes one current-phase.json snapshot" \
    "verify/review/all require PG36_EVIDENCE_DIR pointing to a complete existing drill bundle" \
    "all means verify+review and never switches, fails over, reinitializes, or deletes anything" \
    "drill:switchover is an L2 sandbox mutation and requires every guard in lab-contract.md" \
    "reset:fixture is destructive and separately guarded; it is never part of all or drill:switchover"
}

case "$action" in
  capture|verify|review|all|drill:switchover|reset:fixture)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3 ssh psql
do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

require_drill_bundle() {
  if [[ ! -d "$evidence_dir/drill" ]]; then
    printf 'complete drill directory does not exist: %s\n' "$evidence_dir/drill" >&2
    exit 66
  fi
}

capture_current() {
  mkdir -p "$evidence_dir"
  python3 "$script_dir/capture.py" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --output "$evidence_dir/current-phase.json" \
    --phase current \
    --ssh-user "$ssh_user"
}

validate_drill() {
  require_drill_bundle
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --failure-model "$script_dir/failure-model.json" \
    --evidence "$evidence_dir/drill" \
    --output "$evidence_dir/drill/validation-report.json"
  python3 "$script_dir/validate.py" \
    --requirements "$script_dir/requirements.json" \
    --failure-model "$script_dir/failure-model.json" \
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
  if [[ "${PG36_CH20_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
     || "${PG36_CH20_NONPRODUCTION:-}" != "true" \
     || "${PG36_CH20_PRODUCTION_DATA:-}" != "false" \
     || "${PG36_CH20_PRODUCTION_TRAFFIC:-}" != "false" \
     || "${PG36_CH20_CONFIRM:-}" != "SWITCH_CH20_PG_TEST_1_TO_2_AND_BACK" ]]; then
    printf '%s\n' \
      "refusing planned switchover: exact target, nonproduction, data, traffic, and confirmation guards are required" >&2
    exit 77
  fi
  if [[ -z "$inventory" || ! -f "$inventory" ]]; then
    printf 'private chapter-19 inventory is required\n' >&2
    exit 64
  fi
  if [[ -e "$evidence_dir" ]] \
     && [[ -n "$(find "$evidence_dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    printf 'refusing to overwrite non-empty evidence directory: %s\n' "$evidence_dir" >&2
    exit 73
  fi
}

run_ch19_gate() {
  local destination="$1"
  PG36_CH19_INVENTORY="$inventory" \
  PG36_EVIDENCE_DIR="$destination" \
  PG36_SSH_USER="$ssh_user" \
    bash "$ch19_dir/task.sh" all
}

run_guarded_drill() {
  require_mutation_guards
  mkdir -p "$evidence_dir"

  private_service_dir="$(mktemp -d /tmp/pg36-ch20-client.XXXXXX)"
  cleanup_private_dir() {
    case "$private_service_dir" in
      /tmp/pg36-ch20-client.*)
        rm -rf -- "$private_service_dir"
        ;;
      *)
        printf 'refusing unexpected temporary cleanup target: %s\n' "$private_service_dir" >&2
        ;;
    esac
  }
  trap cleanup_private_dir EXIT

  run_ch19_gate "$evidence_dir/preflight-ch19"
  python3 "$script_dir/private_client_service.py" \
    --inventory "$inventory" \
    --requirements "$script_dir/requirements.json" \
    --output "$private_service_dir/pg_service.conf"
  python3 "$script_dir/drill.py" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --service-file "$private_service_dir/pg_service.conf" \
    --output "$evidence_dir/drill" \
    --ssh-user "$ssh_user" \
    --target-token "pg36-l2-vagrant/pg-test" \
    --confirmation "SWITCH_CH20_PG_TEST_1_TO_2_AND_BACK" \
    --authority "nonproduction-no-data-no-traffic"
  validate_drill
  run_ch19_gate "$evidence_dir/postflight-ch19"
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
    printf 'counterexamples=10-rejected\n'
    printf 'production_ch20_gate=pending\n'
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
  drill:switchover)
    run_guarded_drill
    printf 'status=planned-drill-ok\n'
    printf 'mutation=planned-switchover-and-baseline-restore\n'
    printf 'production_ch20_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
  reset:fixture)
    exec bash "$script_dir/reset-fixture.sh"
    ;;
esac
