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
    ) AS can_set_owner,
    pg_catalog.has_database_privilege(
        :'owner_role',
        current_database(),
        'CREATE'
    ) AS owner_can_create
\gset

\if :database_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch14 context guard rejected the database';
  END
  $context_error$;
\endif

\if :writable_instance
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch14 context guard rejected a recovery instance';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 formal fixture requires PostgreSQL 14 through 18';
  END
  $context_error$;
\endif

\if :superuser_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 administration path requires a superuser session';
  END
  $context_error$;
\endif

\if :can_set_owner
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 session cannot SET ROLE to the object owner';
  END
  $context_error$;
\endif

\if :owner_can_create
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 owner role lacks CREATE on the target database';
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
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'pg_trgm'
          AND version = '1.3'
          AND superuser
          AND trusted
          AND relocatable
    ) AS pg_trgm_13_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'pg_trgm'
          AND version = '1.6'
          AND superuser
          AND trusted
          AND relocatable
    ) AS pg_trgm_16_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'vector'
          AND version = '0.8.4'
          AND superuser
          AND NOT trusted
          AND relocatable
    ) AS vector_084_ok
\gset

\if :model_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch14 requires the ch04-v1 model';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 requires a constrained pg36_app LOGIN role';
  END
  $context_error$;
\endif

\if :pg_trgm_13_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 baseline requires trusted pg_trgm version 1.3';
  END
  $context_error$;
\endif

\if :pg_trgm_16_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 baseline requires trusted pg_trgm version 1.6';
  END
  $context_error$;
\endif

\if :vector_084_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch14 baseline requires untrusted vector version 0.8.4';
  END
  $context_error$;
\endif

SELECT pg_catalog.format(
           '[context] database=%s session_user=%s owner=%s model=ch04-v1 pg_trgm=1.3->1.6 vector=0.8.4 server=%s',
           current_database(),
           session_user,
           :'owner_role',
           current_setting('server_version')
       ) AS context_line
\gset
\echo :context_line
