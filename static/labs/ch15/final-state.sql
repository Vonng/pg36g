\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH business_rows AS (
    SELECT
        'product'::text AS kind,
        pg_catalog.lpad(product_id::text, 4, '0') AS sort_key,
        pg_catalog.concat_ws(
            '|',
            product_id,
            sku,
            category,
            active,
            title,
            description,
            embedding::text,
            embedding_model
        ) AS payload
    FROM shop_ch15.product_search

    UNION ALL

    SELECT
        'query',
        query_id,
        pg_catalog.concat_ws(
            '|',
            query_id,
            raw_query,
            coalesce(category_filter, ''),
            embedding::text,
            embedding_model,
            intent
        )
    FROM shop_ch15.eval_query

    UNION ALL

    SELECT
        'judgment',
        query_id || '|' ||
            pg_catalog.lpad(product_id::text, 4, '0'),
        pg_catalog.concat_ws(
            '|',
            query_id,
            product_id,
            grade,
            rationale
        )
    FROM shop_ch15.relevance_judgment

    UNION ALL

    SELECT
        'ranking',
        strategy || '|' || query_id || '|' ||
            pg_catalog.lpad(result_rank::text, 4, '0'),
        pg_catalog.concat_ws(
            '|',
            strategy,
            query_id,
            product_id,
            result_rank,
            pg_catalog.round(score::numeric, 8),
            pg_catalog.array_to_string(sources, '+')
        )
    FROM shop_ch15.all_ranking
    WHERE result_rank <= 3

    UNION ALL

    SELECT
        'quality',
        strategy,
        pg_catalog.concat_ws(
            '|',
            strategy,
            query_count,
            mean_precision_at_3,
            mean_recall_at_3,
            mrr_at_3,
            mean_ndcg_at_3,
            min_ndcg_at_3
        )
    FROM shop_ch15.quality_summary
),
business_checksum AS (
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           ) AS checksum
    FROM business_rows
),
top_ids AS (
    SELECT
        strategy,
        query_id,
        pg_catalog.string_agg(
            product_id::text,
            ',' ORDER BY result_rank
        ) AS ids
    FROM shop_ch15.all_ranking
    WHERE result_rank <= 3
    GROUP BY strategy, query_id
),
fact AS (
    SELECT
        'release'::text AS key,
        '1.3-proposal'::text AS value

    UNION ALL

    SELECT 'fixture', fixture_version
    FROM shop_ch15.fixture_meta

    UNION ALL

    SELECT 'embedding_model', embedding_model
    FROM shop_ch15.fixture_meta

    UNION ALL

    SELECT 'products', pg_catalog.count(*)::text
    FROM shop_ch15.product_search

    UNION ALL

    SELECT
        'active_products',
        pg_catalog.count(*) FILTER (WHERE active)::text
    FROM shop_ch15.product_search

    UNION ALL

    SELECT 'queries', pg_catalog.count(*)::text
    FROM shop_ch15.eval_query

    UNION ALL

    SELECT 'judgments', pg_catalog.count(*)::text
    FROM shop_ch15.relevance_judgment

    UNION ALL

    SELECT
        'hybrid_top_ids',
        pg_catalog.string_agg(
            query_id || '=' || ids,
            ';' ORDER BY query_id
        )
    FROM top_ids
    WHERE strategy = 'hybrid_rrf'

    UNION ALL

    SELECT
        'quality',
        pg_catalog.string_agg(
            strategy || '=' ||
            mean_recall_at_3::text || '/' ||
            mrr_at_3::text || '/' ||
            mean_ndcg_at_3::text,
            ';' ORDER BY strategy
        )
    FROM shop_ch15.quality_summary

    UNION ALL

    SELECT 'business_checksum', checksum
    FROM business_checksum
)
SELECT key, value
FROM fact
ORDER BY key;
