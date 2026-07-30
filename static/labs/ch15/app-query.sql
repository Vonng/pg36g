\set ON_ERROR_STOP on
\pset pager off

SET search_path = pg_catalog;
SET statement_timeout = '30s';

SELECT
    ranking.query_id,
    ranking.result_rank,
    ranking.product_id,
    product.title,
    pg_catalog.round(
        ranking.score::numeric,
        8
    ) AS rrf_score,
    pg_catalog.array_to_string(
        ranking.sources,
        '+'
    ) AS sources
FROM shop_ch15.hybrid_rrf_ranking AS ranking
JOIN shop_ch15.product_search AS product
  ON product.product_id = ranking.product_id
WHERE ranking.query_id IN ('q02', 'q08')
  AND ranking.result_rank <= 3
ORDER BY ranking.query_id, ranking.result_rank;

SELECT
    strategy,
    mean_recall_at_3,
    mrr_at_3,
    mean_ndcg_at_3
FROM shop_ch15.quality_summary
ORDER BY strategy;
