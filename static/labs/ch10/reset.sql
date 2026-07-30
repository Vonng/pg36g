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
    :'reset_token' = 'RESET_CH10_CONCURRENCY_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_private/ch10' AS target_ok
\gset

\if :token_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch10 action token';
  END
  $reset_error$;
\endif

\if :target_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch10 target token';
  END
  $reset_error$;
\endif

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch10 deterministic concurrency lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch10_inventory',
        'shop_private.ch10_doctor',
        'shop_private.ch10_deadlock_probe',
        'shop_private.ch10_job',
        'shop_private.ch10_payment_request',
        'shop_private.ch10_outbox'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'reset refused: % lacks the ch10 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DO $active_guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch10-%'
    ) THEN
        RAISE EXCEPTION 'reset refused: ch10 workers are active';
    END IF;
END
$active_guard$;

DROP TABLE IF EXISTS shop_private.ch10_outbox;
DROP TABLE IF EXISTS shop_private.ch10_payment_request;
DROP TABLE IF EXISTS shop_private.ch10_job;
DROP TABLE IF EXISTS shop_private.ch10_deadlock_probe;
DROP TABLE IF EXISTS shop_private.ch10_doctor;
DROP TABLE IF EXISTS shop_private.ch10_inventory;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_private/ch10';
SELECT 'remaining_ch10_relations=' || count(*)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'shop_private'
  AND relation.relname LIKE 'ch10_%';
