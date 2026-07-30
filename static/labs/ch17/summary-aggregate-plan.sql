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
    tenant_id,
    pg_catalog.date_trunc(
        'month',
        occurred_on::timestamp
    )::date AS month_start,
    pg_catalog.sum(sale_count)::bigint AS sale_count,
    pg_catalog.sum(unit_count)::bigint AS unit_count,
    pg_catalog.sum(amount_total)::numeric(18,2)
        AS amount_total
FROM shop_ch17.daily_tenant_summary
GROUP BY tenant_id, month_start
ORDER BY tenant_id, month_start;
