\set ON_ERROR_STOP on
\ir context.sql

BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT available AS waiter_observed
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
FOR UPDATE
\gset

SELECT pg_catalog.format(
    'waiter=locked/available=%s',
    :waiter_observed
);

UPDATE shop_private.ch10_inventory
SET available = available - 20,
    version = version + 1,
    updated_at = timestamptz '2025-01-01 00:05:30+00'
WHERE sku_id = 1001
  AND available >= 20
RETURNING pg_catalog.format(
    'waiter=updated/available=%s/version=%s',
    available,
    version
);

COMMIT;
