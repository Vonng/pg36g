#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
inventory="${PG36_CH19_INVENTORY:-}"
evidence_dir="${PG36_EVIDENCE_DIR:-}"

if [[ "${PG36_CH20_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
   || "${PG36_CH20_NONPRODUCTION:-}" != "true" \
   || "${PG36_CH20_PRODUCTION_DATA:-}" != "false" \
   || "${PG36_CH20_PRODUCTION_TRAFFIC:-}" != "false" \
   || "${PG36_CH20_CLIENTS_DRAINED:-}" != "true" \
   || "${PG36_CH20_RESET_CONFIRM:-}" != "DROP_PG36_CH20_FIXTURE" ]]; then
  printf '%s\n' \
    "refusing fixture reset: exact target, nonproduction, no-data, no-traffic, drained-client, and reset guards are required" >&2
  exit 77
fi

if [[ -z "$inventory" || ! -f "$inventory" \
   || -z "$evidence_dir" || ! -d "$evidence_dir/drill" ]]; then
  printf '%s\n' \
    "refusing fixture reset: private inventory and a complete reviewed evidence directory are required" >&2
  exit 64
fi

python3 "$script_dir/review.py" \
  "$evidence_dir" \
  --source-dir "$script_dir" >/dev/null

private_dir="$(mktemp -d /tmp/pg36-ch20-reset.XXXXXX)"
cleanup_private_dir() {
  case "$private_dir" in
    /tmp/pg36-ch20-reset.*)
      rm -rf -- "$private_dir"
      ;;
    *)
      printf 'refusing unexpected temporary cleanup target: %s\n' "$private_dir" >&2
      ;;
  esac
}
trap cleanup_private_dir EXIT

python3 "$script_dir/private_client_service.py" \
  --inventory "$inventory" \
  --requirements "$script_dir/requirements.json" \
  --output "$private_dir/pg_service.conf" >/dev/null

PGSERVICEFILE="$private_dir/pg_service.conf" \
PGSERVICE=pg36-ch20 \
  psql -X -w \
    --dbname=service=pg36-ch20 \
    --set=ON_ERROR_STOP=1 \
    --file "$script_dir/reset-fixture.sql"

printf 'status=fixture-removed\n'
printf 'target=pg36-l2-vagrant/pg-test database=test schema=pg36_ch20\n'
printf 'recoverability=rerun-setup-or-restore-from-retained-evidence\n'
