\set ON_ERROR_STOP on
\pset pager off

\echo '[setup] ensure the three chapter roles exist'

SELECT 'CREATE ROLE pg36_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pg36_owner'
)
\gexec

SELECT 'CREATE ROLE pg36_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pg36_app'
)
\gexec

SELECT 'CREATE ROLE pg36_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pg36_ro'
)
\gexec

ALTER ROLE pg36_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE pg36_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE pg36_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

COMMENT ON ROLE pg36_owner IS 'pg36_shop object owner; no login';
COMMENT ON ROLE pg36_app IS 'pg36_shop application runtime role';
COMMENT ON ROLE pg36_ro IS 'pg36_shop read-only role';

\echo '[setup] create the database when it is absent'

SELECT $create$
CREATE DATABASE pg36_shop
  OWNER pg36_owner
  TEMPLATE template0
  ENCODING 'UTF8'
$create$
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pg36_shop'
)
\gexec

ALTER DATABASE pg36_shop OWNER TO pg36_owner;
COMMENT ON DATABASE pg36_shop IS 'PostgreSQL 36 Strategies teaching database';
GRANT CONNECT ON DATABASE pg36_shop TO pg36_app, pg36_ro;

\connect pg36_shop

\echo '[setup] establish the business namespace and least-privilege baseline'

CREATE SCHEMA IF NOT EXISTS shop AUTHORIZATION pg36_owner;
ALTER SCHEMA shop OWNER TO pg36_owner;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA shop TO pg36_app, pg36_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pg36_app;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT SELECT ON TABLES TO pg36_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT USAGE, SELECT ON SEQUENCES TO pg36_app;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT SELECT ON SEQUENCES TO pg36_ro;

ALTER ROLE pg36_app IN DATABASE pg36_shop
SET search_path = pg_catalog, shop;

ALTER ROLE pg36_ro IN DATABASE pg36_shop
SET search_path = pg_catalog, shop;

\echo '[setup] complete: roles intentionally have no password in this chapter'
