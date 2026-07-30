\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    pg_catalog.obj_description(
        'shop_private.ch07_plan_probe'::regclass,
        'pg_class'
    ) = 'pg36 ch07 deterministic planner lab; safe to rebuild'
        AS plan_marker_ok,
    pg_catalog.obj_description(
        'shop_private.ch07_event_probe'::regclass,
        'pg_class'
    ) = 'pg36 ch07 deterministic planner lab; safe to rebuild'
        AS event_marker_ok,
    (
        SELECT count(*) = 100000
           AND count(*) FILTER (WHERE tenant_id = 1) = 90000
           AND count(*) FILTER (WHERE tenant_id = 1001) = 10
           AND count(*) FILTER (
                   WHERE region = 'east'
                     AND order_status = 'paid'
               ) = 25000
           AND count(*) FILTER (
                   WHERE region = 'east'
                     AND order_status = 'cancelled'
               ) = 0
        FROM shop_private.ch07_plan_probe
    ) AS plan_data_ok,
    (
        SELECT count(*) = 3650
           AND min(occurred_on) = date '2025-01-01'
           AND max(occurred_on) = date '2025-12-31'
        FROM shop_private.ch07_event_probe
    ) AS event_data_ok,
    (
        SELECT count(*) FILTER (WHERE isleaf) = 4
        FROM pg_catalog.pg_partition_tree(
            'shop_private.ch07_event_probe'::regclass
        )
    ) AS partition_count_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_statistic_ext
        WHERE stxname = 'ch07_region_status_stats'
          AND stxnamespace = 'shop_private'::regnamespace
          AND stxkind @> ARRAY['f', 'm']::"char"[]
    ) AS extended_stats_ok,
    (
        SELECT count(*) > 0
        FROM pg_catalog.pg_stats
        WHERE schemaname = 'shop_private'
          AND tablename = 'ch07_event_probe'
    ) AS parent_stats_ok
\gset

\if :plan_marker_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 plan marker verification failed';
  END
  $ch07_verify_error$;
\endif
\if :event_marker_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 event marker verification failed';
  END
  $ch07_verify_error$;
\endif
\if :plan_data_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 plan data verification failed';
  END
  $ch07_verify_error$;
\endif
\if :event_data_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 event data verification failed';
  END
  $ch07_verify_error$;
\endif
\if :partition_count_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 partition count verification failed';
  END
  $ch07_verify_error$;
\endif
\if :extended_stats_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 extended statistics verification failed';
  END
  $ch07_verify_error$;
\endif
\if :parent_stats_ok
\else
  DO $ch07_verify_error$
  BEGIN
      RAISE EXCEPTION 'ch07 partition parent statistics are missing';
  END
  $ch07_verify_error$;
\endif

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'fixture=ch07-plan-v1';
SELECT 'plan_probe_rows=100000';
SELECT 'hot_tenant_rows=90000';
SELECT 'cold_tenant_rows=10';
SELECT 'correlated_pair_rows=25000';
SELECT 'impossible_pair_rows=0';
SELECT 'partition_rows=3650';
SELECT 'partition_leaf_count=4';
SELECT 'extended_statistics=dependencies+mcv';
SELECT 'partition_parent_stats=present';
