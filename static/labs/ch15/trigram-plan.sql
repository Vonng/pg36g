\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT product.product_id
FROM shop_ch15.product_search AS product
WHERE pg_catalog.lower(product.title)
      OPERATOR(shop_ch14.%)
      pg_catalog.lower('wireles hedphones');
