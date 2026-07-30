\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;
SET enable_bitmapscan = off;
SET enable_sort = off;
EXPLAIN (COSTS OFF)
SELECT
    product.product_id
FROM shop_ch15.product_search AS product
ORDER BY
    product.embedding
        OPERATOR(shop_ch14.<->)
        '[0,0,0.9,0]'::shop_ch14.vector(4)
LIMIT 3;
