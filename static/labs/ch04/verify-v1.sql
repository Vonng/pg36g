\set ON_ERROR_STOP on
\ir context.sql

SET TimeZone = 'UTC';

DO $verify$
DECLARE
    shape_drift text;
    missing_constraint text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) THEN
        RAISE EXCEPTION 'ch04 schema version marker is missing';
    END IF;

    IF (SELECT count(*) FROM shop.customer) <> 2
       OR (SELECT count(*) FROM shop.product) <> 3
       OR (SELECT count(*) FROM shop.sales_order) <> 2
       OR (SELECT count(*) FROM shop.sales_order_item) <> 3
       OR (SELECT count(*) FROM shop.payment) <> 2 THEN
        RAISE EXCEPTION 'unexpected ch04 sample row counts';
    END IF;

    WITH expected(
        table_name,
        column_name,
        data_type,
        is_not_null,
        identity_kind,
        generated_kind
    ) AS (
        VALUES
          ('customer', 'customer_id', 'bigint', true, 'd', ''),
          ('customer', 'customer_ref', 'text', true, '', ''),
          ('customer', 'email', 'text', true, '', ''),
          ('customer', 'display_name', 'text', true, '', ''),
          ('customer', 'created_at',
           'timestamp(3) with time zone', true, '', ''),
          ('product', 'product_id', 'bigint', true, 'd', ''),
          ('product', 'sku', 'text', true, '', ''),
          ('product', 'product_name', 'text', true, '', ''),
          ('product', 'active', 'boolean', true, '', ''),
          ('product', 'created_at',
           'timestamp(3) with time zone', true, '', ''),
          ('product', 'currency_code', 'text', true, '', ''),
          ('product', 'current_unit_price_minor',
           'bigint', true, '', ''),
          ('sales_order', 'order_id', 'bigint', true, 'd', ''),
          ('sales_order', 'order_no', 'text', true, '', ''),
          ('sales_order', 'customer_id', 'bigint', true, '', ''),
          ('sales_order', 'request_key', 'text', true, '', ''),
          ('sales_order', 'request_fingerprint', 'text', true, '', ''),
          ('sales_order', 'buyer_email', 'text', true, '', ''),
          ('sales_order', 'order_status', 'text', true, '', ''),
          ('sales_order', 'placed_at',
           'timestamp(3) with time zone', false, '', ''),
          ('sales_order', 'created_by_trace_id',
           'text', true, '', ''),
          ('sales_order', 'currency_code', 'text', true, '', ''),
          ('sales_order', 'paid_at',
           'timestamp(3) with time zone', false, '', ''),
          ('sales_order', 'cancelled_at',
           'timestamp(3) with time zone', false, '', ''),
          ('sales_order_item', 'order_id', 'bigint', true, '', ''),
          ('sales_order_item', 'line_no', 'integer', true, '', ''),
          ('sales_order_item', 'product_id', 'bigint', true, '', ''),
          ('sales_order_item', 'sku_snapshot', 'text', true, '', ''),
          ('sales_order_item', 'product_name_snapshot',
           'text', true, '', ''),
          ('sales_order_item', 'quantity', 'integer', true, '', ''),
          ('sales_order_item', 'currency_code', 'text', true, '', ''),
          ('sales_order_item', 'unit_price_minor',
           'bigint', true, '', ''),
          ('sales_order_item', 'line_total_minor',
           'bigint', false, '', 's'),
          ('payment', 'payment_id', 'bigint', true, 'd', ''),
          ('payment', 'order_id', 'bigint', true, '', ''),
          ('payment', 'provider', 'text', true, '', ''),
          ('payment', 'provider_payment_ref', 'text', true, '', ''),
          ('payment', 'idempotency_key', 'text', true, '', ''),
          ('payment', 'request_fingerprint', 'text', true, '', ''),
          ('payment', 'payment_status', 'text', true, '', ''),
          ('payment', 'occurred_at',
           'timestamp(3) with time zone', true, '', ''),
          ('payment', 'trace_id', 'text', true, '', ''),
          ('payment', 'currency_code', 'text', true, '', ''),
          ('payment', 'amount_minor', 'bigint', true, '', ''),
          ('payment', 'failure_code', 'text', false, '', '')
    ),
    actual AS (
        SELECT
            c.relname::text AS table_name,
            a.attname::text AS column_name,
            pg_catalog.format_type(
                a.atttypid,
                a.atttypmod
            ) AS data_type,
            a.attnotnull AS is_not_null,
            a.attidentity::text AS identity_kind,
            a.attgenerated::text AS generated_kind
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_attribute AS a
          ON a.attrelid = c.oid
        WHERE n.nspname = 'shop'
          AND c.relname IN (
              'customer',
              'product',
              'sales_order',
              'sales_order_item',
              'payment'
          )
          AND c.relkind = 'r'
          AND a.attnum > 0
          AND NOT a.attisdropped
    )
    SELECT string_agg(
               CASE
                   WHEN e.column_name IS NULL
                   THEN 'unexpected:' ||
                        a.table_name || '.' || a.column_name
                   WHEN a.column_name IS NULL
                   THEN 'missing-or-different:' ||
                        e.table_name || '.' || e.column_name
               END,
               ', '
               ORDER BY
                   COALESCE(e.table_name, a.table_name),
                   COALESCE(e.column_name, a.column_name)
           )
      INTO shape_drift
      FROM expected AS e
      FULL JOIN actual AS a
        USING (
            table_name,
            column_name,
            data_type,
            is_not_null,
            identity_kind,
            generated_kind
        )
     WHERE e.column_name IS NULL
        OR a.column_name IS NULL;

    IF shape_drift IS NOT NULL THEN
        RAISE EXCEPTION 'ch04 column shape drift: %', shape_drift;
    END IF;

    WITH expected(
        schema_name,
        table_name,
        constraint_name,
        constraint_type
    ) AS (
        VALUES
          ('shop', 'customer', 'customer_pkey', 'p'),
          ('shop', 'customer',
           'customer_customer_ref_key', 'u'),
          ('shop', 'customer', 'customer_email_key', 'u'),
          ('shop', 'customer', 'customer_email_canonical', 'c'),
          ('shop', 'product', 'product_pkey', 'p'),
          ('shop', 'product', 'product_sku_key', 'u'),
          ('shop', 'product',
           'product_currency_supported', 'c'),
          ('shop', 'product',
           'product_price_minor_bounds', 'c'),
          ('shop', 'sales_order', 'sales_order_pkey', 'p'),
          ('shop', 'sales_order',
           'sales_order_order_no_key', 'u'),
          ('shop', 'sales_order',
           'sales_order_request_key', 'u'),
          ('shop', 'sales_order',
           'sales_order_customer_fkey', 'f'),
          ('shop', 'sales_order',
           'sales_order_order_currency_key', 'u'),
          ('shop', 'sales_order',
           'sales_order_status_fkey', 'f'),
          ('shop', 'sales_order',
           'sales_order_state_time_consistent', 'c'),
          ('shop', 'sales_order_item',
           'sales_order_item_pkey', 'p'),
          ('shop', 'sales_order_item',
           'sales_order_item_order_fkey', 'f'),
          ('shop', 'sales_order_item',
           'sales_order_item_product_fkey', 'f'),
          ('shop', 'sales_order_item',
           'sales_order_item_price_minor_bounds', 'c'),
          ('shop', 'sales_order_item',
           'sales_order_item_quantity_bounds', 'c'),
          ('shop', 'sales_order_item',
           'sales_order_item_line_total_bounds', 'c'),
          ('shop', 'payment', 'payment_pkey', 'p'),
          ('shop', 'payment',
           'payment_provider_ref_key', 'u'),
          ('shop', 'payment',
           'payment_idempotency_key', 'u'),
          ('shop', 'payment', 'payment_order_fkey', 'f'),
          ('shop', 'payment', 'payment_status_fkey', 'f'),
          ('shop', 'payment',
           'payment_amount_minor_bounds', 'c'),
          ('shop', 'payment',
           'payment_failure_semantics', 'c'),
          ('shop_private', 'order_status_catalog',
           'order_status_catalog_pkey', 'p'),
          ('shop_private', 'order_status_transition',
           'order_status_transition_pkey', 'p'),
          ('shop_private', 'order_status_transition',
           'order_status_transition_from_fkey', 'f'),
          ('shop_private', 'order_status_transition',
           'order_status_transition_to_fkey', 'f'),
          ('shop_private', 'payment_status_catalog',
           'payment_status_catalog_pkey', 'p'),
          ('shop_private', 'payment_status_transition',
           'payment_status_transition_pkey', 'p'),
          ('shop_private', 'payment_status_transition',
           'payment_status_transition_from_fkey', 'f'),
          ('shop_private', 'payment_status_transition',
           'payment_status_transition_to_fkey', 'f'),
          ('shop_private', 'schema_version',
           'schema_version_pkey', 'p')
    )
    SELECT string_agg(
               e.constraint_name,
               ', '
               ORDER BY e.constraint_name
           )
      INTO missing_constraint
      FROM expected AS e
     WHERE NOT EXISTS (
         SELECT 1
         FROM pg_catalog.pg_constraint AS c
         JOIN pg_catalog.pg_class AS r
           ON r.oid = c.conrelid
         JOIN pg_catalog.pg_namespace AS n
           ON n.oid = r.relnamespace
         WHERE n.nspname = e.schema_name
           AND r.relname = e.table_name
           AND c.conname = e.constraint_name
           AND c.contype = e.constraint_type::"char"
           AND c.convalidated
     );

    IF missing_constraint IS NOT NULL THEN
        RAISE EXCEPTION
            'missing or invalid ch04 constraints: %',
            missing_constraint;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.sales_order_item
        WHERE line_total_minor
              <> unit_price_minor * quantity::bigint
           OR currency_code <> 'CNY'
    ) OR EXISTS (
        SELECT 1
        FROM shop.payment
        WHERE currency_code <> 'CNY'
    ) OR EXISTS (
        SELECT 1
        FROM shop.product
        WHERE currency_code <> 'CNY'
    ) THEN
        RAISE EXCEPTION 'money-unit invariant drifted';
    END IF;

    IF (
        SELECT item_subtotal_minor
        FROM shop_api.order_summary
        WHERE order_id = 1001
    ) <> 16780 OR (
        SELECT captured_amount_minor
        FROM shop_api.order_summary
        WHERE order_id = 1001
    ) <> 16780 THEN
        RAISE EXCEPTION 'order 1001 exact totals drifted';
    END IF;

    IF (SELECT count(*) FROM shop_private.order_status_catalog) <> 4
       OR (
           SELECT count(*)
           FROM shop_private.order_status_transition
       ) <> 4
       OR (
           SELECT count(*)
           FROM shop_private.payment_status_catalog
       ) <> 3
       OR (
           SELECT count(*)
           FROM shop_private.payment_status_transition
       ) <> 2 THEN
        RAISE EXCEPTION 'state catalog or transition graph drifted';
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
         AND o.currency_code = i.currency_code
        LEFT JOIN shop.product AS p
          ON p.product_id = i.product_id
        WHERE o.order_id IS NULL OR p.product_id IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM shop.payment AS p
        LEFT JOIN shop.sales_order AS o
          ON o.order_id = p.order_id
         AND o.currency_code = p.currency_code
        WHERE o.order_id IS NULL
    ) THEN
        RAISE EXCEPTION 'orphan or cross-currency row detected';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_catalog.pg_trigger AS t
        JOIN pg_catalog.pg_class AS c
          ON c.oid = t.tgrelid
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = c.relnamespace
        WHERE n.nspname = 'shop'
          AND c.relname IN ('sales_order', 'payment')
          AND t.tgname IN (
              'sales_order_status_transition_guard',
              'payment_status_transition_guard'
          )
          AND NOT t.tgisinternal
          AND t.tgenabled = 'O'
    ) <> 2 THEN
        RAISE EXCEPTION 'status transition trigger drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = p.pronamespace
        WHERE n.nspname = 'shop_private'
          AND p.proname IN (
              'enforce_order_status_transition',
              'enforce_payment_status_transition'
          )
          AND (
              NOT p.prosecdef
              OR NOT COALESCE(
                  'search_path=pg_catalog, shop_private'
                  = ANY (p.proconfig),
                  false
              )
              OR pg_catalog.pg_get_userbyid(p.proowner)
                 <> 'pg36_owner'
              OR has_function_privilege(
                  'pg36_app',
                  p.oid,
                  'EXECUTE'
              )
          )
    ) OR (
        SELECT count(*)
        FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = p.pronamespace
        WHERE n.nspname = 'shop_private'
          AND p.proname IN (
              'enforce_order_status_transition',
              'enforce_payment_status_transition'
          )
    ) <> 2 THEN
        RAISE EXCEPTION
            'SECURITY DEFINER transition function drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_partitioned_table AS pt
        WHERE pt.partrelid IN (
            'shop.customer'::regclass,
            'shop.product'::regclass,
            'shop.sales_order'::regclass,
            'shop.sales_order_item'::regclass,
            'shop.payment'::regclass
        )
    ) THEN
        RAISE EXCEPTION 'ADR says v1 is not partitioned';
    END IF;

    IF NOT has_table_privilege(
        'pg36_app',
        'shop.sales_order',
        'SELECT,INSERT,UPDATE,DELETE'
    ) OR NOT has_sequence_privilege(
        'pg36_app',
        pg_catalog.pg_get_serial_sequence(
            'shop.sales_order',
            'order_id'
        ),
        'USAGE'
    ) OR NOT has_table_privilege(
        'pg36_ro',
        'shop_api.order_summary',
        'SELECT'
    ) OR has_table_privilege(
        'pg36_ro',
        'shop.sales_order',
        'UPDATE'
    ) OR has_schema_privilege(
        'pg36_app',
        'shop_private',
        'USAGE'
    ) THEN
        RAISE EXCEPTION 'role or sequence privilege drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = c.relnamespace
        WHERE n.nspname IN ('shop', 'shop_api', 'shop_private')
          AND c.relname IN (
              'customer',
              'product',
              'sales_order',
              'sales_order_item',
              'payment',
              'order_summary',
              'schema_version',
              'order_status_catalog',
              'order_status_transition',
              'payment_status_catalog',
              'payment_status_transition'
          )
          AND pg_catalog.pg_get_userbyid(c.relowner)
              <> 'pg36_owner'
    ) THEN
        RAISE EXCEPTION 'one or more ch04 objects have the wrong owner';
    END IF;
END
$verify$;

\echo '--- verify:state ---'

SELECT key || '=' || value AS state
FROM (
    SELECT 1, 'status', 'ok'
    UNION ALL
    SELECT 2, 'model_version', 'ch04-v1'
    UNION ALL
    SELECT 3, 'money_unit', 'CNY-fen'
    UNION ALL
    SELECT 4, 'session_timezone', current_setting('TimeZone')
    UNION ALL
    SELECT 5, 'customer_count', count(*)::text
      FROM shop.customer
    UNION ALL
    SELECT 6, 'product_count', count(*)::text
      FROM shop.product
    UNION ALL
    SELECT 7, 'order_count', count(*)::text
      FROM shop.sales_order
    UNION ALL
    SELECT 8, 'item_count', count(*)::text
      FROM shop.sales_order_item
    UNION ALL
    SELECT 9, 'payment_count', count(*)::text
      FROM shop.payment
    UNION ALL
    SELECT 10, 'order_transition_count', count(*)::text
      FROM shop_private.order_status_transition
    UNION ALL
    SELECT 11, 'partition_decision', 'not-now'
    UNION ALL
    SELECT 12, 'relation_checksum',
           pg_catalog.md5(
               string_agg(
                   order_id || '|' || line_no || '|' ||
                   product_id || '|' || currency_code || '|' ||
                   unit_price_minor || '|' || quantity || '|' ||
                   line_total_minor,
                   E'\n'
                   ORDER BY order_id, line_no
               )
           )
      FROM shop.sales_order_item
) AS snapshot(ord, key, value)
ORDER BY ord;
