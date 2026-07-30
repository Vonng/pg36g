\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    pg_catalog.obj_description(
        'shop_private.ch07_plan_probe'::regclass,
        'pg_class'
    ) = 'pg36 ch07 deterministic planner lab; safe to rebuild'
        AS marker_ok,
    (
        SELECT count(*) = 100000
        FROM shop_private.ch07_plan_probe
    ) AS row_count_ok
\gset

\if :marker_ok
\else
  DO $ch07_stats_error$
  BEGIN
      RAISE EXCEPTION 'ch07 statistics target marker drifted';
  END
  $ch07_stats_error$;
\endif

\if :row_count_ok
\else
  DO $ch07_stats_error$
  BEGIN
      RAISE EXCEPTION 'ch07 statistics target row count drifted';
  END
  $ch07_stats_error$;
\endif

DROP STATISTICS IF EXISTS shop_private.ch07_region_status_stats;
CREATE STATISTICS shop_private.ch07_region_status_stats
    (dependencies, mcv)
    ON region, order_status
    FROM shop_private.ch07_plan_probe;
ALTER STATISTICS shop_private.ch07_region_status_stats
    SET STATISTICS 1000;
ANALYZE shop_private.ch07_plan_probe;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'statistics=dependencies+mcv';
SELECT 'statistics_target=' || stxstattarget
FROM pg_catalog.pg_statistic_ext
WHERE stxname = 'ch07_region_status_stats'
  AND stxnamespace = 'shop_private'::regnamespace;
