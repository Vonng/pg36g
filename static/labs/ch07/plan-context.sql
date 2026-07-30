\set ON_ERROR_STOP on

SELECT
    current_database() = 'pg36_shop' AS database_ok,
    NOT pg_catalog.pg_is_in_recovery() AS writable_ok,
    EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) AS model_ok
\gset

\if :database_ok
\else
  DO $ch07_plan_context_error$
  BEGIN
      RAISE EXCEPTION 'ch07 plan capture rejected database';
  END
  $ch07_plan_context_error$;
\endif

\if :writable_ok
\else
  DO $ch07_plan_context_error$
  BEGIN
      RAISE EXCEPTION 'ch07 plan capture rejected recovery target';
  END
  $ch07_plan_context_error$;
\endif

\if :model_ok
\else
  DO $ch07_plan_context_error$
  BEGIN
      RAISE EXCEPTION 'ch07 plan capture requires ch04-v1';
  END
  $ch07_plan_context_error$;
\endif

SET ROLE pg36_owner;
SET client_encoding = 'UTF8';
SET TimeZone = 'UTC';
SET search_path = pg_catalog, shop_private;
SET statement_timeout = '30s';
SET lock_timeout = '5s';
SET idle_in_transaction_session_timeout = '60s';
