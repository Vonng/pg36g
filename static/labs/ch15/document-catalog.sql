\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    product.product_id,
    product.category,
    product.active,
    product.title,
    product.search_document::text AS search_document,
    product.embedding::text AS embedding,
    product.embedding_model
FROM shop_ch15.product_search AS product
ORDER BY product.product_id;
