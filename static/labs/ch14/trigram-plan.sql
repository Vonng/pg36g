\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT document.doc_id
FROM shop_ch14.candidate_doc AS document
WHERE document.title
      OPERATOR(shop_ch14.%)
      'PostgreSQL extenson';
