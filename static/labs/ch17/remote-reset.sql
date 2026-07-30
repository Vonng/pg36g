\set ON_ERROR_STOP on
\pset pager off
\ir remote-context.sql

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
        current_database() ||
        '/shop_ch17_shard' AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3660',
          MESSAGE =
              'remote reset refused: invalid ch17 action token';
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
              'remote reset refused: invalid ch17 target token';
  END
  $action_guard$;
\endif

\ir remote-verify.sql

BEGIN;

DROP TABLE shop_ch17_shard.sales_fact;
DROP TABLE shop_ch17_shard.account_dim;
DROP TABLE shop_ch17_shard.fixture_meta;
DROP SCHEMA shop_ch17_shard;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=remote-reset-ok';
SELECT 'database=' || current_database();
SELECT 'remaining_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace(
                    'shop_ch17_shard'
                ) IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'database_shell=retained';
