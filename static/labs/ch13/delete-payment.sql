\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DELETE FROM shop_ch13.payment
WHERE order_id = 102
  AND payment_ref = 'pay-ch13-102';
