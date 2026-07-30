\set ON_ERROR_STOP on
\ir context.sql

BEGIN TRANSACTION READ ONLY;

SELECT
    pg_catalog.array_agg(
        a.attname::text
        ORDER BY a.attnum
    ) = ARRAY[
        'order_id',
        'order_no',
        'customer_id',
        'order_status',
        'currency_code',
        'placed_at',
        'paid_at',
        'cancelled_at',
        'item_count',
        'item_subtotal_minor',
        'captured_amount_minor'
    ]::text[] AS view_shape_ok
FROM pg_catalog.pg_attribute AS a
WHERE a.attrelid = 'shop_api.order_summary'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
\gset

\if :view_shape_ok
\else
  DO $query_contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0603',
          MESSAGE = 'shop_api.order_summary column contract drifted';
  END
  $query_contract_error$;
\endif

WITH page_1 AS MATERIALIZED (
    SELECT
        o.order_id,
        o.order_no,
        o.placed_at
    FROM shop.sales_order AS o
    WHERE o.placed_at IS NOT NULL
    ORDER BY o.placed_at DESC, o.order_id DESC
    LIMIT 1
),
page_2 AS (
    SELECT
        o.order_id,
        o.order_no,
        o.placed_at
    FROM shop.sales_order AS o
    CROSS JOIN page_1 AS cursor
    WHERE o.placed_at IS NOT NULL
      AND (o.placed_at, o.order_id)
          < (cursor.placed_at, cursor.order_id)
    ORDER BY o.placed_at DESC, o.order_id DESC
    LIMIT 1
)
SELECT
    p1.order_id::text AS page_1_order_id,
    p2.order_id::text AS page_2_order_id,
    p1.order_id <> p2.order_id AS pages_do_not_overlap,
    p1.placed_at > p2.placed_at
        OR (
            p1.placed_at = p2.placed_at
            AND p1.order_id > p2.order_id
        ) AS strict_cursor_order
FROM page_1 AS p1
CROSS JOIN page_2 AS p2
\gset

\if :pages_do_not_overlap
\else
  DO $query_contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0604',
          MESSAGE = 'keyset pages overlap';
  END
  $query_contract_error$;
\endif

\if :strict_cursor_order
\else
  DO $query_contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0604',
          MESSAGE = 'keyset cursor is not a strict total order';
  END
  $query_contract_error$;
\endif

SELECT
    count(*) = count(DISTINCT order_no)
        AS business_key_unique,
    count(*) = count(DISTINCT request_key)
        AS idempotency_key_unique
FROM shop.sales_order
\gset

\if :business_key_unique
\else
  DO $query_contract_error$
  BEGIN
      RAISE EXCEPTION 'order_no query contract drifted';
  END
  $query_contract_error$;
\endif

\if :idempotency_key_unique
\else
  DO $query_contract_error$
  BEGIN
      RAISE EXCEPTION 'request_key query contract drifted';
  END
  $query_contract_error$;
\endif

COMMIT;

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'query_contract=explicit-columns+stable-keyset';
SELECT 'view_column_count=11';
SELECT 'cursor_order=placed_at-desc,order_id-desc';
SELECT 'page_1_order_id=' || :'page_1_order_id';
SELECT 'page_2_order_id=' || :'page_2_order_id';
SELECT 'pages_do_not_overlap=' || :'pages_do_not_overlap';
SELECT 'business_key_unique=' || :'business_key_unique';
SELECT 'idempotency_key_unique=' || :'idempotency_key_unique';
