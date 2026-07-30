\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH business_rows AS (
    SELECT
        'account'::text AS kind,
        pg_catalog.lpad(tenant_id::text, 2, '0') ||
            '|' ||
            pg_catalog.lpad(account_id::text, 3, '0')
            AS sort_key,
        pg_catalog.concat_ws(
            '|',
            tenant_id,
            account_id,
            segment,
            region
        ) AS payload
    FROM shop_ch17.account_dim

    UNION ALL

    SELECT
        'sale',
        pg_catalog.lpad(sale_id::text, 9, '0'),
        pg_catalog.concat_ws(
            '|',
            sale_id,
            tenant_id,
            account_id,
            occurred_on,
            channel,
            units,
            amount
        )
    FROM shop_ch17.sales_fact
),
business_checksum AS (
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           ) AS checksum
    FROM business_rows
),
monthly_checksum AS (
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   pg_catalog.concat_ws(
                       '|',
                       tenant_id,
                       month_start,
                       sale_count,
                       unit_count,
                       amount_total
                   ),
                   E'\n'
                   ORDER BY tenant_id, month_start
               )
           ) AS checksum
    FROM shop_ch17.local_tenant_month
),
shard_count AS (
    SELECT
        tableoid::pg_catalog.regclass::text AS shard_name,
        pg_catalog.count(*) AS sale_count
    FROM shop_ch17.sales_fact_distributed
    GROUP BY tableoid
),
fact AS (
    SELECT
        'release'::text AS key,
        '1.5-proposal'::text AS value

    UNION ALL

    SELECT 'fixture', fixture_version
    FROM shop_ch17.fixture_meta

    UNION ALL

    SELECT
        'local_sales',
        pg_catalog.count(*)::text
    FROM shop_ch17.sales_fact

    UNION ALL

    SELECT
        'distributed_sales',
        pg_catalog.count(*)::text
    FROM shop_ch17.sales_fact_distributed

    UNION ALL

    SELECT
        'shard_rows',
        pg_catalog.string_agg(
            shard_name || ':' || sale_count::text,
            ',' ORDER BY shard_name
        )
    FROM shard_count

    UNION ALL

    SELECT
        'summary_rows',
        pg_catalog.count(*)::text
    FROM shop_ch17.daily_tenant_summary

    UNION ALL

    SELECT
        'tenant3_april',
        pg_catalog.count(*)::text ||
            ':' ||
            pg_catalog.sum(amount)::text
    FROM shop_ch17.sales_fact_distributed
    WHERE tenant_id = 3
      AND occurred_on >= DATE '2026-04-01'

    UNION ALL

    SELECT 'naive_transfer_rows', '240000'

    UNION ALL

    SELECT 'two_stage_transfer_rows', '960'

    UNION ALL

    SELECT
        'postgres_fdw',
        extversion
    FROM pg_catalog.pg_extension
    WHERE extname = 'postgres_fdw'

    UNION ALL

    SELECT
        'business_checksum',
        checksum
    FROM business_checksum

    UNION ALL

    SELECT
        'monthly_checksum',
        checksum
    FROM monthly_checksum
)
SELECT key, value
FROM fact
ORDER BY key;
