\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    ranking.strategy,
    ranking.query_id,
    query.raw_query,
    ranking.result_rank,
    ranking.product_id,
    product.title,
    pg_catalog.round(
        ranking.score::numeric,
        8
    ) AS score,
    coalesce(judgment.grade, 0) AS relevance_grade,
    pg_catalog.array_to_string(
        ranking.sources,
        '+'
    ) AS sources
FROM shop_ch15.all_ranking AS ranking
JOIN shop_ch15.eval_query AS query
  ON query.query_id = ranking.query_id
JOIN shop_ch15.product_search AS product
  ON product.product_id = ranking.product_id
LEFT JOIN shop_ch15.relevance_judgment AS judgment
  ON judgment.query_id = ranking.query_id
 AND judgment.product_id = ranking.product_id
WHERE ranking.result_rank <= 3
ORDER BY
    ranking.strategy,
    ranking.query_id,
    ranking.result_rank;
