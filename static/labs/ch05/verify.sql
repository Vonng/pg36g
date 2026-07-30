\set ON_ERROR_STOP on
\ir ../ch04/verify-v1.sql

DO $verify$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND (
              application_name LIKE 'pg36-ch05-blocker-%'
              OR application_name LIKE 'pg36-ch05-waiter-%'
          )
    ) THEN
        RAISE EXCEPTION 'a ch05 blocker or waiter session is still connected';
    END IF;

    IF (
        SELECT request_fingerprint
        FROM shop.sales_order
        WHERE order_id = 1002
    ) IS DISTINCT FROM pg_catalog.md5('bob|gift:1') THEN
        RAISE EXCEPTION 'the rollback-only labs changed order 1002';
    END IF;
END
$verify$;

\echo '--- ch05 verify:state ---'

SELECT key || '=' || value AS state
FROM (
    SELECT 1, 'status', 'ok'
    UNION ALL
    SELECT 2, 'model_version', 'ch04-v1'
    UNION ALL
    SELECT 3, 'lab_state', 'rollback-only'
    UNION ALL
    SELECT 4, 'active_lab_workers',
           count(*)::text
      FROM pg_catalog.pg_stat_activity
     WHERE pid <> pg_catalog.pg_backend_pid()
       AND datname = current_database()
       AND (
           application_name LIKE 'pg36-ch05-blocker-%'
           OR application_name LIKE 'pg36-ch05-waiter-%'
       )
    UNION ALL
    SELECT 5, 'order_1002_fingerprint',
           request_fingerprint
      FROM shop.sales_order
     WHERE order_id = 1002
    UNION ALL
    SELECT 6, 'relation_checksum',
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
) AS snapshot(ord, key, value)
ORDER BY ord;
