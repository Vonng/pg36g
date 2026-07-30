#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
action="${1:-}"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch08/mystery}"
public_dir="$evidence_dir/public"
sealed_dir="$evidence_dir/.sealed"
answer_file="$sealed_dir/answer.json"
diagnosis_file="${PG36_DIAGNOSIS_FILE:-$public_dir/diagnosis.json}"
reveal_file="${PG36_REVEAL_FILE:-$public_dir/reveal.json}"

usage() {
  printf '%s\n' \
    "usage: $0 {run|diagnose|reveal}" \
    "required: PG36_EVIDENCE_DIR" \
    "run: optional PG36_CASE_SEED; requires PGSERVICEFILE" \
    "reveal: optional PG36_DIAGNOSIS_FILE and PG36_REVEAL_FILE"
}

case "$action" in
  run|diagnose|reveal)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

for command_name in bash python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

run_case() {
  if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
    usage >&2
    exit 64
  fi
  if [[ -e "$answer_file" || -e "$public_dir/signals.json" ]]; then
    printf 'refusing to overwrite an existing mystery run: %s\n' \
      "$evidence_dir" >&2
    exit 73
  fi

  mkdir -p "$public_dir" "$sealed_dir"
  chmod 700 "$public_dir" "$sealed_dir"

  local seed="${PG36_CASE_SEED:-}"
  if [[ -z "$seed" ]]; then
    seed="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  fi

  local selection
  selection="$(
    PG36_CASE_SEED_VALUE="$seed" python3 - <<'PY'
import hashlib
import os

seed = os.environ["PG36_CASE_SEED_VALUE"]
digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
modes = ("estimate", "lock", "client")
diagnoses = ("estimate-plan", "lock-wait", "client-slow-consumer")
index = int(digest, 16) % len(modes)
print(f"{digest}|{modes[index]}|{diagnoses[index]}")
PY
  )"

  local seed_digest selected_mode expected_diagnosis
  IFS='|' read -r seed_digest selected_mode expected_diagnosis \
    <<<"$selection"

  PG36_CASE_SEED_VALUE="$seed" \
  PG36_CASE_SEED_DIGEST="$seed_digest" \
  PG36_SELECTED_MODE="$selected_mode" \
  PG36_EXPECTED_DIAGNOSIS="$expected_diagnosis" \
  PG36_ANSWER_FILE="$answer_file" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

answer = {
    "schema": "pg36-ch08-answer-v1",
    "selector": "sha256-mod3-v1",
    "seed": os.environ["PG36_CASE_SEED_VALUE"],
    "seed_sha256": os.environ["PG36_CASE_SEED_DIGEST"],
    "selected_mode": os.environ["PG36_SELECTED_MODE"],
    "expected_diagnosis": os.environ["PG36_EXPECTED_DIAGNOSIS"],
}
path = Path(os.environ["PG36_ANSWER_FILE"])
path.write_text(
    json.dumps(answer, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY

  PG36_CASE_SEED_VALUE="$seed" \
  PG36_PUBLIC_METADATA="$public_dir/metadata.json" \
    python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

metadata = {
    "schema": "pg36-ch08-public-v1",
    "selector": "sha256-mod3-v1",
    "seed": os.environ["PG36_CASE_SEED_VALUE"],
    "captured_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds"),
    "ground_truth_in_public_artifact": False,
}
Path(os.environ["PG36_PUBLIC_METADATA"]).write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

  PG36_EVIDENCE_DIR="$public_dir" \
    "$script_dir/${selected_mode}-case.sh" \
    >"$public_dir/case.stdout" \
    2>"$public_dir/case.stderr"

  if [[ ! -s "$public_dir/signals.json" ]]; then
    printf 'mystery case did not produce public signals\n' >&2
    exit 1
  fi

  printf 'status=ok action=run evidence=%s seed=%s\n' \
    "$evidence_dir" "$seed"
  printf 'ground_truth=%s\n' "$answer_file"
  printf 'public_signals=%s\n' "$public_dir/signals.json"
}

diagnose_case() {
  if [[ ! -s "$public_dir/signals.json" ]]; then
    printf 'missing public signals: run the mystery case first\n' >&2
    exit 66
  fi
  mkdir -p "$(dirname -- "$diagnosis_file")"
  "$script_dir/diagnose.py" \
    --signals "$public_dir/signals.json" \
    --output "$diagnosis_file"
  printf 'answer_artifact_read=false\n'
}

reveal_case() {
  if [[ ! -s "$answer_file" ]]; then
    printf 'missing sealed answer: run the mystery case first\n' >&2
    exit 66
  fi
  if [[ ! -s "$diagnosis_file" ]]; then
    printf 'missing diagnosis: %s\n' "$diagnosis_file" >&2
    exit 66
  fi
  mkdir -p "$(dirname -- "$reveal_file")"

  PG36_ANSWER_FILE="$answer_file" \
  PG36_DIAGNOSIS_FILE_VALUE="$diagnosis_file" \
  PG36_REVEAL_FILE_VALUE="$reveal_file" \
    python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

answer_path = Path(os.environ["PG36_ANSWER_FILE"])
diagnosis_path = Path(os.environ["PG36_DIAGNOSIS_FILE_VALUE"])
reveal_path = Path(os.environ["PG36_REVEAL_FILE_VALUE"])
answer = json.loads(answer_path.read_text(encoding="utf-8"))
diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
actual = diagnosis.get("diagnosis")
expected = answer.get("expected_diagnosis")
matched = actual == expected
result = {
    "schema": "pg36-ch08-reveal-v1",
    "status": "pass" if matched else "fail",
    "matched": matched,
    "diagnosis": actual,
    "expected_diagnosis": expected,
    "selected_mode": answer.get("selected_mode"),
    "seed": answer.get("seed"),
    "seed_sha256": answer.get("seed_sha256"),
}
reveal_path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(
    f"status={result['status']} matched={str(matched).lower()} "
    f"diagnosis={actual} expected={expected}"
)
sys.exit(0 if matched else 1)
PY
}

case "$action" in
  run)
    run_case
    ;;
  diagnose)
    diagnose_case
    ;;
  reveal)
    reveal_case
    ;;
esac
