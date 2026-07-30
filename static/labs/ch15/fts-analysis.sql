\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    query.query_id,
    query.raw_query,
    pg_catalog.websearch_to_tsquery(
        'pg_catalog.english'::pg_catalog.regconfig,
        query.raw_query
    )::text AS parsed_query,
    pg_catalog.numnode(
        pg_catalog.websearch_to_tsquery(
            'pg_catalog.english'::pg_catalog.regconfig,
            query.raw_query
        )
    ) AS node_count,
    (
        SELECT pg_catalog.count(*)
        FROM shop_ch15.product_search AS product
        WHERE product.active
          AND product.category = query.category_filter
          AND product.search_document
              @@
              pg_catalog.websearch_to_tsquery(
                  'pg_catalog.english'::pg_catalog.regconfig,
                  query.raw_query
              )
    ) AS matched_products
FROM shop_ch15.eval_query AS query
ORDER BY query.query_id;
