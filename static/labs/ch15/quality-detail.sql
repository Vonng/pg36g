\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    strategy,
    query_id,
    result_count,
    relevant_retrieved,
    relevant_count,
    precision_at_3,
    recall_at_3,
    reciprocal_rank_at_3,
    ndcg_at_3
FROM shop_ch15.quality_per_query
ORDER BY strategy, query_id;
