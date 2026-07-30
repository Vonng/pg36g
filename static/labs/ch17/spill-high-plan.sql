\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET max_parallel_workers_per_gather = 0;
SET work_mem = '32MB';

EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT pg_catalog.count(*)
FROM (
    SELECT sale_id, amount
    FROM shop_ch17.sales_fact
    ORDER BY amount, sale_id
    OFFSET 0
) AS ordered_sales;
