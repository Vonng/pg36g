\set ON_ERROR_STOP on
\ir context.sql

SELECT
    pg_catalog.current_setting('application_name')
        LIKE 'pg36-ch06-%' AS application_ok,
    pg_catalog.current_setting('client_encoding') = 'UTF8'
        AS encoding_ok,
    pg_catalog.current_setting('TimeZone') = 'UTC'
        AS timezone_ok,
    current_schemas(false) = ARRAY['pg_catalog', 'shop']::name[]
        AS path_ok,
    pg_catalog.current_setting('statement_timeout')::interval
        = interval '30 seconds' AS statement_timeout_ok,
    pg_catalog.current_setting('lock_timeout')::interval
        = interval '5 seconds' AS lock_timeout_ok,
    pg_catalog.current_setting(
        'idle_in_transaction_session_timeout'
    )::interval = interval '60 seconds' AS idle_timeout_ok,
    pg_catalog.current_setting('standard_conforming_strings') = 'on'
        AS strings_ok
\gset

\if :application_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected application_name';
  END
  $session_error$;
\endif

\if :encoding_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected client_encoding';
  END
  $session_error$;
\endif

\if :timezone_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected TimeZone';
  END
  $session_error$;
\endif

\if :path_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected search_path';
  END
  $session_error$;
\endif

\if :statement_timeout_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected statement_timeout';
  END
  $session_error$;
\endif

\if :lock_timeout_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected lock_timeout';
  END
  $session_error$;
\endif

\if :idle_timeout_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected idle transaction timeout';
  END
  $session_error$;
\endif

\if :strings_ok
\else
  DO $session_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0601',
          MESSAGE = 'session baseline rejected string semantics';
  END
  $session_error$;
\endif

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'database=' || current_database();
SELECT 'effective_role=' || current_user;
SELECT 'application_name=' ||
       pg_catalog.current_setting('application_name');
SELECT 'client_encoding=' ||
       pg_catalog.current_setting('client_encoding');
SELECT 'timezone=' || pg_catalog.current_setting('TimeZone');
SELECT 'search_path=' || pg_catalog.current_setting('search_path');
SELECT 'statement_timeout=' ||
       pg_catalog.current_setting('statement_timeout');
SELECT 'lock_timeout=' ||
       pg_catalog.current_setting('lock_timeout');
SELECT 'idle_in_transaction_session_timeout=' ||
       pg_catalog.current_setting(
           'idle_in_transaction_session_timeout'
       );
