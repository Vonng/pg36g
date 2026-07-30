\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        query_id,
        product_id,
        grade,
        rationale
    FROM shop_ch15.relevance_judgment
    ORDER BY query_id, product_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
