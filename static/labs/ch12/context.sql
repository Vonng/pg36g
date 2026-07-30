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

\if :{?app_role}
\else
  \set app_role pg36_app
\endif

SELECT
    current_database() = :'expected_db' AS database_ok,
    NOT pg_catalog.pg_is_in_recovery()  AS writable_instance,
    current_setting('server_version_num')::integer >= 140000
        AS version_ok,
    pg_catalog.pg_has_role(
        session_user,
        :'owner_role',
        'SET'
    ) AS can_set_owner
\gset

\if :database_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 context guard rejected the database';
  END
  $context_error$;
\endif

\if :writable_instance
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 context guard rejected a recovery instance';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 requires PostgreSQL 14 or later';
  END
  $context_error$;
\endif

\if :can_set_owner
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 session cannot SET ROLE to the object owner';
  END
  $context_error$;
\endif

SET ROLE :"owner_role";
SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET statement_timeout = '30s';
SET lock_timeout = '5s';
SET idle_in_transaction_session_timeout = '30s';

SELECT
    current_user = :'owner_role' AS role_ok,
    EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) AS model_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = :'app_role'
          AND rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolreplication
          AND NOT rolbypassrls
    ) AS app_role_ok
\gset

\if :role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 context guard rejected the effective role';
  END
  $context_error$;
\endif

\if :model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 requires the ch04-v1 model';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch12 requires a constrained pg36_app LOGIN role';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s current_user=%s model=ch04-v1 app_role=%s server=%s',
           current_database(),
           session_user,
           current_user,
           :'app_role',
           current_setting('server_version')
       ) AS context_line
\gset
\echo :context_line
