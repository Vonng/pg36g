\set ON_ERROR_STOP on
\ir context.sql

BEGIN;

CREATE SCHEMA IF NOT EXISTS shop_api AUTHORIZATION pg36_owner;
ALTER SCHEMA shop_api OWNER TO pg36_owner;

CREATE SCHEMA IF NOT EXISTS shop_private AUTHORIZATION pg36_owner;
ALTER SCHEMA shop_private OWNER TO pg36_owner;

REVOKE ALL ON SCHEMA shop_api FROM PUBLIC;
REVOKE ALL ON SCHEMA shop_private FROM PUBLIC, pg36_app, pg36_ro;
GRANT USAGE ON SCHEMA shop_api TO pg36_app, pg36_ro;

CREATE TABLE IF NOT EXISTS shop.customer (
    customer_id   bigint,
    customer_ref  text NOT NULL,
    email         text NOT NULL,
    display_name  text NOT NULL,
    created_at    timestamptz NOT NULL,
    CONSTRAINT customer_pkey PRIMARY KEY (customer_id),
    CONSTRAINT customer_customer_ref_key UNIQUE (customer_ref),
    CONSTRAINT customer_email_key UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS shop.product (
    product_id          bigint,
    sku                 text NOT NULL,
    product_name        text NOT NULL,
    current_unit_price  numeric NOT NULL,
    active              boolean NOT NULL,
    created_at          timestamptz NOT NULL,
    CONSTRAINT product_pkey PRIMARY KEY (product_id),
    CONSTRAINT product_sku_key UNIQUE (sku),
    CONSTRAINT product_price_nonnegative
        CHECK (current_unit_price >= 0)
);

CREATE TABLE IF NOT EXISTS shop.sales_order (
    order_id               bigint,
    order_no               text NOT NULL,
    customer_id            bigint NOT NULL,
    request_key            text NOT NULL,
    request_fingerprint    text NOT NULL,
    buyer_email            text NOT NULL,
    order_status           text NOT NULL,
    placed_at              timestamptz NOT NULL,
    created_by_trace_id    text NOT NULL,
    CONSTRAINT sales_order_pkey PRIMARY KEY (order_id),
    CONSTRAINT sales_order_order_no_key UNIQUE (order_no),
    CONSTRAINT sales_order_request_key
        UNIQUE (customer_id, request_key),
    CONSTRAINT sales_order_customer_fkey
        FOREIGN KEY (customer_id)
        REFERENCES shop.customer (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS shop.sales_order_item (
    order_id               bigint,
    line_no                integer,
    product_id             bigint NOT NULL,
    sku_snapshot           text NOT NULL,
    product_name_snapshot  text NOT NULL,
    unit_price             numeric NOT NULL,
    quantity               integer NOT NULL,
    CONSTRAINT sales_order_item_pkey
        PRIMARY KEY (order_id, line_no),
    CONSTRAINT sales_order_item_order_fkey
        FOREIGN KEY (order_id)
        REFERENCES shop.sales_order (order_id)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,
    CONSTRAINT sales_order_item_product_fkey
        FOREIGN KEY (product_id)
        REFERENCES shop.product (product_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT sales_order_item_line_positive CHECK (line_no > 0),
    CONSTRAINT sales_order_item_price_nonnegative CHECK (unit_price >= 0),
    CONSTRAINT sales_order_item_quantity_positive CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS shop.payment (
    payment_id             bigint,
    order_id               bigint NOT NULL,
    provider               text NOT NULL,
    provider_payment_ref   text NOT NULL,
    idempotency_key        text NOT NULL,
    request_fingerprint    text NOT NULL,
    payment_status         text NOT NULL,
    amount                 numeric NOT NULL,
    occurred_at            timestamptz NOT NULL,
    trace_id               text NOT NULL,
    CONSTRAINT payment_pkey PRIMARY KEY (payment_id),
    CONSTRAINT payment_provider_ref_key
        UNIQUE (provider, provider_payment_ref),
    CONSTRAINT payment_idempotency_key
        UNIQUE (provider, idempotency_key),
    CONSTRAINT payment_order_fkey
        FOREIGN KEY (order_id)
        REFERENCES shop.sales_order (order_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT payment_amount_positive CHECK (amount > 0)
);

DO $shape_guard$
DECLARE
    missing_columns text;
    unexpected_columns text;
    missing_constraints text;
    unexpected_constraints text;
BEGIN
    WITH expected(table_name, column_name, data_type, is_not_null) AS (
        VALUES
          ('customer', 'customer_id', 'bigint', true),
          ('customer', 'customer_ref', 'text', true),
          ('customer', 'email', 'text', true),
          ('customer', 'display_name', 'text', true),
          ('customer', 'created_at', 'timestamp with time zone', true),
          ('product', 'product_id', 'bigint', true),
          ('product', 'sku', 'text', true),
          ('product', 'product_name', 'text', true),
          ('product', 'current_unit_price', 'numeric', true),
          ('product', 'active', 'boolean', true),
          ('product', 'created_at', 'timestamp with time zone', true),
          ('sales_order', 'order_id', 'bigint', true),
          ('sales_order', 'order_no', 'text', true),
          ('sales_order', 'customer_id', 'bigint', true),
          ('sales_order', 'request_key', 'text', true),
          ('sales_order', 'request_fingerprint', 'text', true),
          ('sales_order', 'buyer_email', 'text', true),
          ('sales_order', 'order_status', 'text', true),
          ('sales_order', 'placed_at', 'timestamp with time zone', true),
          ('sales_order', 'created_by_trace_id', 'text', true),
          ('sales_order_item', 'order_id', 'bigint', true),
          ('sales_order_item', 'line_no', 'integer', true),
          ('sales_order_item', 'product_id', 'bigint', true),
          ('sales_order_item', 'sku_snapshot', 'text', true),
          ('sales_order_item', 'product_name_snapshot', 'text', true),
          ('sales_order_item', 'unit_price', 'numeric', true),
          ('sales_order_item', 'quantity', 'integer', true),
          ('payment', 'payment_id', 'bigint', true),
          ('payment', 'order_id', 'bigint', true),
          ('payment', 'provider', 'text', true),
          ('payment', 'provider_payment_ref', 'text', true),
          ('payment', 'idempotency_key', 'text', true),
          ('payment', 'request_fingerprint', 'text', true),
          ('payment', 'payment_status', 'text', true),
          ('payment', 'amount', 'numeric', true),
          ('payment', 'occurred_at', 'timestamp with time zone', true),
          ('payment', 'trace_id', 'text', true)
    ),
    actual AS (
        SELECT
            c.relname::text AS table_name,
            a.attname::text AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
            a.attnotnull AS is_not_null
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
               e.table_name || '.' || e.column_name,
               ', '
               ORDER BY e.table_name, e.column_name
           )
      INTO missing_columns
      FROM expected AS e
      LEFT JOIN actual AS a
        USING (table_name, column_name, data_type, is_not_null)
     WHERE a.column_name IS NULL;

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION 'logical model column drift: %', missing_columns;
    END IF;

    WITH expected(table_name, column_name) AS (
        VALUES
          ('customer', 'customer_id'),
          ('customer', 'customer_ref'),
          ('customer', 'email'),
          ('customer', 'display_name'),
          ('customer', 'created_at'),
          ('product', 'product_id'),
          ('product', 'sku'),
          ('product', 'product_name'),
          ('product', 'current_unit_price'),
          ('product', 'active'),
          ('product', 'created_at'),
          ('sales_order', 'order_id'),
          ('sales_order', 'order_no'),
          ('sales_order', 'customer_id'),
          ('sales_order', 'request_key'),
          ('sales_order', 'request_fingerprint'),
          ('sales_order', 'buyer_email'),
          ('sales_order', 'order_status'),
          ('sales_order', 'placed_at'),
          ('sales_order', 'created_by_trace_id'),
          ('sales_order_item', 'order_id'),
          ('sales_order_item', 'line_no'),
          ('sales_order_item', 'product_id'),
          ('sales_order_item', 'sku_snapshot'),
          ('sales_order_item', 'product_name_snapshot'),
          ('sales_order_item', 'unit_price'),
          ('sales_order_item', 'quantity'),
          ('payment', 'payment_id'),
          ('payment', 'order_id'),
          ('payment', 'provider'),
          ('payment', 'provider_payment_ref'),
          ('payment', 'idempotency_key'),
          ('payment', 'request_fingerprint'),
          ('payment', 'payment_status'),
          ('payment', 'amount'),
          ('payment', 'occurred_at'),
          ('payment', 'trace_id')
    )
    SELECT string_agg(
               c.relname || '.' || a.attname,
               ', '
               ORDER BY c.relname, a.attname
           )
      INTO unexpected_columns
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
       AND NOT EXISTS (
           SELECT 1
           FROM expected AS e
           WHERE e.table_name = c.relname
             AND e.column_name = a.attname
       );

    IF unexpected_columns IS NOT NULL THEN
        RAISE EXCEPTION
            'logical model has unexpected columns: %',
            unexpected_columns;
    END IF;

    WITH expected(constraint_name, constraint_type) AS (
        VALUES
          ('customer_pkey', 'p'),
          ('customer_customer_ref_key', 'u'),
          ('customer_email_key', 'u'),
          ('product_pkey', 'p'),
          ('product_sku_key', 'u'),
          ('product_price_nonnegative', 'c'),
          ('sales_order_pkey', 'p'),
          ('sales_order_order_no_key', 'u'),
          ('sales_order_request_key', 'u'),
          ('sales_order_customer_fkey', 'f'),
          ('sales_order_item_pkey', 'p'),
          ('sales_order_item_order_fkey', 'f'),
          ('sales_order_item_product_fkey', 'f'),
          ('sales_order_item_line_positive', 'c'),
          ('sales_order_item_price_nonnegative', 'c'),
          ('sales_order_item_quantity_positive', 'c'),
          ('payment_pkey', 'p'),
          ('payment_provider_ref_key', 'u'),
          ('payment_idempotency_key', 'u'),
          ('payment_order_fkey', 'f'),
          ('payment_amount_positive', 'c')
    )
    SELECT string_agg(
               e.constraint_name,
               ', '
               ORDER BY e.constraint_name
           )
      INTO missing_constraints
      FROM expected AS e
     WHERE NOT EXISTS (
         SELECT 1
         FROM pg_catalog.pg_constraint AS c
         JOIN pg_catalog.pg_namespace AS n
           ON n.oid = c.connamespace
         WHERE n.nspname = 'shop'
           AND c.conname = e.constraint_name
           AND c.contype = e.constraint_type::"char"
           AND c.convalidated
     );

    IF missing_constraints IS NOT NULL THEN
        RAISE EXCEPTION
            'logical model constraint drift: %',
            missing_constraints;
    END IF;

    WITH expected(constraint_name) AS (
        VALUES
          ('customer_pkey'),
          ('customer_customer_ref_key'),
          ('customer_email_key'),
          ('product_pkey'),
          ('product_sku_key'),
          ('product_price_nonnegative'),
          ('sales_order_pkey'),
          ('sales_order_order_no_key'),
          ('sales_order_request_key'),
          ('sales_order_customer_fkey'),
          ('sales_order_item_pkey'),
          ('sales_order_item_order_fkey'),
          ('sales_order_item_product_fkey'),
          ('sales_order_item_line_positive'),
          ('sales_order_item_price_nonnegative'),
          ('sales_order_item_quantity_positive'),
          ('payment_pkey'),
          ('payment_provider_ref_key'),
          ('payment_idempotency_key'),
          ('payment_order_fkey'),
          ('payment_amount_positive')
    )
    SELECT string_agg(c.conname, ', ' ORDER BY c.conname)
      INTO unexpected_constraints
      FROM pg_catalog.pg_constraint AS c
      JOIN pg_catalog.pg_class AS r
        ON r.oid = c.conrelid
      JOIN pg_catalog.pg_namespace AS n
        ON n.oid = r.relnamespace
     WHERE n.nspname = 'shop'
       AND r.relname IN (
           'customer',
           'product',
           'sales_order',
           'sales_order_item',
           'payment'
       )
       AND c.contype IN ('p', 'u', 'f', 'c')
       AND NOT EXISTS (
           SELECT 1
           FROM expected AS e
           WHERE e.constraint_name = c.conname
       );

    IF unexpected_constraints IS NOT NULL THEN
        RAISE EXCEPTION
            'logical model has unexpected constraints: %',
            unexpected_constraints;
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
              'order_summary'
          )
          AND pg_catalog.pg_get_userbyid(c.relowner) <> 'pg36_owner'
    ) THEN
        RAISE EXCEPTION 'one or more ch03 objects have the wrong owner';
    END IF;
END
$shape_guard$;

CREATE OR REPLACE VIEW shop_api.order_summary
AS
SELECT
    o.order_id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.placed_at,
    count(i.line_no) AS item_count,
    COALESCE(sum(i.unit_price * i.quantity), 0::numeric) AS item_subtotal,
    COALESCE(
        (
            SELECT sum(p.amount)
            FROM shop.payment AS p
            WHERE p.order_id = o.order_id
              AND p.payment_status = 'captured'
        ),
        0::numeric
    ) AS captured_amount
FROM shop.sales_order AS o
LEFT JOIN shop.sales_order_item AS i
  ON i.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.placed_at;

COMMENT ON SCHEMA shop IS
    'Canonical pg36_shop business relations';
COMMENT ON SCHEMA shop_api IS
    'Explicit query interface; not an automatic security boundary';
COMMENT ON SCHEMA shop_private IS
    'Owner-only internal namespace for future implementation objects';
COMMENT ON TABLE shop.sales_order_item IS
    'Line facts plus purchase-time product snapshots; ch03 logical model v0';
COMMENT ON VIEW shop_api.order_summary IS
    'Derived query model for teaching; money and status semantics close in ch04';

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE
    shop.customer,
    shop.product,
    shop.sales_order,
    shop.sales_order_item,
    shop.payment
TO pg36_app;

GRANT SELECT
ON TABLE
    shop.customer,
    shop.product,
    shop.sales_order,
    shop.sales_order_item,
    shop.payment
TO pg36_ro;

GRANT SELECT ON shop_api.order_summary TO pg36_app, pg36_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop_api
GRANT SELECT ON TABLES TO pg36_app, pg36_ro;

COMMIT;

\echo '[setup] ch03 logical model v0 is ready'
