\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        product_id,
        sku,
        category,
        active::text,
        title,
        description,
        embedding::text
    FROM shop_ch15.product_search
    ORDER BY product_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
