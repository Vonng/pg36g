\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker unknown
\endif
\if :{?qty}
\else
  \set qty 0
\endif
\if :{?gate}
\else
  \set gate 0
\endif

BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT
    available AS observed,
    available - :qty AS replacement
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
\gset

SELECT pg_catalog.format(
           'worker=%s/rr_observed=%s/qty=%s/replacement=%s',
           :'worker',
           :observed,
           :qty,
           :replacement
       );

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

UPDATE shop_private.ch10_inventory
SET available = :replacement,
    version = version + 1,
    updated_at = timestamptz '2025-01-01 00:04:00+00'
WHERE sku_id = 1001
RETURNING pg_catalog.format(
    'worker=%s/rr_wrote=%s/version=%s',
    :'worker',
    available,
    version
);

COMMIT;
