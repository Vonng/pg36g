\set ON_ERROR_STOP on
\pset pager off

UPDATE shop_ch15.product_search
SET title = 'unauthorized mutation'
WHERE product_id = 1;
