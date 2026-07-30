#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch08/estimate-$(date -u +%Y%m%dT%H%M%SZ)}"
pg_service="${PGSERVICE:-pg36-admin}"
connection="service=${pg_service} application_name=pg36-ch08-estimate"

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  printf 'estimate case requires PGSERVICEFILE\n' >&2
  exit 64
fi

for command_name in psql python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

mkdir -p "$evidence_dir"

psql -X -w \
  --dbname="$connection" \
  --set=ON_ERROR_STOP=1 \
  --file="$script_dir/../ch07/verify.sql" \
  >"$evidence_dir/preflight.txt" \
  2>"$evidence_dir/preflight.stderr"

capture_plan() {
  local mode="$1"
  local output="$2"
  psql -X -w -qAt \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    --set=plan_mode="$mode" \
    --set=tenant_id=1 \
    --file="$script_dir/../ch07/parameter-plan.sql" \
    >"$output"
  python3 -m json.tool "$output" >/dev/null
}

capture_plan force_generic_plan "$evidence_dir/generic-hot.json"
capture_plan force_custom_plan "$evidence_dir/custom-hot.json"

"$script_dir/make_signals.py" \
  --mode estimate \
  --evidence-dir "$evidence_dir" \
  >"$evidence_dir/signal-build.txt"

cat "$evidence_dir/signals.json"
