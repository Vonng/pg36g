\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

EXPLAIN (
    ANALYZE,
    VERBOSE,
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
    pg_catalog.sum(sale_count) AS sale_count,
    pg_catalog.sum(unit_count) AS unit_count,
    pg_catalog.sum(amount_total) AS amount_total
FROM (
    SELECT
        tenant_id,
        occurred_on,
        pg_catalog.count(*) AS sale_count,
        pg_catalog.sum(units)::bigint AS unit_count,
        pg_catalog.sum(amount) AS amount_total
    FROM shop_ch17.sales_fact_dist_0
    GROUP BY tenant_id, occurred_on

    UNION ALL

    SELECT
        tenant_id,
        occurred_on,
        pg_catalog.count(*) AS sale_count,
        pg_catalog.sum(units)::bigint AS unit_count,
        pg_catalog.sum(amount) AS amount_total
    FROM shop_ch17.sales_fact_dist_1
    GROUP BY tenant_id, occurred_on
) AS shard_daily
GROUP BY tenant_id, month_start
ORDER BY tenant_id, month_start;
