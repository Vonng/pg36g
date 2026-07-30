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
    :'reset_token' = 'RESET_CH07_PLAN_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_private/ch07' AS target_ok
\gset

\if :token_ok
\else
  DO $ch07_reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch07 action token';
  END
  $ch07_reset_error$;
\endif
\if :target_ok
\else
  DO $ch07_reset_error$
  BEGIN
      RAISE EXCEPTION 'reset refused: invalid ch07 target token';
  END
  $ch07_reset_error$;
\endif

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch07 deterministic planner lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch07_plan_probe',
        'shop_private.ch07_event_probe'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'reset refused: % does not carry the ch07 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch07_event_probe CASCADE;
DROP TABLE IF EXISTS shop_private.ch07_plan_probe CASCADE;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_private/ch07';
SELECT 'remaining_ch07_relations=' || count(*)
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'shop_private'
  AND c.relname LIKE 'ch07_%';
