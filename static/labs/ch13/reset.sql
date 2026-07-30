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
    :'reset_token' = 'RESET_CH13_ROUTINE_GUARD' AS token_ok,
    :'reset_target' = 'pg36_shop/shop_ch13' AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3620',
          MESSAGE = 'reset refused: invalid ch13 action token';
  END
  $action_guard$;
\endif

\if :target_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3621',
          MESSAGE = 'reset refused: invalid ch13 target token';
  END
  $action_guard$;
\endif

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch13');
    expected_marker constant text :=
        'pg36 ch13 routine guard lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3622',
            MESSAGE = 'reset refused: shop_ch13 schema marker mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
          AND (
              relation.relname <> ALL (ARRAY[
                  'schema_version',
                  'sales_order',
                  'payment',
                  'order_history',
                  'statement_audit',
                  'payment_payment_id_seq',
                  'order_history_history_id_seq',
                  'statement_audit_audit_id_seq'
              ])
              OR pg_catalog.obj_description(
                     relation.oid,
                     'pg_class'
                 ) IS DISTINCT FROM expected_marker
          )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3622',
            MESSAGE = 'reset refused: shop_ch13 relation inventory drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
          AND (
              routine.oid::pg_catalog.regprocedure::text
                  <> ALL (ARRAY[
                  'shop_ch13.allowed_transition(text,text)',
                  'shop_ch13.order_snapshot(bigint)',
                  'shop_ch13.guard_order_transition()',
                  'shop_ch13.audit_order_transition()',
                  'shop_ch13.validate_paid_order()',
                  'shop_ch13.transition_order(bigint,bigint,text,text)',
                  'shop_ch13.capture_payment(bigint,bigint,text,bigint,text)',
                  'shop_ch13.expire_stale_orders(timestamp with time zone,integer,integer)'
              ])
              OR pg_catalog.obj_description(
                     routine.oid,
                     'pg_proc'
                 ) IS DISTINCT FROM expected_marker
          )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3622',
            MESSAGE = 'reset refused: shop_ch13 routine inventory drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_trigger AS trigger_catalog
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_catalog.tgrelid
        WHERE relation.relnamespace = schema_oid
          AND NOT trigger_catalog.tgisinternal
          AND (
              trigger_catalog.tgname <> ALL (ARRAY[
                  'a_guard_order_transition',
                  'z_audit_order_transition',
                  'z_validate_paid_order',
                  'z_validate_payment'
              ])
              OR pg_catalog.obj_description(
                     trigger_catalog.oid,
                     'pg_trigger'
                 ) IS DISTINCT FROM expected_marker
          )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3622',
            MESSAGE = 'reset refused: shop_ch13 trigger inventory drifted';
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
          AND application_name LIKE 'pg36-ch13-%'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3623',
            MESSAGE = 'reset refused: ch13 workers are active';
    END IF;
END
$active_guard$;

DROP TABLE IF EXISTS shop_ch13.payment;
DROP TABLE IF EXISTS shop_ch13.order_history;
DROP TABLE IF EXISTS shop_ch13.statement_audit;
DROP TABLE IF EXISTS shop_ch13.sales_order;
DROP TABLE IF EXISTS shop_ch13.schema_version;

DROP PROCEDURE IF EXISTS shop_ch13.expire_stale_orders(
    timestamptz,
    integer,
    integer
);
DROP FUNCTION IF EXISTS shop_ch13.capture_payment(
    bigint,
    bigint,
    text,
    bigint,
    text
);
DROP FUNCTION IF EXISTS shop_ch13.transition_order(
    bigint,
    bigint,
    text,
    text
);
DROP FUNCTION IF EXISTS shop_ch13.validate_paid_order();
DROP FUNCTION IF EXISTS shop_ch13.audit_order_transition();
DROP FUNCTION IF EXISTS shop_ch13.guard_order_transition();
DROP FUNCTION IF EXISTS shop_ch13.order_snapshot(bigint);
DROP FUNCTION IF EXISTS shop_ch13.allowed_transition(text, text);
DROP SCHEMA IF EXISTS shop_ch13;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_ch13';
SELECT 'remaining_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace('shop_ch13') IS NULL
               THEN '0'
           ELSE '1'
       END;
