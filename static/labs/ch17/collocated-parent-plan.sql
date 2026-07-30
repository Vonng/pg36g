\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_partitionwise_join = on;

EXPLAIN (
    ANALYZE,
    VERBOSE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT
    account.segment,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(sale.amount) AS amount_total
FROM shop_ch17.sales_fact_distributed AS sale
JOIN shop_ch17.account_dim_distributed AS account
  USING (tenant_id, account_id)
WHERE sale.tenant_id = 3
  AND sale.occurred_on >= DATE '2026-04-01'
GROUP BY account.segment
ORDER BY account.segment;
