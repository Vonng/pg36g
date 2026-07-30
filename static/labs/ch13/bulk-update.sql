\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

DO $actor$
BEGIN
    PERFORM pg_catalog.set_config(
        'pg36.actor',
        'bulk-lab',
        true
    );
END
$actor$;

UPDATE shop_ch13.sales_order
SET
    status = 'canceled',
    version = version + 1
WHERE order_id IN (105, 106, 107);

COMMIT;

SELECT
    affected_count,
    order_ids,
    actor,
    session_actor
FROM shop_ch13.statement_audit
WHERE order_ids = ARRAY[105::bigint, 106::bigint, 107::bigint];
