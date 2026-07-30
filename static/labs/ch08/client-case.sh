#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch08/client-$(date -u +%Y%m%dT%H%M%SZ)}"

mkdir -p "$evidence_dir/raw"

PG36_EVIDENCE_DIR="$evidence_dir/raw" \
"$script_dir/client-write-lab.sh" \
  >"$evidence_dir/fixture.txt" \
  2>"$evidence_dir/fixture.stderr"

"$script_dir/make_signals.py" \
  --mode client \
  --evidence-dir "$evidence_dir" \
  >"$evidence_dir/signal-build.txt"

cat "$evidence_dir/signals.json"
