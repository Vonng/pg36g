\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    relation.relname AS relation_name,
    trigger_catalog.tgname AS trigger_name,
    trigger_catalog.tgfoid::pg_catalog.regprocedure::text
        AS function_signature,
    (trigger_catalog.tgtype & 1) <> 0 AS row_level,
    (trigger_catalog.tgtype & 2) <> 0 AS before_timing,
    (trigger_catalog.tgtype & 64) <> 0 AS instead_timing,
    trigger_catalog.tgdeferrable,
    trigger_catalog.tginitdeferred,
    coalesce(trigger_catalog.tgoldtable, '')
        AS old_transition_table,
    coalesce(trigger_catalog.tgnewtable, '')
        AS new_transition_table,
    pg_catalog.pg_get_triggerdef(
        trigger_catalog.oid,
        true
    ) AS trigger_definition,
    pg_catalog.obj_description(
        trigger_catalog.oid,
        'pg_trigger'
    ) AS marker
FROM pg_catalog.pg_trigger AS trigger_catalog
JOIN pg_catalog.pg_class AS relation
  ON relation.oid = trigger_catalog.tgrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'shop_ch13'
  AND NOT trigger_catalog.tgisinternal
ORDER BY relation_name, trigger_name;
