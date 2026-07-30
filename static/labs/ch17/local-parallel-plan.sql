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
SELECT
    tenant_id,
    pg_catalog.date_trunc(
        'month',
        occurred_on::timestamp
    )::date AS month_start,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(amount) AS amount_total
FROM shop_ch17.sales_fact
GROUP BY tenant_id, month_start
ORDER BY tenant_id, month_start;
