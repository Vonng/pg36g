\set ON_ERROR_STOP on
\pset pager off

SET search_path = pg_catalog;
SET TimeZone = 'UTC';
SET statement_timeout = '30s';

SELECT
    document.doc_id,
    document.title,
    pg_catalog.round(
        shop_ch14.similarity(
            document.title,
            'PostgreSQL extenson'
        )::numeric,
        6
    ) AS trigram_score
FROM shop_ch14.candidate_doc AS document
ORDER BY trigram_score DESC, document.doc_id
LIMIT 3;

SELECT
    document.doc_id,
    document.title,
    pg_catalog.round(
        (
            document.embedding
            OPERATOR(shop_ch14.<->)
            '[1,0,0]'::shop_ch14.vector(3)
        )::numeric,
        6
    ) AS l2_distance
FROM shop_ch14.candidate_doc AS document
ORDER BY
    document.embedding
        OPERATOR(shop_ch14.<->)
        '[1,0,0]'::shop_ch14.vector(3),
    document.doc_id
LIMIT 3;
