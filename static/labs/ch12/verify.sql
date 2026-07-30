\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET search_path = pg_catalog, shop_ch12;

DO $verify$
DECLARE
    expected_marker constant text :=
        'pg36 ch12 reference service lab; exact schema may be rebuilt';
    relation_name text;
BEGIN
    IF (
        SELECT pg_catalog.obj_description(
                   namespace.oid,
                   'pg_namespace'
               )
        FROM pg_catalog.pg_namespace AS namespace
        WHERE namespace.nspname = 'shop_ch12'
    ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION 'shop_ch12 marker drifted';
    END IF;

    FOREACH relation_name IN ARRAY ARRAY[
        'schema_version',
        'inventory',
        'sales_order',
        'order_request',
        'sales_order_item',
        'payment',
        'payment_request',
        'outbox'
    ]
    LOOP
        IF pg_catalog.obj_description(
               pg_catalog.to_regclass(
                   'shop_ch12.' || relation_name
               )::oid,
               'pg_class'
           ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'ch12 relation marker drifted: %',
                relation_name;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM shop_ch12.schema_version
        WHERE singleton
          AND version = 1
          AND contract = 'pg36-ch12-service-contract-v1'
    ) THEN
        RAISE EXCEPTION 'ch12 schema contract drifted';
    END IF;

    IF pg_catalog.has_schema_privilege(
           'pg36_app',
           'shop_ch12',
           'CREATE'
       ) THEN
        RAISE EXCEPTION 'pg36_app unexpectedly has schema CREATE';
    END IF;

    IF pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch12.sales_order',
           'DELETE'
       ) THEN
        RAISE EXCEPTION 'pg36_app unexpectedly has DELETE';
    END IF;

    IF pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch12.outbox',
           'SELECT'
       )
       OR NOT pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch12.outbox',
           'INSERT'
       ) THEN
        RAISE EXCEPTION 'pg36_app outbox privilege drifted';
    END IF;

    IF pg_catalog.has_sequence_privilege(
           'pg36_app',
           'shop_ch12.sales_order_order_id_seq',
           'SELECT'
       )
       OR NOT pg_catalog.has_sequence_privilege(
           'pg36_app',
           'shop_ch12.sales_order_order_id_seq',
           'USAGE'
       ) THEN
        RAISE EXCEPTION 'pg36_app sequence privilege drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.oid =
              'shop_ch12.raise_serialization_once()'::regprocedure
          AND routine.prosecdef
          AND routine.proconfig @>
              ARRAY['search_path=pg_catalog']::text[]
          AND pg_catalog.has_function_privilege(
                  'pg36_app',
                  routine.oid,
                  'EXECUTE'
              )
    ) THEN
        RAISE EXCEPTION 'lab fault function hardening drifted';
    END IF;

    IF (
        SELECT count(*)
        FROM shop_ch12.inventory
    ) <> 2
       OR (
           SELECT available
           FROM shop_ch12.inventory
           WHERE sku = 'PG36-SKU-001'
       ) <> 8
       OR (
           SELECT available
           FROM shop_ch12.inventory
           WHERE sku = 'PG36-SKU-002'
       ) <> 4 THEN
        RAISE EXCEPTION 'inventory final state drifted';
    END IF;

    IF (
        SELECT count(*)
        FROM shop_ch12.sales_order
    ) <> 2
       OR (
           SELECT count(*)
           FROM shop_ch12.sales_order_item
       ) <> 2
       OR (
           SELECT count(*)
           FROM shop_ch12.payment
       ) <> 1
       OR (
           SELECT count(*)
           FROM shop_ch12.outbox
       ) <> 3 THEN
        RAISE EXCEPTION 'service write cardinality drifted';
    END IF;

    IF (
        SELECT count(*)
        FROM shop_ch12.order_request
        WHERE order_id IS NOT NULL
          AND response IS NOT NULL
    ) <> 2
       OR (
           SELECT count(*)
           FROM shop_ch12.payment_request
           WHERE payment_id IS NOT NULL
             AND response IS NOT NULL
       ) <> 1 THEN
        RAISE EXCEPTION 'idempotency ledger drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM shop_ch12.sales_order
        WHERE order_id = 1200001
          AND state = 'paid'
          AND total_minor = 25800
          AND trace_id = 'trace-order-001'
    )
       OR NOT EXISTS (
           SELECT 1
           FROM shop_ch12.sales_order
           WHERE order_id = 1200002
             AND state = 'placed'
             AND total_minor = 8900
             AND trace_id = 'trace-retry-001'
       ) THEN
        RAISE EXCEPTION 'order state or trace relationship drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM shop_ch12.payment
        WHERE payment_id = 1200001
          AND order_id = 1200001
          AND amount_minor = 25800
          AND state = 'captured'
          AND trace_id = 'trace-payment-001'
    ) THEN
        RAISE EXCEPTION 'payment state drifted';
    END IF;

    IF (
        SELECT pg_catalog.array_agg(
                   event_key
                   ORDER BY event_key
               )
        FROM shop_ch12.outbox
    ) IS DISTINCT FROM ARRAY[
        'order:order-001:placed',
        'order:order-retry:placed',
        'payment:pay-001:captured'
    ]::text[] THEN
        RAISE EXCEPTION 'outbox state drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name = 'pg36-ch12-api'
          AND state <> 'idle'
    ) THEN
        RAISE EXCEPTION 'a ch12 API query is still active';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'contract=pg36-ch12-service-contract-v1';
SELECT 'orders=' || count(*)
FROM shop_ch12.sales_order;
SELECT 'payments=' || count(*)
FROM shop_ch12.payment;
SELECT 'outbox=' || count(*)
FROM shop_ch12.outbox;
SELECT 'inventory=' ||
       pg_catalog.string_agg(
           sku || ':' || available || ':v' || version,
           ','
           ORDER BY sku
       )
FROM shop_ch12.inventory;
SELECT 'app_can_create=' ||
       pg_catalog.has_schema_privilege(
           'pg36_app',
           'shop_ch12',
           'CREATE'
       );
SELECT 'app_can_delete=' ||
       pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch12.sales_order',
           'DELETE'
       );
SELECT 'app_can_read_outbox=' ||
       pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch12.outbox',
           'SELECT'
       );
SELECT 'active_api_queries=' || count(*)
FROM pg_catalog.pg_stat_activity
WHERE pid <> pg_catalog.pg_backend_pid()
  AND datname = current_database()
  AND application_name = 'pg36-ch12-api'
  AND state <> 'idle';
SELECT 'relation_checksum=' ||
       pg_catalog.md5(
           pg_catalog.string_agg(
               order_id || '|' || line_no || '|' ||
               product_id || '|' || currency_code || '|' ||
               unit_price_minor || '|' || quantity || '|' ||
               line_total_minor,
               E'\n'
               ORDER BY order_id, line_no
           )
       )
FROM shop.sales_order_item;
