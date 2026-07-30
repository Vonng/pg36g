\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        query_id,
        raw_query,
        category_filter,
        embedding::text,
        intent
    FROM shop_ch15.eval_query
    ORDER BY query_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
