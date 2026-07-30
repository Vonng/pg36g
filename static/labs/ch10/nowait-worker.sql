\set ON_ERROR_STOP on
\ir context.sql

BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT available
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
FOR UPDATE NOWAIT;
ROLLBACK;
