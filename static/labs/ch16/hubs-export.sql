\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        hub_id,
        hub_name,
        pg_catalog.to_char(
            shop_ch16_ext.ST_X(location),
            'FM999990.00000'
        ) AS longitude,
        pg_catalog.to_char(
            shop_ch16_ext.ST_Y(location),
            'FM999990.00000'
        ) AS latitude
    FROM shop_ch16.delivery_hub
    ORDER BY hub_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
