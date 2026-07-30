#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-all}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch36/$(date -u +%Y%m%dT%H%M%SZ)}"

usage() {
  printf '%s\n' \
    "usage: $0 {lint|compile|verify|review|all}" \
    "all chapter 36 actions are offline and read-only with respect to chapters 32-35" \
    "compile creates a new closure bundle; verify/review/all consume an existing bundle" \
    "no action connects to PostgreSQL, SSH, monitoring, ticketing, or messaging systems"
}

case "$action" in
  lint|compile|verify|review|all)
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
  mkdir -p -- "$evidence_dir"
  chmod 0700 "$evidence_dir"
}

require_bundle() {
  local name
  for name in \
    closure-report.json \
    postmortem-portfolio.json \
    roadmap-90d.json \
    capability-assessment.json \
    input-manifest.json \
    source-manifest.json
  do
    if [[ ! -f "$evidence_dir/$name" ]]; then
      printf 'evidence file does not exist: %s\n' "$evidence_dir/$name" >&2
      exit 66
    fi
  done
}

compile_bundle() {
  python3 "$script_dir/compile.py" \
    --source-dir "$script_dir" \
    --output-dir "$evidence_dir"
}

verify_bundle() {
  require_bundle
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --bundle-dir "$evidence_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$evidence_dir/validation-report.json" \
    --negative-output "$evidence_dir/negative-report.json" \
    --public-summary "$evidence_dir/public-summary.json"
}

review_bundle() {
  require_bundle
  for name in validation-report.json negative-report.json public-summary.json
  do
    if [[ ! -f "$evidence_dir/$name" ]]; then
      printf 'validated evidence file does not exist: %s\n' "$evidence_dir/$name" >&2
      exit 66
    fi
  done
  python3 "$script_dir/review.py" "$evidence_dir"
}

lint_contracts() {
  local lint_dir
  lint_dir="$(mktemp -d "${TMPDIR:-/tmp}/pg36-ch36-lint.XXXXXX")"
  python3 "$script_dir/compile.py" \
    --source-dir "$script_dir" \
    --output-dir "$lint_dir" >/dev/null
  python3 "$script_dir/validate.py" \
    --source-dir "$script_dir" \
    --bundle-dir "$lint_dir" \
    --negative-cases "$script_dir/negative-cases.json" \
    --output "$lint_dir/validation-report.json" \
    --negative-output "$lint_dir/negative-report.json" \
    --public-summary "$lint_dir/public-summary.json" >/dev/null
  case "$lint_dir" in
    "${TMPDIR:-/tmp}"/pg36-ch36-lint.*)
      rm -rf -- "$lint_dir"
      ;;
  esac
  printf 'status=lint-ok\n'
  printf 'incident_sources=4-hash-bound\n'
  printf 'declared_counterexamples=36-schema-valid\n'
  printf 'source_files_hash_bound=12\n'
  printf 'production_ch36_gate=pending\n'
  printf 'learner_assessment=not-assessed\n'
}

case "$action" in
  lint)
    lint_contracts
    ;;
  compile)
    require_new_evidence_dir
    compile_bundle
    printf 'mutation=none\n'
    ;;
  verify)
    verify_bundle
    printf 'mutation=none\n'
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
esac
