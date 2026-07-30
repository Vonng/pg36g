\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker retry
\endif
\if :{?qty}
\else
  \set qty 0
\endif

BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT
    available AS observed,
    version AS observed_version
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
\gset

WITH changed AS (
    UPDATE shop_private.ch10_inventory
    SET available = available - :qty,
        version = version + 1,
        updated_at = timestamptz '2025-01-01 00:03:30+00'
    WHERE sku_id = 1001
      AND version = :observed_version
      AND available >= :qty
    RETURNING available, version
)
SELECT pg_catalog.format(
           'worker=%s/qty=%s/retry_updated=%s/available=%s/version=%s',
           :'worker',
           :qty,
           count(*),
           coalesce(max(available)::text, 'null'),
           coalesce(max(version)::text, 'null')
       )
FROM changed;

COMMIT;
