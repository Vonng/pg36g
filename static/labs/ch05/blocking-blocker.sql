\set ON_ERROR_STOP on
\ir context.sql

\if :{?target_order_id}
\else
  \set target_order_id 1002
\endif

\if :{?hold_seconds}
\else
  \set hold_seconds 45
\endif

\pset format unaligned
\pset tuples_only on
\set VERBOSITY sqlstate

BEGIN;
SET LOCAL statement_timeout = '60s';

UPDATE shop.sales_order
SET request_fingerprint =
        pg_catalog.md5(
            'ch05-uncommitted-blocker-' ||
            pg_catalog.pg_backend_pid()::text
        )
WHERE order_id = :target_order_id
RETURNING
    'blocker_holds_order=' || order_id::text ||
    '|backend_pid=' || pg_catalog.pg_backend_pid()::text ||
    '|tuple_xmin=' || xmin::text;

SELECT pg_catalog.pg_sleep(:hold_seconds);

ROLLBACK;
