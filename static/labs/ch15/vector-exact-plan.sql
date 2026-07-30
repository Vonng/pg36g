\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_indexscan = off;
SET enable_bitmapscan = off;
EXPLAIN (COSTS OFF)
SELECT
    product.product_id,
    product.embedding
        OPERATOR(shop_ch14.<->)
        '[0,0,0.9,0]'::shop_ch14.vector(4) AS distance
FROM shop_ch15.product_search AS product
WHERE product.active
  AND product.category = 'outdoor'
ORDER BY distance, product.product_id
LIMIT 3;
