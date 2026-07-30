\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        tenant_id,
        pg_catalog.to_char(
            month_start,
            'YYYY-MM-DD'
        ) AS month_start,
        sale_count,
        unit_count,
        amount_total
    FROM shop_ch17.local_tenant_month
    ORDER BY tenant_id, month_start
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
