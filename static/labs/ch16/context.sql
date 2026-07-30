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
      RAISE EXCEPTION 'ch16 context guard rejected the database';
  END
  $context_error$;
\endif

\if :writable_instance
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch16 context guard rejected a recovery instance';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 formal fixture requires PostgreSQL 14 through 18';
  END
  $context_error$;
\endif

\if :superuser_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 administration path requires a superuser session';
  END
  $context_error$;
\endif

\if :can_set_owner
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 session cannot SET ROLE to the object owner';
  END
  $context_error$;
\endif

SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET DateStyle = 'ISO, YMD';
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
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'btree_gist'
          AND version = '1.8'
          AND superuser
          AND trusted
          AND relocatable
    ) AS btree_available,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'postgis'
          AND version = '3.6.4'
          AND superuser
          AND NOT trusted
          AND NOT relocatable
    ) AS postgis_available,
    NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = extension_catalog.extnamespace
        WHERE extension_catalog.extname = 'btree_gist'
          AND (
              extension_catalog.extversion <> '1.8'
              OR namespace.nspname <> 'shop_ch16_ext'
              OR pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) IS DISTINCT FROM
                 'pg36 ch16 spatiotemporal lab; safe to rebuild'
          )
    ) AS btree_state_ok,
    NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = extension_catalog.extnamespace
        WHERE extension_catalog.extname = 'postgis'
          AND (
              extension_catalog.extversion <> '3.6.4'
              OR namespace.nspname <> 'shop_ch16_ext'
              OR pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) IS DISTINCT FROM
                 'pg36 ch16 spatiotemporal lab; safe to rebuild'
          )
    ) AS postgis_state_ok
\gset

\if :model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch16 requires the ch04-v1 model';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 requires a constrained pg36_app LOGIN role';
  END
  $context_error$;
\endif

\if :btree_available
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 requires btree_gist 1.8 support files';
  END
  $context_error$;
\endif

\if :postgis_available
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 requires PostGIS 3.6.4 support files';
  END
  $context_error$;
\endif

\if :btree_state_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 found an unmanaged btree_gist installation';
  END
  $context_error$;
\endif

\if :postgis_state_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch16 found an unmanaged PostGIS installation';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s owner=%s model=ch04-v1 postgis_support=3.6.4 btree_gist_support=1.8 server=%s',
           current_database(),
           session_user,
           :'owner_role',
           current_setting('server_version')
       ) AS context_line
\gset
\echo :context_line
