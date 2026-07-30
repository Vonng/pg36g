\set ON_ERROR_STOP on
\pset pager off

\if :{?confirm_reset}
\else
  \set confirm_reset ''
\endif

SELECT :'confirm_reset' = 'RESET_PG36_SHOP' AS reset_confirmed
\gset

\if :reset_confirmed
  \echo '[reset] confirmation accepted'
\else
  \echo '[reset] refused: pass -v confirm_reset=RESET_PG36_SHOP'
  SELECT 'confirmation_required'::integer;
\endif

\connect postgres

\echo '[reset] terminate sessions connected to the teaching database'

SELECT pg_catalog.pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE datname = 'pg36_shop'
  AND pid <> pg_backend_pid();

\echo '[reset] drop only chapter-owned database and roles'

DROP DATABASE IF EXISTS pg36_shop;
DROP ROLE IF EXISTS pg36_ro;
DROP ROLE IF EXISTS pg36_app;
DROP ROLE IF EXISTS pg36_owner;

\echo '[reset] complete'
