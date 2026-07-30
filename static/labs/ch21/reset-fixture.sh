#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
run_id="${PG36_CH21_RUN_ID:-}"
ssh_user="${PG36_SSH_USER:-vagrant}"

if [[ "${PG36_CH21_TARGET:-}" != "pg36-l2-vagrant/pg-test" \
   || "${PG36_CH21_NONPRODUCTION:-}" != "true" \
   || "${PG36_CH21_PRODUCTION_DATA:-}" != "false" \
   || "${PG36_CH21_PRODUCTION_TRAFFIC:-}" != "false" \
   || "${PG36_CH21_RESET_CONFIRM:-}" != "DELETE_ONE_CH21_SANDBOX_RUN" ]]; then
  printf '%s\n' \
    "refusing destructive reset: exact sandbox and reset guards are required" >&2
  exit 77
fi

if [[ ! "$run_id" =~ ^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$ ]]; then
  printf 'refusing invalid run id: %s\n' "$run_id" >&2
  exit 64
fi

ssh_args=(
  ssh -F /dev/null
  -o BatchMode=yes
  -o ConnectTimeout=5
  -o UserKnownHostsFile=/dev/null
  -o StrictHostKeyChecking=no
  -o LogLevel=ERROR
)

restore_root="/data/pg36-ch21-restore/$run_id"
"${ssh_args[@]}" "$ssh_user@10.10.10.13" \
  sudo -n bash -s -- "$restore_root" <<'REMOTE'
set -Eeuo pipefail
restore_root="$1"
case "$restore_root" in
  /data/pg36-ch21-restore/run_????????T??????Z_????????) ;;
  *) printf 'refusing unexpected restore path\n' >&2; exit 64 ;;
esac
[[ ! -L "$restore_root" ]] || {
  printf 'refusing symlink restore root\n' >&2
  exit 73
}
if [[ -s "$restore_root/data/postmaster.pid" \
   || -S "$restore_root/socket/.s.PGSQL.55432" ]]; then
  printf 'refusing to delete a possibly running restore\n' >&2
  exit 73
fi
if [[ -d "$restore_root" ]]; then
  rm -rf -- "$restore_root"
fi
REMOTE

"${ssh_args[@]}" "$ssh_user@10.10.10.11" \
  "sudo -n -iu postgres /usr/bin/psql -X -v ON_ERROR_STOP=1 -q -d test --set=run_id='$run_id' --file=-" \
  < "$script_dir/reset-fixture.sql"

printf 'status=one-run-reset\n'
printf 'run_id=%s\n' "$run_id"
printf 'restore_directory=deleted-if-present\n'
printf 'fixture_rows=deleted\n'
