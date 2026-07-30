\set ON_ERROR_STOP on

\if :{?confirm_reset}
\else
  \set confirm_reset ''
\endif

SELECT :'confirm_reset' = 'RESET_CH03_MODEL' AS reset_confirmed
\gset

\if :reset_confirmed
  \echo '[reset] confirmation accepted'
\else
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset confirmation is required';
  END
  $reset_error$;
\endif

\ir context.sql

BEGIN;
DROP VIEW IF EXISTS shop_api.order_summary;
DROP TABLE IF EXISTS shop.payment;
DROP TABLE IF EXISTS shop.sales_order_item;
DROP TABLE IF EXISTS shop.sales_order;
DROP TABLE IF EXISTS shop.product;
DROP TABLE IF EXISTS shop.customer;
DROP SCHEMA IF EXISTS shop_api;
DROP SCHEMA IF EXISTS shop_private;
COMMIT;

\echo '[reset] removed ch03 model objects only'
