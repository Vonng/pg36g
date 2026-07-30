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
SET search_path = pg_catalog, shop;

SELECT
    current_user = :'owner_role' AS role_ok,
    current_schemas(false) = ARRAY['pg_catalog', 'shop']::name[] AS path_ok
\gset

\if :role_ok
\else
  \warn '[context] refused: effective role is not' :owner_role
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected the effective role';
  END
  $context_error$;
\endif

\if :path_ok
\else
  \warn '[context] refused: effective search_path is not pg_catalog, shop'
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'context guard rejected the effective search_path';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s current_user=%s search_path=%s',
           current_database(),
           session_user,
           current_user,
           current_setting('search_path')
       ) AS context_line
\gset
\echo :context_line
