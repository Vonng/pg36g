\set ON_ERROR_STOP on
\pset pager off

UPDATE shop_ch17.sales_fact_distributed
SET amount = amount + 1
WHERE sale_id = 60001;
