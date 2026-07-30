\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

CALL shop_ch13.expire_stale_orders(
    timestamptz '2024-02-01 00:00:00+00',
    2,
    0
);
