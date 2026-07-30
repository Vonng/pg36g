#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
evidence_dir="${PG36_EVIDENCE_DIR:-${PWD}/evidence/ch09/concurrent-failure}"
pg_service="${PGSERVICE:-pg36-admin}"
connection="service=${pg_service} application_name=pg36-ch09-concurrent-failure"
index_name="ch09_unique_probe_external_ref_uidx"

usage() {
  printf '%s\n' \
    "usage: $0" \
    "requires PGSERVICEFILE, a fresh ch09 fixture, and PG36_EVIDENCE_DIR"
}

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

for command_name in grep psql; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

mkdir -p "$evidence_dir"

psql_cmd() {
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    "$@"
}

marker_ok="$(
  psql_cmd -qAt --command="
    SELECT pg_catalog.obj_description(
               'shop_private.ch09_unique_probe'::regclass,
               'pg_class'
           ) =
           'pg36 ch09 deterministic index lab; safe to rebuild'
       AND pg_catalog.to_regclass(
               'shop_private.${index_name}'
           ) IS NULL;
  "
)"
if [[ "$marker_ok" != t ]]; then
  printf 'refusing concurrent failure lab: target identity mismatch\n' >&2
  exit 1
fi

set +e
psql_cmd \
  --set=VERBOSITY=verbose \
  --file="$script_dir/concurrent-failure.sql" \
  >"$evidence_dir/create.stdout" \
  2>"$evidence_dir/create.stderr"
create_exit=$?
set -e

if [[ "$create_exit" -ne 3 ]] \
   || ! grep -Fq 'ERROR:  23505' "$evidence_dir/create.stderr"; then
  printf 'concurrent unique build did not fail with SQLSTATE 23505\n' >&2
  exit 1
fi

psql_cmd --csv --command="
  SELECT
      table_class.relname AS table_name,
      index_class.relname AS index_name,
      index_catalog.indisvalid,
      index_catalog.indisready,
      index_catalog.indisunique,
      pg_catalog.pg_relation_size(index_catalog.indexrelid)
          AS index_bytes
  FROM pg_catalog.pg_index AS index_catalog
  JOIN pg_catalog.pg_class AS index_class
    ON index_class.oid = index_catalog.indexrelid
  JOIN pg_catalog.pg_class AS table_class
    ON table_class.oid = index_catalog.indrelid
  WHERE index_catalog.indexrelid =
        'shop_private.${index_name}'::regclass
    AND index_catalog.indrelid =
        'shop_private.ch09_unique_probe'::regclass;
" >"$evidence_dir/invalid-index.csv"

invalid_ok="$(
  psql_cmd -qAt --command="
    SELECT count(*) = 1
       AND bool_and(NOT indisvalid)
       AND bool_and(indisunique)
    FROM pg_catalog.pg_index
    WHERE indexrelid =
          'shop_private.${index_name}'::regclass
      AND indrelid =
          'shop_private.ch09_unique_probe'::regclass;
  "
)"
if [[ "$invalid_ok" != t ]]; then
  printf 'failed build did not leave the expected invalid index\n' >&2
  exit 1
fi

psql_cmd --command="
  DROP INDEX CONCURRENTLY shop_private.${index_name};
" >"$evidence_dir/drop.stdout" 2>"$evidence_dir/drop.stderr"

remaining="$(
  psql_cmd -qAt --command="
    SELECT count(*)
    FROM pg_catalog.pg_class AS index_class
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = index_class.relnamespace
    WHERE namespace.nspname = 'shop_private'
      AND index_class.relname = '${index_name}';
  "
)"
if [[ "$remaining" != 0 ]]; then
  printf 'invalid concurrent index remained after exact drop\n' >&2
  exit 1
fi

{
  printf 'status=ok\n'
  printf 'create_expected_exit=%s\n' "$create_exit"
  printf 'create_sqlstate=23505\n'
  printf 'invalid_index_observed=true\n'
  printf 'exact_drop=true\n'
  printf 'remaining_failed_indexes=%s\n' "$remaining"
} >"$evidence_dir/summary.txt"

cat "$evidence_dir/summary.txt"
