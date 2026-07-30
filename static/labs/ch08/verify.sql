\set ON_ERROR_STOP on
\ir ../ch05/verify.sql
\ir ../ch07/verify.sql

DO $verify$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND (
              application_name LIKE 'pg36-ch08-%'
              OR application_name LIKE 'pg36-ch05-blocker-%'
              OR application_name LIKE 'pg36-ch05-waiter-%'
          )
    ) THEN
        RAISE EXCEPTION 'a ch08 diagnostic worker is still connected';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'fixture=ch08-diagnosis-v1';
SELECT 'persistent_objects=none';
SELECT 'active_lab_workers=0';
