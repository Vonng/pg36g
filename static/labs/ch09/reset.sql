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
    :'reset_token' = 'RESET_CH09_INDEX_LAB' AS token_ok,
    :'reset_target' = 'pg36_shop/shop_private/ch09' AS target_ok
\gset

\if :token_ok
\else
  DO $ch09_reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch09 action token';
  END
  $ch09_reset_error$;
\endif
\if :target_ok
\else
  DO $ch09_reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch09 target token';
  END
  $ch09_reset_error$;
\endif

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch09 deterministic index lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch09_order_probe',
        'shop_private.ch09_inventory_probe',
        'shop_private.ch09_search_probe',
        'shop_private.ch09_event_probe',
        'shop_private.ch09_write_base',
        'shop_private.ch09_write_indexed',
        'shop_private.ch09_unique_probe'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'reset refused: % does not carry the ch09 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch09_unique_probe;
DROP TABLE IF EXISTS shop_private.ch09_write_indexed;
DROP TABLE IF EXISTS shop_private.ch09_write_base;
DROP TABLE IF EXISTS shop_private.ch09_event_probe;
DROP TABLE IF EXISTS shop_private.ch09_search_probe;
DROP TABLE IF EXISTS shop_private.ch09_inventory_probe;
DROP TABLE IF EXISTS shop_private.ch09_order_probe;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_private/ch09';
SELECT 'remaining_ch09_relations=' || count(*)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'shop_private'
  AND relation.relname LIKE 'ch09_%';
