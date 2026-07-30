\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        tenant_id,
        pg_catalog.to_char(
            pg_catalog.date_trunc(
                'month',
                occurred_on::timestamp
            )::date,
            'YYYY-MM-DD'
        ) AS month_start,
        pg_catalog.sum(sale_count)::bigint AS sale_count,
        pg_catalog.sum(unit_count)::bigint AS unit_count,
        pg_catalog.sum(amount_total)::numeric(18,2)
            AS amount_total
    FROM shop_ch17.daily_tenant_summary
    GROUP BY
        tenant_id,
        pg_catalog.date_trunc(
            'month',
            occurred_on::timestamp
        )::date
    ORDER BY tenant_id, month_start
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
