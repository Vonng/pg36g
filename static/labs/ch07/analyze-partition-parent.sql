\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    pg_catalog.obj_description(
        'shop_private.ch07_event_probe'::regclass,
        'pg_class'
    ) = 'pg36 ch07 deterministic planner lab; safe to rebuild'
        AS marker_ok
\gset

\if :marker_ok
\else
  DO $ch07_partition_error$
  BEGIN
      RAISE EXCEPTION 'ch07 partition target marker drifted';
  END
  $ch07_partition_error$;
\endif

ANALYZE shop_private.ch07_event_probe;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'partition_parent_stats_after=' || count(*)
FROM pg_catalog.pg_stats
WHERE schemaname = 'shop_private'
  AND tablename = 'ch07_event_probe';
