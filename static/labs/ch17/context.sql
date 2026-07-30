\set ON_ERROR_STOP on
\pset pager off

\if :{?fdw_host}
\else
  \set fdw_host ''
\endif

\if :{?fdw_port}
\else
  \set fdw_port ''
\endif

SELECT
    current_database() = 'pg36_shop' AS database_ok,
    NOT pg_catalog.pg_is_in_recovery() AS writable_ok,
    current_setting('server_version_num')::integer
        BETWEEN 180000 AND 189999 AS version_ok,
    (
        SELECT role.rolsuper
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = session_user
    ) AS admin_ok,
    session_user = 'postgres' AS admin_identity_ok,
    pg_catalog.pg_has_role(
        session_user,
        'pg36_owner',
        'MEMBER'
    ) AS owner_membership_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'pg36_app'
          AND rolcanlogin
          AND NOT rolsuper
    ) AS app_role_ok,
    EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) AS ch04_model_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'postgres_fdw'
          AND version = '1.2'
    ) AS fdw_available,
    (
        NOT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_extension
            WHERE extname = 'postgres_fdw'
        )
        OR EXISTS (
            SELECT 1
            FROM pg_catalog.pg_extension AS extension_catalog
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid =
                     extension_catalog.extnamespace
            WHERE extension_catalog.extname = 'postgres_fdw'
              AND extension_catalog.extversion = '1.2'
              AND namespace.nspname = 'shop_ch17_ext'
              AND pg_catalog.obj_description(
                      extension_catalog.oid,
                      'pg_extension'
                  ) =
                  'pg36 ch17 analytics fdw lab; safe to rebuild'
        )
    ) AS fdw_state_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_database AS database_catalog
        WHERE database_catalog.datname = 'pg36_shard_a'
          AND pg_catalog.pg_get_userbyid(
                  database_catalog.datdba
              ) = 'pg36_owner'
          AND pg_catalog.shobj_description(
                  database_catalog.oid,
                  'pg_database'
              ) =
              'pg36 ch17 fdw shard database a; retained shell'
    ) AS shard_a_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_database AS database_catalog
        WHERE database_catalog.datname = 'pg36_shard_b'
          AND pg_catalog.pg_get_userbyid(
                  database_catalog.datdba
              ) = 'pg36_owner'
          AND pg_catalog.shobj_description(
                  database_catalog.oid,
                  'pg_database'
              ) =
              'pg36 ch17 fdw shard database b; retained shell'
    ) AS shard_b_ok,
    (
        :'fdw_host' = current_setting(
            'unix_socket_directories'
        )
    ) AS fdw_host_ok,
    (
        :'fdw_port' = current_setting('port')
    ) AS fdw_port_ok
\gset

\if :database_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 expected database pg36_shop';
  END
  $context_error$;
\endif

\if :writable_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 requires a writable primary';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 formal fixture requires PostgreSQL 18.x';
  END
  $context_error$;
\endif

\if :admin_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 requires a superuser session';
  END
  $context_error$;
\endif

\if :admin_identity_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 formal fixture requires session_user postgres';
  END
  $context_error$;
\endif

\if :owner_membership_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 session cannot SET ROLE pg36_owner';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 pg36_app role contract drifted';
  END
  $context_error$;
\endif

\if :ch04_model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 requires the ch04-v1 model';
  END
  $context_error$;
\endif

\if :fdw_available
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 requires postgres_fdw 1.2 availability';
  END
  $context_error$;
\endif

\if :fdw_state_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 postgres_fdw installation drifted';
  END
  $context_error$;
\endif

\if :shard_a_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 pg36_shard_a identity drifted';
  END
  $context_error$;
\endif

\if :shard_b_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 pg36_shard_b identity drifted';
  END
  $context_error$;
\endif

\if :fdw_host_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 fdw_host does not match this lab server';
  END
  $context_error$;
\endif

\if :fdw_port_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 fdw_port does not match this lab server';
  END
  $context_error$;
\endif

SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET DateStyle = 'ISO, YMD';
SET lock_timeout = '5s';
SET statement_timeout = '120s';
SET idle_in_transaction_session_timeout = '30s';

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s model=ch04-v1 fdw=1.2 shards=a+b server=%s',
           current_database(),
           session_user,
           current_setting('server_version')
       ) AS context
\gset
\echo :context
