\set ON_ERROR_STOP on
\pset pager off
\ir remote-context.sql

SELECT
    current_database() AS database_name,
    :shard_remainder::integer AS shard_remainder,
    pg_catalog.count(DISTINCT tenant_id)
        AS tenant_count,
    pg_catalog.min(tenant_id) AS min_tenant,
    pg_catalog.max(tenant_id) AS max_tenant,
    (
        SELECT pg_catalog.count(*)
        FROM shop_ch17_shard.account_dim
    ) AS account_count,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(units) AS unit_count,
    pg_catalog.sum(amount) AS amount_total,
    pg_catalog.min(occurred_on) AS first_day,
    pg_catalog.max(occurred_on) AS last_day,
    pg_catalog.md5(
        pg_catalog.string_agg(
            sale_id::text || '|' ||
            tenant_id::text || '|' ||
            account_id::text || '|' ||
            occurred_on::text || '|' ||
            channel || '|' ||
            units::text || '|' ||
            amount::text,
            E'\n' ORDER BY sale_id
        )
    ) AS checksum,
    pg_catalog.obj_description(
        pg_catalog.to_regnamespace(
            'shop_ch17_shard'
        ),
        'pg_namespace'
    ) AS marker
FROM shop_ch17_shard.sales_fact;
