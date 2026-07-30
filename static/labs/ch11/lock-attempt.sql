\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET lock_timeout = '4s';
SET statement_timeout = '8s';

ALTER TABLE shop_private.ch11_order
    ADD COLUMN shipping_code text;
