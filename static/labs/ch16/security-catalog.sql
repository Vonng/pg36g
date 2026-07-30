\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    'app_schema_usage' AS key,
    pg_catalog.has_schema_privilege(
        'pg36_app',
        'shop_ch16',
        'USAGE'
    )::text AS value
UNION ALL
SELECT
    'app_event_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch16.delivery_event',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_event_insert',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch16.delivery_event',
        'INSERT'
    )::text
UNION ALL
SELECT
    'app_event_update',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch16.delivery_event',
        'UPDATE'
    )::text
UNION ALL
SELECT
    'app_event_delete',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch16.delivery_event',
        'DELETE'
    )::text
UNION ALL
SELECT
    'app_membership_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch16.event_zone_membership',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_extension_schema_usage',
    pg_catalog.has_schema_privilege(
        'pg36_app',
        'shop_ch16_ext',
        'USAGE'
    )::text
ORDER BY key;
