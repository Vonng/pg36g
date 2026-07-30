\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET max_parallel_workers_per_gather = 0;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT
    account_id,
    pg_catalog.sum(amount) AS amount_total
FROM shop_ch17.sales_fact
WHERE tenant_id = 3
  AND occurred_on >= DATE '2026-04-01'
GROUP BY account_id
ORDER BY account_id;
