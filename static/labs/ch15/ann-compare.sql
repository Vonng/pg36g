\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;
SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;
SET LOCAL enable_sort = off;
SET LOCAL hnsw.iterative_scan = 'strict_order';

WITH exact_result AS (
    SELECT product_id
    FROM shop_ch15.vector_exact_ranking
    WHERE query_id = 'q06'
      AND result_rank <= 3
),
ann_result AS MATERIALIZED (
    SELECT product.product_id
    FROM shop_ch15.product_search AS product
    WHERE product.active
      AND product.category = 'outdoor'
    ORDER BY
        product.embedding
            OPERATOR(shop_ch14.<->)
            '[0,0,0.9,0]'::shop_ch14.vector(4)
    LIMIT 3
)
SELECT
    (
        SELECT pg_catalog.string_agg(
                   product_id::text,
                   ',' ORDER BY product_id
               )
        FROM exact_result
    ) AS exact_ids,
    (
        SELECT pg_catalog.string_agg(
                   product_id::text,
                   ',' ORDER BY product_id
               )
        FROM ann_result
    ) AS ann_ids,
    (
        SELECT pg_catalog.round(
                   pg_catalog.count(*)::numeric / 3,
                   6
               )
        FROM exact_result AS exact
        JOIN ann_result AS ann
          USING (product_id)
    ) AS recall_at_3;

ROLLBACK;
