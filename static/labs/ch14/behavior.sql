\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH trigram_result AS (
    SELECT
        document.doc_id,
        pg_catalog.round(
            shop_ch14.similarity(
                document.title,
                'PostgreSQL extenson'
            )::numeric,
            6
        ) AS score
    FROM shop_ch14.candidate_doc AS document
    ORDER BY
        shop_ch14.similarity(
            document.title,
            'PostgreSQL extenson'
        ) DESC,
        document.doc_id
    LIMIT 3
),
vector_result AS (
    SELECT
        document.doc_id,
        pg_catalog.round(
            (
                document.embedding
                OPERATOR(shop_ch14.<->)
                '[1,0,0]'::shop_ch14.vector(3)
            )::numeric,
            6
        ) AS distance
    FROM shop_ch14.candidate_doc AS document
    ORDER BY
        document.embedding
            OPERATOR(shop_ch14.<->)
            '[1,0,0]'::shop_ch14.vector(3),
        document.doc_id
    LIMIT 3
),
fact AS (
    SELECT
        'pg_trgm_version' AS key,
        (
            SELECT extversion
            FROM pg_catalog.pg_extension
            WHERE extname = 'pg_trgm'
        ) AS value
    UNION ALL
    SELECT
        'vector_version',
        (
            SELECT extversion
            FROM pg_catalog.pg_extension
            WHERE extname = 'vector'
        )
    UNION ALL
    SELECT
        'trigram_top_ids',
        (
            SELECT pg_catalog.string_agg(
                       doc_id::text,
                       ',' ORDER BY score DESC, doc_id
                   )
            FROM trigram_result
        )
    UNION ALL
    SELECT
        'trigram_scores',
        (
            SELECT pg_catalog.string_agg(
                       score::text,
                       ',' ORDER BY score DESC, doc_id
                   )
            FROM trigram_result
        )
    UNION ALL
    SELECT
        'vector_top_ids',
        (
            SELECT pg_catalog.string_agg(
                       doc_id::text,
                       ',' ORDER BY distance, doc_id
                   )
            FROM vector_result
        )
    UNION ALL
    SELECT
        'vector_distances',
        (
            SELECT pg_catalog.string_agg(
                       distance::text,
                       ',' ORDER BY distance, doc_id
                   )
            FROM vector_result
        )
)
SELECT key, value
FROM fact
ORDER BY key;
