#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ssh_user="${PG36_SSH_USER:-vagrant}"

if [[ "${PG36_CH22_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
   || "${PG36_CH22_NONPRODUCTION:-}" != "true" \
   || "${PG36_CH22_PRODUCTION_DATA:-}" != "false" \
   || "${PG36_CH22_PRODUCTION_TRAFFIC:-}" != "false" \
   || "${PG36_CH22_RESET_CONFIRM:-}" != "DROP_CH22_SYNTHETIC_SCHEMA_AND_ROLE" ]]; then
  printf '%s\n' \
    "refusing destructive reset: exact sandbox and reset guards are required" >&2
  exit 77
fi

ssh -F /dev/null \
  -o BatchMode=yes \
  -o ConnectTimeout=5 \
  -o UserKnownHostsFile=/dev/null \
  -o StrictHostKeyChecking=no \
  -o LogLevel=ERROR \
  "$ssh_user@10.10.10.11" \
  "sudo -n -iu postgres /usr/bin/psql -X -v ON_ERROR_STOP=1 -q -d test --file=-" \
  < "$script_dir/reset-fixture.sql"

printf 'status=fixture-reset\n'
printf 'dropped=pg36_ch22\n'
printf 'preserved_declared_role=test\n'
printf 'topology_or_timeline_reset=false\n'
