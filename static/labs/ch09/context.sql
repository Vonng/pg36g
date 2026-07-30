\set ON_ERROR_STOP on
\ir ../ch06/context.sql

SELECT
    current_setting('server_version_num')::integer >= 140000
        AS supported_version,
    NOT pg_catalog.pg_is_in_recovery() AS writable_primary
\gset

\if :supported_version
\else
  DO $ch09_context_error$
  BEGIN
      RAISE EXCEPTION 'ch09 requires PostgreSQL 14 or newer';
  END
  $ch09_context_error$;
\endif

\if :writable_primary
\else
  DO $ch09_context_error$
  BEGIN
      RAISE EXCEPTION 'ch09 requires a writable L1 primary';
  END
  $ch09_context_error$;
\endif
