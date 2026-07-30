\set ON_ERROR_STOP on
\ir context.sql

\pset format unaligned
\pset tuples_only on
\set VERBOSITY sqlstate
\set ON_ERROR_STOP off

\echo autocommit_client_setting=:AUTOCOMMIT
\echo failed_transaction_probe=begin

BEGIN;
SELECT 1 / 0;
SELECT 'this statement must receive SQLSTATE 25P02';
ROLLBACK;

\echo failed_transaction_recovered=true
\echo savepoint_probe=begin

BEGIN;
SAVEPOINT risky_statement;

UPDATE shop.product
SET currency_code = 'USD'
WHERE product_id = 101;

ROLLBACK TO SAVEPOINT risky_statement;

UPDATE shop.sales_order
SET request_fingerprint =
        pg_catalog.md5('ch05-savepoint-' || order_id::text)
WHERE order_id = 1002
RETURNING 'savepoint_recovered_write=' || (order_id = 1002)::text;

ROLLBACK;

SELECT 'state_restored=' ||
       (
           request_fingerprint =
           pg_catalog.md5('bob|gift:1')
       )::text
FROM shop.sales_order
WHERE order_id = 1002;

\set ON_ERROR_STOP on
