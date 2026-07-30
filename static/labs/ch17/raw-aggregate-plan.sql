\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET min_parallel_table_scan_size = 0;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0;
SET max_parallel_workers_per_gather = 2;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT *
FROM shop_ch17.local_tenant_month
ORDER BY tenant_id, month_start;
