#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ssh_user="${PG36_SSH_USER:-vagrant}"

if [[ "${PG36_CH23_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
   || "${PG36_CH23_NONPRODUCTION:-}" != "true" \
   || "${PG36_CH23_SYNTHETIC_DATA_ONLY:-}" != "true" \
   || "${PG36_CH23_RESET_CONFIRM:-}" \
      != "DROP_CH23_SYNTHETIC_SECURITY_FIXTURE" ]]; then
  printf '%s\n' \
    "refusing fixture reset: exact target, nonproduction, synthetic-data, and destructive confirmation guards are required" >&2
  exit 77
fi

ssh \
  -F /dev/null \
  -o BatchMode=yes \
  -o ConnectTimeout=5 \
  -o UserKnownHostsFile=/dev/null \
  -o StrictHostKeyChecking=no \
  -o LogLevel=ERROR \
  "${ssh_user}@10.10.10.11" \
  'sudo -n -iu postgres /usr/bin/psql -X -v ON_ERROR_STOP=1 -d test --file=-' \
  < "$script_dir/reset-fixture.sql"

printf 'status=fixture-reset\n'
printf 'removed=schema-pg36_ch23-and-five-synthetic-roles\n'
printf 'preserved=predeclared-login-test-and-all-nonfixture-objects\n'
