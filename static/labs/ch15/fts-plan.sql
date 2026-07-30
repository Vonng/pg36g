\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT product.product_id
FROM shop_ch15.product_search AS product
WHERE product.search_document
      @@
      pg_catalog.websearch_to_tsquery(
          'pg_catalog.english'::pg_catalog.regconfig,
          'coffee bean grinder'
      );
