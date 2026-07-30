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

SELECT
    available AS observed,
    version AS observed_version,
    available - :qty AS replacement
FROM shop_private.ch10_inventory
WHERE sku_id = 1001
\gset

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

WITH changed AS (
    UPDATE shop_private.ch10_inventory
    SET available = :replacement,
        version = version + 1,
        updated_at = timestamptz '2025-01-01 00:03:00+00'
    WHERE sku_id = 1001
      AND version = :observed_version
      AND available >= :qty
    RETURNING available, version
)
SELECT
    count(*) AS updated,
    pg_catalog.format(
        'worker=%s/qty=%s/observed=%s/observed_version=%s/'
        'updated=%s/available=%s/version=%s',
        :'worker',
        :qty,
        :observed,
        :observed_version,
        count(*),
        coalesce(max(available)::text, 'null'),
        coalesce(max(version)::text, 'null')
    ) AS result
FROM changed
\gset

\echo :result
COMMIT;
