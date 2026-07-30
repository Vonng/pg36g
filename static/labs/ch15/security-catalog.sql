\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    'app_schema_usage' AS key,
    pg_catalog.has_schema_privilege(
        'pg36_app',
        'shop_ch15',
        'USAGE'
    )::text AS value
UNION ALL
SELECT
    'app_product_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch15.product_search',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_product_insert',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch15.product_search',
        'INSERT'
    )::text
UNION ALL
SELECT
    'app_product_update',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch15.product_search',
        'UPDATE'
    )::text
UNION ALL
SELECT
    'app_product_delete',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch15.product_search',
        'DELETE'
    )::text
UNION ALL
SELECT
    'app_quality_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch15.quality_summary',
        'SELECT'
    )::text
ORDER BY key;
