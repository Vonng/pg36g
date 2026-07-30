\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

ALTER SERVER pg36_ch17_shard_b
    OPTIONS (SET port '1');

SELECT
    shop_ch17_ext.postgres_fdw_disconnect(
        'pg36_ch17_shard_b'
    );

SELECT
    'healthy_shard_tenant_2=' ||
    pg_catalog.count(*)::text
FROM shop_ch17.sales_fact_distributed
WHERE tenant_id = 2;

SELECT
    pg_catalog.count(*)
FROM shop_ch17.sales_fact_distributed;
