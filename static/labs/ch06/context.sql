\set ON_ERROR_STOP on
\pset pager off

\if :{?expected_db}
\else
  \set expected_db pg36_shop
\endif

\if :{?owner_role}
\else
  \set owner_role pg36_owner
\endif

SELECT
    current_database() = :'expected_db' AS database_ok,
    NOT pg_catalog.pg_is_in_recovery()  AS writable_instance
\gset

\if :database_ok
\else
  \warn '[context] refused: expected database' :expected_db
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected the current database';
  END
  $context_error$;
\endif

\if :writable_instance
\else
  \warn '[context] refused: the target instance is in recovery'
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected a recovery instance';
  END
  $context_error$;
\endif

SET ROLE :"owner_role";
SET client_encoding = 'UTF8';
SET TimeZone = 'UTC';
SET search_path = pg_catalog, shop;
SET statement_timeout = '30s';
SET lock_timeout = '5s';
SET idle_in_transaction_session_timeout = '60s';

SELECT
    current_user = :'owner_role' AS role_ok,
    current_schemas(false) = ARRAY['pg_catalog', 'shop']::name[] AS path_ok,
    EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) AS model_ok
\gset

\if :role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected the effective role';
  END
  $context_error$;
\endif

\if :path_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected the effective search_path';
  END
  $context_error$;
\endif

\if :model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch06 requires the ch04-v1 model';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s current_user=%s model=ch04-v1',
           current_database(),
           session_user,
           current_user
       ) AS context_line
\gset
\echo :context_line
