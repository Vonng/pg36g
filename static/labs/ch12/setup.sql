\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $active_guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name = 'pg36-ch12-api'
    ) THEN
        RAISE EXCEPTION
            'setup refused: pg36-ch12-api still has database sessions';
    END IF;
END
$active_guard$;

DO $collision_guard$
DECLARE
    schema_oid oid;
    unknown_relation text;
    unknown_function text;
    unknown_type text;
    expected_marker constant text :=
        'pg36 ch12 reference service lab; exact schema may be rebuilt';
BEGIN
    SELECT oid
    INTO schema_oid
    FROM pg_catalog.pg_namespace
    WHERE nspname = 'shop_ch12';

    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'setup refused: shop_ch12 lacks the exact lab marker';
    END IF;

    SELECT relation.relname
    INTO unknown_relation
    FROM pg_catalog.pg_class AS relation
    WHERE relation.relnamespace = schema_oid
      AND relation.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
      AND relation.relname <> ALL (ARRAY[
          'schema_version',
          'inventory',
          'sales_order',
          'sales_order_order_id_seq',
          'order_request',
          'sales_order_item',
          'payment',
          'payment_payment_id_seq',
          'payment_request',
          'outbox',
          'outbox_event_id_seq',
          'retry_fault_seq'
      ])
    ORDER BY relation.relname
    LIMIT 1;

    IF unknown_relation IS NOT NULL THEN
        RAISE EXCEPTION
            'setup refused: unknown relation in shop_ch12: %',
            unknown_relation;
    END IF;

    SELECT routine.oid::regprocedure::text
    INTO unknown_function
    FROM pg_catalog.pg_proc AS routine
    WHERE routine.pronamespace = schema_oid
      AND routine.oid IS DISTINCT FROM
          pg_catalog.to_regprocedure(
              'shop_ch12.raise_serialization_once()'
          )::oid
    ORDER BY routine.oid::regprocedure::text
    LIMIT 1;

    IF unknown_function IS NOT NULL THEN
        RAISE EXCEPTION
            'setup refused: unknown function in shop_ch12: %',
            unknown_function;
    END IF;

    SELECT type_catalog.typname
    INTO unknown_type
    FROM pg_catalog.pg_type AS type_catalog
    WHERE type_catalog.typnamespace = schema_oid
      AND type_catalog.typrelid = 0
      AND type_catalog.typelem = 0
    ORDER BY type_catalog.typname
    LIMIT 1;

    IF unknown_type IS NOT NULL THEN
        RAISE EXCEPTION
            'setup refused: unknown standalone type in shop_ch12: %',
            unknown_type;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND relation.relkind IN ('r', 'p', 'S')
          AND pg_catalog.obj_description(
                  relation.oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker
    ) THEN
        RAISE EXCEPTION
            'setup refused: a ch12 relation lacks the marker';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
          AND pg_catalog.obj_description(
                  routine.oid,
                  'pg_proc'
              ) IS DISTINCT FROM expected_marker
    ) THEN
        RAISE EXCEPTION
            'setup refused: a ch12 function lacks the marker';
    END IF;
END
$collision_guard$;

DROP FUNCTION IF EXISTS shop_ch12.raise_serialization_once();
DROP TABLE IF EXISTS shop_ch12.outbox;
DROP TABLE IF EXISTS shop_ch12.payment_request;
DROP TABLE IF EXISTS shop_ch12.payment;
DROP TABLE IF EXISTS shop_ch12.sales_order_item;
DROP TABLE IF EXISTS shop_ch12.order_request;
DROP TABLE IF EXISTS shop_ch12.sales_order;
DROP TABLE IF EXISTS shop_ch12.inventory;
DROP TABLE IF EXISTS shop_ch12.schema_version;
DROP SEQUENCE IF EXISTS shop_ch12.retry_fault_seq;
DROP SCHEMA IF EXISTS shop_ch12;
CREATE SCHEMA shop_ch12 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch12 IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';

SET search_path = pg_catalog, shop_ch12;

CREATE TABLE shop_ch12.schema_version (
    singleton boolean PRIMARY KEY DEFAULT true,
    version integer NOT NULL,
    contract text NOT NULL,
    installed_at timestamptz NOT NULL,
    CONSTRAINT ch12_schema_version_singleton_check
        CHECK (singleton),
    CONSTRAINT ch12_schema_version_exact_check
        CHECK (
            version = 1
            AND contract = 'pg36-ch12-service-contract-v1'
        )
);

CREATE TABLE shop_ch12.inventory (
    sku text PRIMARY KEY,
    available integer NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    unit_price_minor bigint NOT NULL,
    currency_code text NOT NULL DEFAULT 'CNY',
    CONSTRAINT ch12_inventory_sku_check
        CHECK (sku ~ '^[A-Z0-9][A-Z0-9._-]{2,31}$'),
    CONSTRAINT ch12_inventory_available_check
        CHECK (available >= 0),
    CONSTRAINT ch12_inventory_version_check
        CHECK (version >= 0),
    CONSTRAINT ch12_inventory_price_check
        CHECK (unit_price_minor > 0),
    CONSTRAINT ch12_inventory_currency_check
        CHECK (currency_code = 'CNY')
);

CREATE TABLE shop_ch12.sales_order (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY
        (START WITH 1200001)
        PRIMARY KEY,
    customer_ref text NOT NULL,
    state text NOT NULL,
    total_minor bigint NOT NULL,
    currency_code text NOT NULL,
    trace_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT ch12_sales_order_customer_check
        CHECK (customer_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'),
    CONSTRAINT ch12_sales_order_state_check
        CHECK (state IN ('placed', 'paid')),
    CONSTRAINT ch12_sales_order_total_check
        CHECK (total_minor > 0),
    CONSTRAINT ch12_sales_order_currency_check
        CHECK (currency_code = 'CNY'),
    CONSTRAINT ch12_sales_order_trace_check
        CHECK (trace_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
);

CREATE TABLE shop_ch12.order_request (
    request_key text PRIMARY KEY,
    fingerprint text NOT NULL,
    order_id bigint UNIQUE
        REFERENCES shop_ch12.sales_order(order_id),
    response jsonb,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT ch12_order_request_key_check
        CHECK (
            request_key ~
            '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
        ),
    CONSTRAINT ch12_order_request_fingerprint_check
        CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ch12_order_request_shape_check
        CHECK (
            (
                order_id IS NULL
                AND response IS NULL
            )
            OR
            (
                order_id IS NOT NULL
                AND response IS NOT NULL
                AND pg_catalog.jsonb_typeof(response) = 'object'
            )
        )
);

CREATE TABLE shop_ch12.sales_order_item (
    order_id bigint NOT NULL
        REFERENCES shop_ch12.sales_order(order_id),
    line_no smallint NOT NULL,
    sku text NOT NULL
        REFERENCES shop_ch12.inventory(sku),
    quantity integer NOT NULL,
    unit_price_minor bigint NOT NULL,
    line_total_minor bigint GENERATED ALWAYS AS
        (quantity::bigint * unit_price_minor) STORED,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT ch12_order_item_line_check
        CHECK (line_no > 0),
    CONSTRAINT ch12_order_item_quantity_check
        CHECK (quantity > 0),
    CONSTRAINT ch12_order_item_price_check
        CHECK (unit_price_minor > 0)
);

CREATE TABLE shop_ch12.payment (
    payment_id bigint GENERATED BY DEFAULT AS IDENTITY
        (START WITH 1200001)
        PRIMARY KEY,
    order_id bigint NOT NULL UNIQUE
        REFERENCES shop_ch12.sales_order(order_id),
    amount_minor bigint NOT NULL,
    currency_code text NOT NULL,
    state text NOT NULL,
    trace_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT ch12_payment_amount_check
        CHECK (amount_minor > 0),
    CONSTRAINT ch12_payment_currency_check
        CHECK (currency_code = 'CNY'),
    CONSTRAINT ch12_payment_state_check
        CHECK (state = 'captured'),
    CONSTRAINT ch12_payment_trace_check
        CHECK (trace_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
);

CREATE TABLE shop_ch12.payment_request (
    idempotency_key text PRIMARY KEY,
    fingerprint text NOT NULL,
    payment_id bigint UNIQUE
        REFERENCES shop_ch12.payment(payment_id),
    response jsonb,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT ch12_payment_request_key_check
        CHECK (
            idempotency_key ~
            '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
        ),
    CONSTRAINT ch12_payment_request_fingerprint_check
        CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ch12_payment_request_shape_check
        CHECK (
            (
                payment_id IS NULL
                AND response IS NULL
            )
            OR
            (
                payment_id IS NOT NULL
                AND response IS NOT NULL
                AND pg_catalog.jsonb_typeof(response) = 'object'
            )
        )
);

CREATE TABLE shop_ch12.outbox (
    event_id bigint GENERATED BY DEFAULT AS IDENTITY
        (START WITH 1200001)
        PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    aggregate_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    trace_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT ch12_outbox_event_key_check
        CHECK (
            event_key ~
            '^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$'
        ),
    CONSTRAINT ch12_outbox_aggregate_check
        CHECK (aggregate_type IN ('order', 'payment')),
    CONSTRAINT ch12_outbox_type_check
        CHECK (event_type IN ('order.placed', 'payment.captured')),
    CONSTRAINT ch12_outbox_payload_check
        CHECK (pg_catalog.jsonb_typeof(payload) = 'object'),
    CONSTRAINT ch12_outbox_trace_check
        CHECK (trace_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
);

CREATE SEQUENCE shop_ch12.retry_fault_seq;

CREATE FUNCTION shop_ch12.raise_serialization_once()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    attempt bigint;
BEGIN
    attempt := pg_catalog.nextval(
        'shop_ch12.retry_fault_seq'::regclass
    );
    IF attempt = 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = '40001',
            MESSAGE =
                'pg36 ch12 deterministic serialization injection';
    END IF;
END
$function$;

COMMENT ON TABLE shop_ch12.schema_version IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.inventory IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.sales_order IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.order_request IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.sales_order_item IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.payment IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.payment_request IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON TABLE shop_ch12.outbox IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON SEQUENCE shop_ch12.sales_order_order_id_seq IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON SEQUENCE shop_ch12.payment_payment_id_seq IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON SEQUENCE shop_ch12.outbox_event_id_seq IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON SEQUENCE shop_ch12.retry_fault_seq IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';
COMMENT ON FUNCTION shop_ch12.raise_serialization_once() IS
    'pg36 ch12 reference service lab; exact schema may be rebuilt';

INSERT INTO shop_ch12.schema_version (
    singleton,
    version,
    contract,
    installed_at
)
VALUES (
    true,
    1,
    'pg36-ch12-service-contract-v1',
    timestamptz '2025-01-01 00:00:00+00'
);

INSERT INTO shop_ch12.inventory (
    sku,
    available,
    version,
    unit_price_minor,
    currency_code
)
VALUES
    ('PG36-SKU-001', 10, 0, 12900, 'CNY'),
    ('PG36-SKU-002', 5, 0, 8900, 'CNY');

REVOKE ALL ON SCHEMA shop_ch12 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch12 TO pg36_app;

REVOKE ALL ON ALL TABLES IN SCHEMA shop_ch12 FROM PUBLIC;
GRANT SELECT ON shop_ch12.schema_version TO pg36_app;
GRANT SELECT, UPDATE ON shop_ch12.inventory TO pg36_app;
GRANT SELECT, INSERT, UPDATE
    ON shop_ch12.sales_order, shop_ch12.order_request
    TO pg36_app;
GRANT SELECT, INSERT
    ON shop_ch12.sales_order_item
    TO pg36_app;
GRANT SELECT, INSERT ON shop_ch12.payment TO pg36_app;
GRANT SELECT, INSERT, UPDATE
    ON shop_ch12.payment_request
    TO pg36_app;
GRANT INSERT ON shop_ch12.outbox TO pg36_app;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA shop_ch12 FROM PUBLIC;
GRANT USAGE
    ON SEQUENCE shop_ch12.sales_order_order_id_seq,
                    shop_ch12.payment_payment_id_seq,
                    shop_ch12.outbox_event_id_seq
    TO pg36_app;

REVOKE ALL ON FUNCTION
    shop_ch12.raise_serialization_once()
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
    shop_ch12.raise_serialization_once()
    TO pg36_app;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=pg36-ch12-service-contract-v1';
SELECT 'schema_owner=' ||
       pg_catalog.pg_get_userbyid(namespace.nspowner)
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname = 'shop_ch12';
SELECT 'inventory_rows=' || count(*)
FROM shop_ch12.inventory;
SELECT 'orders=' || count(*)
FROM shop_ch12.sales_order;
SELECT 'app_can_create_schema=' ||
       pg_catalog.has_schema_privilege(
           'pg36_app',
           'shop_ch12',
           'CREATE'
       );
