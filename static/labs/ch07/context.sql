\set ON_ERROR_STOP on
\ir ../ch06/context.sql

SELECT
    current_setting('server_version_num')::integer >= 140000
        AS supported_version,
    current_setting('enable_partition_pruning') = 'on'
        AS pruning_enabled
\gset

\if :supported_version
\else
  DO $ch07_context_error$
  BEGIN
      RAISE EXCEPTION 'ch07 requires PostgreSQL 14 or newer';
  END
  $ch07_context_error$;
\endif

\if :pruning_enabled
\else
  DO $ch07_context_error$
  BEGIN
      RAISE EXCEPTION 'ch07 requires enable_partition_pruning=on';
  END
  $ch07_context_error$;
\endif
