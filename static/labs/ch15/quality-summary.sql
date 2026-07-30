\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    strategy,
    query_count,
    mean_precision_at_3,
    mean_recall_at_3,
    mrr_at_3,
    mean_ndcg_at_3,
    min_ndcg_at_3
FROM shop_ch15.quality_summary
ORDER BY strategy;
