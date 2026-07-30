\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    object_name,
    bytes
FROM (
    VALUES
        (
            'account_dim_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch17.account_dim'::pg_catalog.regclass
            )
        ),
        (
            'daily_summary_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch17.daily_tenant_summary'
                    ::pg_catalog.regclass
            )
        ),
        (
            'sales_fact_heap',
            pg_catalog.pg_relation_size(
                'shop_ch17.sales_fact'::pg_catalog.regclass
            )
        ),
        (
            'sales_fact_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch17.sales_fact'::pg_catalog.regclass
            )
        ),
        (
            'sales_tenant_day_index',
            pg_catalog.pg_relation_size(
                'shop_ch17.sales_fact_tenant_day_idx'
                    ::pg_catalog.regclass
            )
        ),
        (
            'sales_day_brin_index',
            pg_catalog.pg_relation_size(
                'shop_ch17.sales_fact_day_brin_idx'
                    ::pg_catalog.regclass
            )
        )
) AS size_fact(object_name, bytes)
ORDER BY object_name;
