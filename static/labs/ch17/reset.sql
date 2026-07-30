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
        'RESET_CH17_ANALYTICS_FDW_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_ch17+shop_ch17_ext+fdw'
        AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3660',
          MESSAGE =
              'reset refused: invalid ch17 action token';
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
              'reset refused: invalid ch17 target token';
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
          AND application_name LIKE 'pg36-ch17-%'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3663',
            MESSAGE =
                'reset refused: ch17 workers are active';
    END IF;
END
$active_guard$;

\ir verify.sql

DROP VIEW shop_ch17.distributed_tenant_month;
DROP VIEW shop_ch17.local_tenant_month;
DROP MATERIALIZED VIEW
    shop_ch17.daily_tenant_summary;
DROP TABLE shop_ch17.sales_fact_distributed;
DROP TABLE shop_ch17.account_dim_distributed;
DROP TABLE shop_ch17.sales_fact;
DROP TABLE shop_ch17.account_dim;
DROP TABLE shop_ch17.fixture_meta;
DROP SCHEMA shop_ch17;

DROP USER MAPPING
    FOR postgres SERVER pg36_ch17_shard_a;
DROP USER MAPPING
    FOR pg36_owner SERVER pg36_ch17_shard_a;
DROP USER MAPPING
    FOR pg36_app SERVER pg36_ch17_shard_a;
DROP USER MAPPING
    FOR postgres SERVER pg36_ch17_shard_b;
DROP USER MAPPING
    FOR pg36_owner SERVER pg36_ch17_shard_b;
DROP USER MAPPING
    FOR pg36_app SERVER pg36_ch17_shard_b;
DROP SERVER pg36_ch17_shard_a;
DROP SERVER pg36_ch17_shard_b;

DROP EXTENSION postgres_fdw;
DROP SCHEMA shop_ch17_ext;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=coordinator-reset-ok';
SELECT 'remaining_data_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace(
                    'shop_ch17'
                ) IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'remaining_extension_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace(
                    'shop_ch17_ext'
                ) IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'remaining_ch17_servers=' ||
       pg_catalog.count(*)::text
FROM pg_catalog.pg_foreign_server
WHERE srvname IN (
    'pg36_ch17_shard_a',
    'pg36_ch17_shard_b'
);
SELECT 'retained_shard_databases=' ||
       pg_catalog.string_agg(
           datname,
           ',' ORDER BY datname
       )
FROM pg_catalog.pg_database
WHERE datname IN ('pg36_shard_a', 'pg36_shard_b');
