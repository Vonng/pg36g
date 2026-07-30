\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    'app_schema_usage' AS key,
    pg_catalog.has_schema_privilege(
        'pg36_app',
        'shop_ch17',
        'USAGE'
    )::text AS value
UNION ALL
SELECT
    'app_local_sales_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch17.sales_fact',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_local_sales_write',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch17.sales_fact',
        'INSERT,UPDATE,DELETE'
    )::text
UNION ALL
SELECT
    'app_distributed_sales_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch17.sales_fact_distributed',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_distributed_sales_write',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch17.sales_fact_distributed',
        'INSERT,UPDATE,DELETE'
    )::text
UNION ALL
SELECT
    'app_server_a_usage',
    pg_catalog.has_server_privilege(
        'pg36_app',
        'pg36_ch17_shard_a',
        'USAGE'
    )::text
UNION ALL
SELECT
    'app_server_b_usage',
    pg_catalog.has_server_privilege(
        'pg36_app',
        'pg36_ch17_shard_b',
        'USAGE'
    )::text
ORDER BY key;
