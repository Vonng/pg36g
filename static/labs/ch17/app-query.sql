\set ON_ERROR_STOP on
\pset pager off

SELECT
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(amount) AS amount_total
FROM shop_ch17.sales_fact_distributed
WHERE tenant_id = 3
  AND occurred_on >= DATE '2026-04-01';
