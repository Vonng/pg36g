\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\if :{?reset_token}
\else
  \set reset_token ''
\endif

\if :{?reset_target}
\else
  \set reset_target ''
\endif

SELECT
    :'reset_token' = 'RESET_CH12_SERVICE_LAB' AS token_ok,
    :'reset_target' = 'pg36_shop/shop_ch12' AS target_ok
\gset

\if :token_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch12 action token';
  END
  $reset_error$;
\endif

\if :target_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch12 target token';
  END
  $reset_error$;
\endif

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
            'reset refused: shop_ch12 lacks the exact lab marker';
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
            'reset refused: unknown relation in shop_ch12: %',
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
            'reset refused: unknown function in shop_ch12: %',
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
            'reset refused: unknown standalone type in shop_ch12: %',
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
            'reset refused: a ch12 relation lacks the marker';
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
            'reset refused: a ch12 function lacks the marker';
    END IF;
END
$collision_guard$;

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
            'reset refused: pg36-ch12-api still has database sessions';
    END IF;
END
$active_guard$;

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

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_ch12';
SELECT 'schema_remaining=' ||
       count(*)
FROM pg_catalog.pg_namespace
WHERE nspname = 'shop_ch12';
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
