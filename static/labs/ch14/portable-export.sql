\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        document.doc_id,
        document.title,
        document.embedding::text AS embedding_text
    FROM shop_ch14.candidate_doc AS document
    ORDER BY document.doc_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
