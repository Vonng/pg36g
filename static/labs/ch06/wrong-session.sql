\set ON_ERROR_STOP on
\set VERBOSITY sqlstate
\pset pager off

SET ROLE pg36_owner;
SET client_encoding = 'UTF8';
SET TimeZone = 'Asia/Shanghai';
SET search_path = public;
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;

DO $wrong_session$
BEGIN
    IF pg_catalog.current_setting('TimeZone') <> 'UTC'
       OR current_schemas(false)
          <> ARRAY['pg_catalog', 'shop']::name[]
       OR pg_catalog.current_setting('statement_timeout')::interval
          = interval '0 seconds'
       OR pg_catalog.current_setting('lock_timeout')::interval
          = interval '0 seconds'
       OR pg_catalog.current_setting(
              'idle_in_transaction_session_timeout'
          )::interval = interval '0 seconds' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0601',
            MESSAGE = 'session baseline rejected intentionally wrong state';
    END IF;

    RAISE EXCEPTION USING
        ERRCODE = 'P0602',
        MESSAGE = 'negative session fixture no longer violates the baseline';
END
$wrong_session$;
