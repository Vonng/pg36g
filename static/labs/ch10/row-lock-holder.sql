\set ON_ERROR_STOP on
\ir context.sql

\if :{?gate}
\else
  \set gate 0
\endif

BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT available AS holder_observed
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
FOR UPDATE
\gset

SELECT pg_catalog.format(
    'holder=locked/available=%s',
    :holder_observed
);

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

UPDATE shop_private.ch10_inventory
SET available = available - 10,
    version = version + 1,
    updated_at = timestamptz '2025-01-01 00:05:00+00'
WHERE sku_id = 1001
  AND available >= 10
RETURNING pg_catalog.format(
    'holder=updated/available=%s/version=%s',
    available,
    version
);

COMMIT;
