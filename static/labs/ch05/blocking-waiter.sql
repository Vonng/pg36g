\set ON_ERROR_STOP on
\ir context.sql

\if :{?target_order_id}
\else
  \set target_order_id 1002
\endif

\pset format unaligned
\pset tuples_only on

BEGIN;
SET LOCAL lock_timeout = '50s';
SET LOCAL statement_timeout = '55s';

UPDATE shop.sales_order
SET request_fingerprint =
        pg_catalog.md5(
            'ch05-rolled-back-waiter-' ||
            pg_catalog.pg_backend_pid()::text
        )
WHERE order_id = :target_order_id
RETURNING
    'waiter_acquired_order=' || order_id::text ||
    '|backend_pid=' || pg_catalog.pg_backend_pid()::text;

ROLLBACK;
