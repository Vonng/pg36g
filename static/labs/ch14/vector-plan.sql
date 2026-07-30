\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT document.doc_id
FROM shop_ch14.candidate_doc AS document
ORDER BY
    document.embedding
        OPERATOR(shop_ch14.<->)
        '[1,0,0]'::shop_ch14.vector(3)
LIMIT 3;
