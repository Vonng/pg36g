\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\if :{?reset_token}
\else
  \set reset_token ''
\endif

\if :{?reset_target}
\else
  \set reset_target ''
\endif

SELECT
    :'reset_token' =
        'RESET_CH16_SPATIOTEMPORAL_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_ch16+shop_ch16_ext' AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3660',
          MESSAGE =
              'reset refused: invalid ch16 action token';
  END
  $action_guard$;
\endif

\if :target_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3661',
          MESSAGE =
              'reset refused: invalid ch16 target token';
  END
  $action_guard$;
\endif

BEGIN;

DO $active_guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch16-%'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3663',
            MESSAGE =
                'reset refused: ch16 workers are active';
    END IF;
END
$active_guard$;

-- Reuse the exhaustive state, ownership, dependency, privilege, and checksum
-- audit.  Any mismatch aborts this transaction before the first DROP.
\ir verify.sql

DROP VIEW shop_ch16.quarter_hour_volume;
DROP VIEW shop_ch16.event_zone_membership;
DROP VIEW shop_ch16.event_lateness;
DROP TABLE shop_ch16.delivery_event;
DROP TABLE shop_ch16.delivery_hub;
DROP TABLE shop_ch16.geofence_version;
DROP TABLE shop_ch16.event_registry;
DROP TABLE shop_ch16.ingest_attempt;
DROP TABLE shop_ch16.fixture_meta;
DROP SCHEMA shop_ch16;

DROP EXTENSION postgis;
DROP EXTENSION btree_gist;
DROP SCHEMA shop_ch16_ext;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT
    'reset_target=' ||
    'pg36_shop/shop_ch16+shop_ch16_ext';
SELECT 'remaining_data_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace(
                    'shop_ch16'
                ) IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'remaining_extension_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace(
                    'shop_ch16_ext'
                ) IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'remaining_ch16_extensions=' ||
       pg_catalog.count(*)::text
FROM pg_catalog.pg_extension
WHERE extname IN ('btree_gist', 'postgis');
SELECT 'preserved_ch14_extensions=' ||
       pg_catalog.string_agg(
           extname || ':' || extversion,
           ',' ORDER BY extname
       )
FROM pg_catalog.pg_extension
WHERE extname IN ('pg_trgm', 'vector');
