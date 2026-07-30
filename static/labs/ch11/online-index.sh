#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

phase="${1:-}"
pg_service="${PGSERVICE:-pg36-admin}"
connection="service=${pg_service} application_name=pg36-ch11-index-${phase}"
index_name="ch11_order_shipping_missing_idx"

usage() {
  printf '%s\n' \
    "usage: $0 {build|drop}" \
    "requires PGSERVICEFILE and the expanded ch11 fixture"
}

case "$phase" in
  build|drop)
    ;;
  *)
    usage >&2
    exit 64
    ;;
esac

if [[ ! -f "${PGSERVICEFILE:-}" ]]; then
  usage >&2
  exit 64
fi

for command_name in psql; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 69
  fi
done

psql_cmd() {
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    "$@"
}

identity_ok="$(
  psql_cmd -qAt --command="
    SELECT current_database() = 'pg36_shop'
       AND NOT pg_catalog.pg_is_in_recovery()
       AND pg_catalog.obj_description(
               'shop_private.ch11_order'::regclass,
               'pg_class'
           ) =
           'pg36 ch11 deterministic release lab; safe to rebuild'
       AND EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute
           WHERE attrelid =
                 'shop_private.ch11_order'::regclass
             AND attname = 'shipping_code'
             AND attnum > 0
             AND NOT attisdropped
       );
  "
)"
if [[ "$identity_ok" != t ]]; then
  printf 'refusing index action: ch11 target identity mismatch\n' >&2
  exit 1
fi

if [[ "$phase" == build ]]; then
  existing="$(
    psql_cmd -qAt --command="
      SELECT count(*)
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
      WHERE namespace.nspname = 'shop_private'
        AND relation.relname = '${index_name}';
    "
  )"
  if [[ "$existing" != 0 ]]; then
    printf 'build refused: %s already exists\n' "$index_name" >&2
    exit 1
  fi

  psql_cmd \
    --command="SET ROLE pg36_owner" \
    --command="SET lock_timeout = '2s'" \
    --command="SET statement_timeout = '30s'" \
    --command="
    CREATE INDEX CONCURRENTLY ${index_name}
    ON shop_private.ch11_order (order_id)
    WHERE shipping_code IS NULL
  "

  valid="$(
    psql_cmd -qAt --command="
      SELECT index_catalog.indisvalid
         AND index_catalog.indisready
         AND pg_catalog.pg_get_expr(
                 index_catalog.indpred,
                 index_catalog.indrelid
             ) = '(shipping_code IS NULL)'
      FROM pg_catalog.pg_index AS index_catalog
      WHERE index_catalog.indexrelid =
            'shop_private.${index_name}'::regclass
        AND index_catalog.indrelid =
            'shop_private.ch11_order'::regclass;
    "
  )"
  if [[ "$valid" != t ]]; then
    printf 'concurrent build did not produce the expected valid index\n' >&2
    exit 1
  fi
  printf 'status=ok\nphase=build\nindex=%s\n' "$index_name"
else
  exact="$(
    psql_cmd -qAt --command="
      SELECT count(*) = 1
         AND bool_and(index_catalog.indisvalid)
         AND bool_and(
             pg_catalog.pg_get_expr(
                 index_catalog.indpred,
                 index_catalog.indrelid
             ) = '(shipping_code IS NULL)'
         )
      FROM pg_catalog.pg_index AS index_catalog
      WHERE index_catalog.indexrelid =
            pg_catalog.to_regclass(
                'shop_private.${index_name}'
            )
        AND index_catalog.indrelid =
            'shop_private.ch11_order'::regclass;
    "
  )"
  if [[ "$exact" != t ]]; then
    printf 'drop refused: exact ch11 partial index not found\n' >&2
    exit 1
  fi

  psql_cmd \
    --command="SET ROLE pg36_owner" \
    --command="SET lock_timeout = '2s'" \
    --command="SET statement_timeout = '30s'" \
    --command="
      DROP INDEX CONCURRENTLY shop_private.${index_name}
    "
  printf 'status=ok\nphase=drop\nindex=%s\n' "$index_name"
fi
