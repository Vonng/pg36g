\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    'product_heap'::text AS object_name,
    pg_catalog.pg_relation_size(
        'shop_ch15.product_search'::pg_catalog.regclass
    ) AS bytes
UNION ALL
SELECT
    'product_total',
    pg_catalog.pg_total_relation_size(
        'shop_ch15.product_search'::pg_catalog.regclass
    )
UNION ALL
SELECT
    'fts_gin',
    pg_catalog.pg_relation_size(
        'shop_ch15.product_search_fts_idx'::pg_catalog.regclass
    )
UNION ALL
SELECT
    'trigram_gin',
    pg_catalog.pg_relation_size(
        'shop_ch15.product_search_title_trgm_idx'::pg_catalog.regclass
    )
UNION ALL
SELECT
    'vector_hnsw',
    pg_catalog.pg_relation_size(
        'shop_ch15.product_search_embedding_hnsw_idx'::pg_catalog.regclass
    )
UNION ALL
SELECT
    'filter_btree',
    pg_catalog.pg_relation_size(
        'shop_ch15.product_search_filter_idx'::pg_catalog.regclass
    )
ORDER BY object_name;
