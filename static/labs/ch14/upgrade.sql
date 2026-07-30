\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    (
        SELECT extversion = '1.3'
        FROM pg_catalog.pg_extension
        WHERE extname = 'pg_trgm'
    ) AS source_version_ok
\gset

\if :source_version_ok
\else
  DO $upgrade_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3640',
          MESSAGE = 'pg_trgm source version is not 1.3';
  END
  $upgrade_guard$;
\endif

SET ROLE pg36_owner;
ALTER EXTENSION pg_trgm UPDATE TO '1.6';
RESET ROLE;

\pset format unaligned
\pset tuples_only on
SELECT 'status=upgraded';
SELECT 'pg_trgm_version=' || extversion
FROM pg_catalog.pg_extension
WHERE extname = 'pg_trgm';
