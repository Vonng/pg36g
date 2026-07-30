#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
phase="${1:-}"
pg_service="${PGSERVICE:-pg36-admin}"
connection="service=${pg_service} application_name=pg36-ch09-index-${phase}"

usage() {
  printf '%s\n' \
    "usage: $0 {primary|event-btree|drop-event-btree}" \
    "requires PGSERVICEFILE and a freshly rebuilt ch09 fixture"
}

case "$phase" in
  primary|event-btree|drop-event-btree)
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

psql_cmd() {
  psql -X -w \
    --dbname="$connection" \
    --set=ON_ERROR_STOP=1 \
    "$@"
}

verify_marker() {
  local relation="$1"
  local result
  result="$(
    psql_cmd -qAt --command="
      SELECT pg_catalog.obj_description(
                 '${relation}'::regclass,
                 'pg_class'
             ) =
             'pg36 ch09 deterministic index lab; safe to rebuild';
    "
  )"
  if [[ "$result" != t ]]; then
    printf 'refusing index action: marker mismatch for %s\n' \
      "$relation" >&2
    exit 1
  fi
}

case "$phase" in
  primary)
    verify_marker shop_private.ch09_order_probe
    verify_marker shop_private.ch09_inventory_probe
    verify_marker shop_private.ch09_search_probe
    verify_marker shop_private.ch09_event_probe

    psql_cmd --command="
      CREATE INDEX CONCURRENTLY ch09_order_placed_cover_idx
      ON shop_private.ch09_order_probe
          (customer_id, placed_at DESC)
      INCLUDE (order_no, amount_minor)
      WHERE order_status = 'placed';
    "
    psql_cmd --command="
      COMMENT ON INDEX shop_private.ch09_order_placed_cover_idx IS
      'pg36 ch09 retained order candidate';
    "

    psql_cmd --command="
      CREATE INDEX CONCURRENTLY ch09_inventory_sku_cover_idx
      ON shop_private.ch09_inventory_probe
          (sku_id, warehouse_id)
      INCLUDE (available, reserved, updated_at);
    "
    psql_cmd --command="
      COMMENT ON INDEX shop_private.ch09_inventory_sku_cover_idx IS
      'pg36 ch09 retained inventory candidate';
    "

    psql_cmd --command="
      CREATE INDEX CONCURRENTLY ch09_search_document_gin_idx
      ON shop_private.ch09_search_probe
      USING gin (search_document);
    "
    psql_cmd --command="
      COMMENT ON INDEX shop_private.ch09_search_document_gin_idx IS
      'pg36 ch09 retained search candidate';
    "

    psql_cmd --command="
      CREATE INDEX CONCURRENTLY ch09_event_occurred_brin_idx
      ON shop_private.ch09_event_probe
      USING brin (occurred_at)
      WITH (pages_per_range = 32, autosummarize = on);
    "
    psql_cmd --command="
      COMMENT ON INDEX shop_private.ch09_event_occurred_brin_idx IS
      'pg36 ch09 retained event candidate';
    "
    ;;
  event-btree)
    verify_marker shop_private.ch09_event_probe
    psql_cmd --command="
      CREATE INDEX CONCURRENTLY ch09_event_occurred_btree_idx
      ON shop_private.ch09_event_probe (occurred_at);
    "
    psql_cmd --command="
      COMMENT ON INDEX shop_private.ch09_event_occurred_btree_idx IS
      'pg36 ch09 rejected size comparison candidate';
    "
    ;;
  drop-event-btree)
    verify_marker shop_private.ch09_event_probe
    exact_match="$(
      psql_cmd -qAt --command="
        SELECT count(*) = 1
        FROM pg_catalog.pg_index AS i
        WHERE i.indexrelid =
              pg_catalog.to_regclass(
                  'shop_private.ch09_event_occurred_btree_idx'
              )
          AND i.indrelid =
              'shop_private.ch09_event_probe'::regclass;
      "
    )"
    if [[ "$exact_match" != t ]]; then
      printf 'refusing drop: rejected event B-tree identity mismatch\n' >&2
      exit 1
    fi
    psql_cmd --command="
      DROP INDEX CONCURRENTLY
          shop_private.ch09_event_occurred_btree_idx;
    "
    ;;
esac

printf 'status=ok phase=%s\n' "$phase"
