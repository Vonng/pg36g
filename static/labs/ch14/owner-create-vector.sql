\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET ROLE pg36_owner;
CREATE EXTENSION vector
    WITH SCHEMA shop_ch14
    VERSION '0.8.4';
