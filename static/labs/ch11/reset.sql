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
    :'reset_token' = 'RESET_CH11_RELEASE_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_private/ch11' AS target_ok
\gset

\if :token_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch11 action token';
  END
  $reset_error$;
\endif
\if :target_ok
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch11 target token';
  END
  $reset_error$;
\endif

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    function_oid regprocedure;
    expected_marker constant text :=
        'pg36 ch11 deterministic release lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch11_order',
        'shop_private.ch11_migration_state',
        'shop_private.ch11_default_probe',
        'shop_private.ch11_default_probe_result',
        'shop_private.ch11_event',
        'shop_private.ch11_event_2025q1'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'reset refused: % lacks the ch11 marker',
                relation_name;
        END IF;
    END LOOP;

    function_oid := pg_catalog.to_regprocedure(
        'shop_private.ch11_sync_shipping_code()'
    );
    IF function_oid IS NOT NULL
       AND pg_catalog.obj_description(
               function_oid::oid,
               'pg_proc'
           ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'reset refused: ch11 function lacks marker';
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
          AND application_name LIKE 'pg36-ch11-%'
    ) THEN
        RAISE EXCEPTION 'reset refused: ch11 workers are active';
    END IF;
END
$active_guard$;

DROP TABLE IF EXISTS shop_private.ch11_event CASCADE;
DROP TABLE IF EXISTS shop_private.ch11_event_2025q1;
DROP TABLE IF EXISTS shop_private.ch11_default_probe_result;
DROP TABLE IF EXISTS shop_private.ch11_default_probe;
DROP TABLE IF EXISTS shop_private.ch11_order;
DROP TABLE IF EXISTS shop_private.ch11_migration_state;
DROP FUNCTION IF EXISTS shop_private.ch11_sync_shipping_code();

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_private/ch11';
SELECT 'remaining_ch11_relations=' || count(*)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'shop_private'
  AND relation.relname LIKE 'ch11_%';
SELECT 'remaining_ch11_functions=' || count(*)
FROM pg_catalog.pg_proc AS function_catalog
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = function_catalog.pronamespace
WHERE namespace.nspname = 'shop_private'
  AND function_catalog.proname LIKE 'ch11_%';
