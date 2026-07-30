\set ON_ERROR_STOP on
\ir context.sql

DO $verify$
BEGIN
    IF (SELECT count(*) FROM shop.customer) <> 2
       OR (SELECT count(*) FROM shop.product) <> 3
       OR (SELECT count(*) FROM shop.sales_order) <> 2
       OR (SELECT count(*) FROM shop.sales_order_item) <> 3
       OR (SELECT count(*) FROM shop.payment) <> 2 THEN
        RAISE EXCEPTION 'unexpected ch03 sample row counts';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.sales_order AS o
        LEFT JOIN shop.customer AS c
          ON c.customer_id = o.customer_id
        WHERE c.customer_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM shop.sales_order_item AS i
        LEFT JOIN shop.sales_order AS o
          ON o.order_id = i.order_id
        LEFT JOIN shop.product AS p
          ON p.product_id = i.product_id
        WHERE o.order_id IS NULL OR p.product_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM shop.payment AS p
        LEFT JOIN shop.sales_order AS o
          ON o.order_id = p.order_id
        WHERE o.order_id IS NULL
    ) THEN
        RAISE EXCEPTION 'orphan row detected';
    END IF;

    IF (
        SELECT item_subtotal
        FROM shop_api.order_summary
        WHERE order_id = 1001
    ) <> 167.80 THEN
        RAISE EXCEPTION 'order 1001 subtotal drifted';
    END IF;

    IF (
        SELECT captured_amount
        FROM shop_api.order_summary
        WHERE order_id = 1001
    ) <> 167.80 THEN
        RAISE EXCEPTION 'order 1001 captured amount drifted';
    END IF;

    IF NOT has_table_privilege(
        'pg36_app', 'shop.sales_order', 'SELECT'
    ) OR NOT has_table_privilege(
        'pg36_app', 'shop.sales_order', 'INSERT'
    ) OR NOT has_table_privilege(
        'pg36_app', 'shop.sales_order', 'UPDATE'
    ) OR NOT has_table_privilege(
        'pg36_app', 'shop.sales_order', 'DELETE'
    ) OR NOT has_table_privilege(
        'pg36_ro',
        'shop.sales_order',
        'SELECT'
    ) OR has_table_privilege(
        'pg36_ro',
        'shop.sales_order',
        'UPDATE'
    ) OR NOT has_table_privilege(
        'pg36_ro',
        'shop_api.order_summary',
        'SELECT'
    ) OR has_schema_privilege(
        'pg36_app',
        'shop_private',
        'USAGE'
    ) THEN
        RAISE EXCEPTION 'role boundary drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = c.relnamespace
        WHERE (
                (
                    n.nspname = 'shop'
                    AND c.relname IN (
                        'customer',
                        'product',
                        'sales_order',
                        'sales_order_item',
                        'payment'
                    )
                )
                OR (
                    n.nspname = 'shop_api'
                    AND c.relname = 'order_summary'
                )
              )
          AND pg_catalog.pg_get_userbyid(c.relowner) <> 'pg36_owner'
    ) THEN
        RAISE EXCEPTION 'object owner drifted';
    END IF;
END
$verify$;

SELECT key || '=' || value AS state
FROM (
    SELECT 1, 'status', 'ok'
    UNION ALL
    SELECT 2, 'model_version', 'ch03-v0'
    UNION ALL
    SELECT 3, 'customer_count', count(*)::text
      FROM shop.customer
    UNION ALL
    SELECT 4, 'product_count', count(*)::text
      FROM shop.product
    UNION ALL
    SELECT 5, 'order_count', count(*)::text
      FROM shop.sales_order
    UNION ALL
    SELECT 6, 'item_count', count(*)::text
      FROM shop.sales_order_item
    UNION ALL
    SELECT 7, 'payment_count', count(*)::text
      FROM shop.payment
    UNION ALL
    SELECT 8, 'open_decision_count', '4'
    UNION ALL
    SELECT 9, 'relation_checksum',
           pg_catalog.md5(
               string_agg(
                   order_id || '|' || line_no || '|' ||
                   product_id || '|' || unit_price || '|' || quantity,
                   E'\n'
                   ORDER BY order_id, line_no
               )
           )
      FROM shop.sales_order_item
) AS snapshot(ord, key, value)
ORDER BY ord;
