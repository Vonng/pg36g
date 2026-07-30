#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch33/$(date -u +%Y%m%dT%H%M%SZ)}"
ssh_user="${PG36_SSH_USER:-vagrant}"
inventory="${PG36_CH33_INVENTORY:-}"
private_service_dir=""

usage() {
  printf '%s\n' \
    "usage: $0 {lint|capture|verify|review|all|drill:failover}" \
    "capture is read-only against the declared Pigsty sandbox" \
    "verify/review/all require an existing complete evidence bundle and never mutate PostgreSQL" \
    "drill:failover performs one guarded Patroni service stop/start, automatic failover, planned baseline restore, and disposable rebuild lab" \
    "drill:failover never stops DCS, injects a network partition, deletes managed PGDATA, or executes reinit"
}

case "$action" in
  lint|capture|verify|review|all|drill:failover)
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
  for name in \
    before.json \
    stop-action.json \
    old-primary-fence.json \
    failed.json \
    start-action.json \
    rejoined.json \
    journal-projection.json \
    client-reconciliation.json \
    baseline-restore-action.json \
    restored.json \
    fixture-cleanup.json \
    dcs-tabletop.json \
    drill-manifest.json
  do
    if [[ ! -f "$evidence_dir/managed/$name" ]]; then
      printf 'evidence file does not exist: %s\n' \
        "$evidence_dir/managed/$name" >&2
      exit 66
    fi
  done
  if [[ ! -f "$evidence_dir/rebuild.json" ]]; then
    printf 'evidence file does not exist: %s\n' \
      "$evidence_dir/rebuild.json" >&2
    exit 66
  fi
}

require_mutation_guards() {
  if [[ "${PG36_CH33_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
     || "${PG36_CH33_NONPRODUCTION:-}" != "true" \
     || "${PG36_CH33_PRODUCTION_DATA:-}" != "false" \
     || "${PG36_CH33_PRODUCTION_TRAFFIC:-}" != "false" \
     || "${PG36_CH33_CONFIRM:-}" != "FENCE_FAILOVER_REJOIN_REBUILD_CH33" ]]; then
    printf '%s\n' \
      "refusing chapter 33 drill: exact target, nonproduction, data, traffic, and confirmation guards are required" >&2
    exit 77
  fi
  if [[ -z "$inventory" || ! -f "$inventory" ]]; then
    printf 'private chapter 33 inventory is required\n' >&2
    exit 64
  fi
}

cleanup_private_service() {
  if [[ -z "$private_service_dir" ]]; then
    return
  fi
  case "$private_service_dir" in
    /tmp/pg36-ch33-client.*)
      rm -rf -- "$private_service_dir"
      ;;
    *)
      printf 'refusing unexpected private cleanup target: %s\n' \
        "$private_service_dir" >&2
      ;;
  esac
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch33-lint.XXXXXX")"
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$lint_dir/validation-report.json"
  case "$lint_dir" in
    "${TMPDIR:-/tmp}"/pg36-ch33-lint.*)
      rm -rf -- "$lint_dir"
      ;;
  esac
  printf 'status=lint-ok\n'
  printf 'declared_counterexamples=33-schema-valid\n'
  printf 'source_files_hash_bound=15\n'
  printf 'production_ch33_gate=pending\n'
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

run_drill() {
  require_mutation_guards
  require_new_evidence_dir
  private_service_dir="$(mktemp -d /tmp/pg36-ch33-client.XXXXXX)"
  chmod 0700 "$private_service_dir"
  trap cleanup_private_service EXIT

  python3 "$script_dir/private_client_service.py" \
    --inventory "$inventory" \
    --requirements "$script_dir/requirements.json" \
    --output "$private_service_dir/pg_service.conf"

  python3 "$script_dir/exercise.py" \
    --requirements "$script_dir/requirements.json" \
    --source-dir "$script_dir" \
    --service-file "$private_service_dir/pg_service.conf" \
    --output "$evidence_dir/managed" \
    --ssh-user "$ssh_user" \
    --target-token "pg36-l2-vagrant/pg-test" \
    --confirmation "FENCE_FAILOVER_REJOIN_REBUILD_CH33" \
    --authority "nonproduction-no-data-no-traffic"

  run_id="$(
    python3 - "$evidence_dir/managed/drill-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["run_id"])
PY
  )"
  python3 "$script_dir/rebuild_lab.py" \
    --requirements "$script_dir/requirements.json" \
    --run-id "$run_id" \
    --ssh-user "$ssh_user" \
    --output "$evidence_dir/rebuild.json"

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
    printf 'counterexamples=33-rejected\n'
    printf 'production_ch33_gate=pending\n'
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
  drill:failover)
    run_drill
    printf 'status=failover-rebuild-drill-ok\n'
    printf 'mutation=controlled-process-failover-and-disposable-rebuild\n'
    printf 'managed_pgdata_deleted=false\n'
    printf 'dcs_or_network_fault_injected=false\n'
    printf 'production_ch33_gate=pending\n'
    printf 'evidence=%s\n' "$evidence_dir"
    ;;
esac
