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
    NOT pg_catalog.pg_is_in_recovery() AS writable_instance,
    current_setting('server_version_num')::integer
        BETWEEN 140000 AND 189999 AS version_ok,
    (
        SELECT role.rolsuper
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = session_user
    ) AS superuser_ok,
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
      RAISE EXCEPTION 'ch15 context guard rejected the database';
  END
  $context_error$;
\endif

\if :writable_instance
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch15 context guard rejected a recovery instance';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 formal fixture requires PostgreSQL 14 through 18';
  END
  $context_error$;
\endif

\if :superuser_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 administration path requires a superuser session';
  END
  $context_error$;
\endif

\if :can_set_owner
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 session cannot SET ROLE to the object owner';
  END
  $context_error$;
\endif

SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET statement_timeout = '30s';
SET lock_timeout = '5s';
SET idle_in_transaction_session_timeout = '30s';

SELECT
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
    ) AS app_role_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace AS namespace
        WHERE namespace.nspname = 'shop_ch14'
          AND pg_catalog.obj_description(
                  namespace.oid,
                  'pg_namespace'
              ) =
              'pg36 ch14 extension lifecycle lab; safe to rebuild'
    ) AS ch14_schema_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = extension_catalog.extnamespace
        WHERE extension_catalog.extname = 'pg_trgm'
          AND extension_catalog.extversion = '1.6'
          AND namespace.nspname = 'shop_ch14'
          AND pg_catalog.obj_description(
                  extension_catalog.oid,
                  'pg_extension'
              ) =
              'pg36 ch14 extension lifecycle lab; safe to rebuild'
    ) AS pg_trgm_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = extension_catalog.extnamespace
        WHERE extension_catalog.extname = 'vector'
          AND extension_catalog.extversion = '0.8.4'
          AND namespace.nspname = 'shop_ch14'
          AND pg_catalog.obj_description(
                  extension_catalog.oid,
                  'pg_extension'
              ) =
              'pg36 ch14 extension lifecycle lab; safe to rebuild'
    ) AS vector_ok
\gset

\if :model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch15 requires the ch04-v1 model';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 requires a constrained pg36_app LOGIN role';
  END
  $context_error$;
\endif

\if :ch14_schema_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 requires the verified ch14 extension schema';
  END
  $context_error$;
\endif

\if :pg_trgm_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 requires verified pg_trgm 1.6 from ch14';
  END
  $context_error$;
\endif

\if :vector_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch15 requires verified vector 0.8.4 from ch14';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s owner=%s model=ch04-v1 extensions=pg_trgm-1.6+vector-0.8.4 model_id=pg36-handcrafted-topic-4d-v1 server=%s',
           current_database(),
           session_user,
           :'owner_role',
           current_setting('server_version')
       ) AS context_line
\gset
\echo :context_line
