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

BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

WITH changed AS (
    UPDATE shop_private.ch10_inventory
    SET available = available - :qty,
        version = version + 1,
        updated_at = timestamptz '2025-01-01 00:02:00+00'
    WHERE sku_id = 1001
      AND available >= :qty
    RETURNING available, version
)
SELECT pg_catalog.format(
           'worker=%s/qty=%s/updated=%s/available=%s/version=%s',
           :'worker',
           :qty,
           count(*),
           coalesce(max(available)::text, 'null'),
           coalesce(max(version)::text, 'null')
       )
FROM changed;

COMMIT;
