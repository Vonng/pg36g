\set ON_ERROR_STOP on
\pset pager off

\if :{?expected_database}
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 expected_database variable is required';
  END
  $context_error$;
\endif

\if :{?shard_remainder}
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 shard_remainder variable is required';
  END
  $context_error$;
\endif

\if :{?shard_marker}
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 shard_marker variable is required';
  END
  $context_error$;
\endif

SELECT
    current_database() = :'expected_database' AS database_ok,
    NOT pg_catalog.pg_is_in_recovery() AS writable_ok,
    current_setting('server_version_num')::integer
        BETWEEN 180000 AND 189999 AS version_ok,
    (
        SELECT role.rolsuper
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = session_user
    ) AS admin_ok,
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
    (
        SELECT
            pg_catalog.pg_get_userbyid(
                database_catalog.datdba
            ) = 'pg36_owner'
            AND pg_catalog.shobj_description(
                    database_catalog.oid,
                    'pg_database'
                ) = CASE :'expected_database'
                        WHEN 'pg36_shard_a'
                            THEN
                              'pg36 ch17 fdw shard database a; retained shell'
                        WHEN 'pg36_shard_b'
                            THEN
                              'pg36 ch17 fdw shard database b; retained shell'
                        ELSE NULL
                    END
        FROM pg_catalog.pg_database AS database_catalog
        WHERE database_catalog.datname = current_database()
    ) AS database_identity_ok
\gset

\if :database_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION 'ch17 remote database mismatch';
  END
  $context_error$;
\endif

\if :writable_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote requires a writable primary';
  END
  $context_error$;
\endif

\if :version_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote fixture requires PostgreSQL 18.x';
  END
  $context_error$;
\endif

\if :admin_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote requires a superuser session';
  END
  $context_error$;
\endif

\if :owner_membership_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote cannot SET ROLE pg36_owner';
  END
  $context_error$;
\endif

\if :app_role_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote pg36_app role contract drifted';
  END
  $context_error$;
\endif

\if :database_identity_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 remote database identity drifted';
  END
  $context_error$;
\endif

SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET DateStyle = 'ISO, YMD';
SET lock_timeout = '5s';
SET statement_timeout = '120s';
SET idle_in_transaction_session_timeout = '30s';

\echo [remote-context] database=:DBNAME remainder=:shard_remainder
