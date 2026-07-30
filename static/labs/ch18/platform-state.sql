\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
\ir context.sql

SELECT key, value
FROM (
    SELECT 1 AS ord, 'database'::text AS key,
           current_database()::text AS value
    UNION ALL
    SELECT 2, 'server_major',
           (
               current_setting('server_version_num')::integer
                   / 10000
           )::text
    UNION ALL
    SELECT 3, 'server_version',
           current_setting('server_version')
    UNION ALL
    SELECT 4, 'session_user', session_user
    UNION ALL
    SELECT 5, 'in_recovery',
           pg_catalog.pg_is_in_recovery()::text
    UNION ALL
    SELECT 6, 'model_version', 'ch04-v1'
    UNION ALL
    SELECT 7, 'relation_checksum',
           pg_catalog.md5(
               pg_catalog.string_agg(
                   order_id || '|' || line_no || '|' ||
                   product_id || '|' || currency_code || '|' ||
                   unit_price_minor || '|' || quantity || '|' ||
                   line_total_minor,
                   E'\n'
                   ORDER BY order_id, line_no
               )
           )
      FROM shop.sales_order_item
    UNION ALL
    SELECT 8, 'pigsty_reference', '4.4'
    UNION ALL
    SELECT 9, 'pigsty_l1', 'not-run'
    UNION ALL
    SELECT 10, 'mutation', 'none'
) AS state
ORDER BY ord;

COMMIT;
