#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
expected_target="pg36-l2-vagrant/pg-meta+pg-test"
expected_token="RESET_CH19_L2_SANDBOX"

die() {
  printf 'reset refused: %s\n' "$*" >&2
  exit 77
}

[[ "${PG36_RESET_TARGET:-}" == "$expected_target" ]] \
  || die "PG36_RESET_TARGET must equal $expected_target"
[[ "${PG36_CONFIRM_RESET:-}" == "$expected_token" ]] \
  || die "PG36_CONFIRM_RESET must equal $expected_token"
[[ "${PG36_NO_PRODUCTION_DATA:-}" == "yes" ]] \
  || die "PG36_NO_PRODUCTION_DATA=yes is required"
[[ "${PG36_CLIENTS_DRAINED:-}" == "yes" ]] \
  || die "PG36_CLIENTS_DRAINED=yes is required"

pigsty_home="${PG36_PIGSTY_HOME:-}"
inventory="${PG36_CH19_INVENTORY:-}"
allowlist="${PG36_MACHINE_ID_ALLOWLIST:-}"
reset_evidence="${PG36_RESET_EVIDENCE_DIR:-}"

[[ -n "$pigsty_home" && -d "$pigsty_home" ]] \
  || die "PG36_PIGSTY_HOME must name the exact Pigsty v4.4.0 directory"
[[ -x "$pigsty_home/pgsql-rm.yml" && -f "$pigsty_home/configure" ]] \
  || die "Pigsty removal playbook or release marker is missing"
grep -qx 'PIGSTY_VERSION=v4.4.0' "$pigsty_home/configure" \
  || die "Pigsty home is not exact v4.4.0"
[[ -n "$inventory" && -f "$inventory" ]] \
  || die "PG36_CH19_INVENTORY must name the private inventory"
[[ -n "$allowlist" && -f "$allowlist" ]] \
  || die "PG36_MACHINE_ID_ALLOWLIST must name a reviewed JSON allowlist"
[[ -n "$reset_evidence" ]] \
  || die "PG36_RESET_EVIDENCE_DIR must name a new retained pre-reset evidence directory"

inventory_mode="$(stat -f '%Lp' "$inventory" 2>/dev/null || stat -c '%a' "$inventory")"
[[ "$inventory_mode" == "600" ]] \
  || die "private inventory mode must be 0600"
[[ ! -e "$reset_evidence" ]] \
  || die "PG36_RESET_EVIDENCE_DIR must not already exist"

PG36_EVIDENCE_DIR="$reset_evidence" \
PG36_CH19_INVENTORY="$inventory" \
  bash "$script_dir/task.sh" all

python3 - "$allowlist" "$reset_evidence" <<'PY'
import json
import sys
from pathlib import Path

allowlist = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evidence = Path(sys.argv[2])
expected_hosts = {
    "10.10.10.10",
    "10.10.10.11",
    "10.10.10.12",
    "10.10.10.13",
}
if allowlist.get("schema") != "pg36-ch19-machine-identity-allowlist-v1":
    raise SystemExit("reset refused: machine identity allowlist schema drifted")
identities = allowlist.get("machine_id_sha256", {})
if set(identities) != expected_hosts:
    raise SystemExit("reset refused: machine identity allowlist host set drifted")
for host, expected in identities.items():
    facts = json.loads(
        (evidence / "hosts" / f"{host}.json").read_text(encoding="utf-8")
    )
    if facts.get("machine_id_sha256") != expected:
        raise SystemExit(f"reset refused: machine identity changed for {host}")
print("machine_identity_preflight=ok")
PY

printf '%s\n' \
  "DESTRUCTIVE: this will remove pg-test and pg-meta, including PostgreSQL data" \
  "and the configured backup state for those sandbox clusters."
printf 'Type %s to continue: ' "$expected_token" >/dev/tty
IFS= read -r typed </dev/tty
[[ "$typed" == "$expected_token" ]] || die "interactive acknowledgement did not match"

export ANSIBLE_INVENTORY="$inventory"
"$pigsty_home/pgsql-rm.yml" -i "$inventory" -l pg-test
"$pigsty_home/pgsql-rm.yml" -i "$inventory" -l pg-meta

printf 'status=reset-complete\n'
printf 'target=%s\n' "$expected_target"
printf 'recoverability=destructive-cluster-removal; rebuild from declaration or restore exercise\n'
