\set ON_ERROR_STOP on

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'test'
  AND application_name LIKE 'pg36_ch22_%'
  AND pid <> pg_backend_pid();

DROP SCHEMA IF EXISTS pg36_ch22 CASCADE;
