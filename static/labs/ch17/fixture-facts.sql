\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH local_fact AS (
    SELECT
        pg_catalog.count(*) AS sale_count,
        pg_catalog.sum(units) AS unit_count,
        pg_catalog.sum(amount) AS amount_total,
        pg_catalog.min(occurred_on) AS first_day,
        pg_catalog.max(occurred_on) AS last_day
    FROM shop_ch17.sales_fact
),
distributed_fact AS (
    SELECT
        pg_catalog.count(*) AS sale_count,
        pg_catalog.sum(units) AS unit_count,
        pg_catalog.sum(amount) AS amount_total
    FROM shop_ch17.sales_fact_distributed
),
fact AS (
    SELECT
        'local_sales'::text AS key,
        sale_count::text AS value
    FROM local_fact

    UNION ALL

    SELECT 'local_units', unit_count::text
    FROM local_fact

    UNION ALL

    SELECT 'local_amount', amount_total::text
    FROM local_fact

    UNION ALL

    SELECT 'first_day', first_day::text
    FROM local_fact

    UNION ALL

    SELECT 'last_day', last_day::text
    FROM local_fact

    UNION ALL

    SELECT 'distributed_sales', sale_count::text
    FROM distributed_fact

    UNION ALL

    SELECT 'distributed_units', unit_count::text
    FROM distributed_fact

    UNION ALL

    SELECT 'distributed_amount', amount_total::text
    FROM distributed_fact

    UNION ALL

    SELECT
        'summary_rows',
        pg_catalog.count(*)::text
    FROM shop_ch17.daily_tenant_summary

    UNION ALL

    SELECT
        'summary_sales',
        pg_catalog.sum(sale_count)::text
    FROM shop_ch17.daily_tenant_summary

    UNION ALL

    SELECT
        'shard_rows',
        pg_catalog.string_agg(
            tableoid::pg_catalog.regclass::text ||
            ':' || sale_count::text,
            ',' ORDER BY
                tableoid::pg_catalog.regclass::text
        )
    FROM (
        SELECT
            tableoid,
            pg_catalog.count(*) AS sale_count
        FROM shop_ch17.sales_fact_distributed
        GROUP BY tableoid
    ) AS shard_count
)
SELECT key, value
FROM fact
ORDER BY key;
