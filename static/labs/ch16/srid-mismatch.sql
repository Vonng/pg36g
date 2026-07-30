\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT shop_ch16_ext.ST_Intersects(
    shop_ch16_ext.ST_SetSRID(
        shop_ch16_ext.ST_MakePoint(0, 0),
        4326
    ),
    shop_ch16_ext.ST_SetSRID(
        shop_ch16_ext.ST_MakePoint(0, 0),
        3857
    )
);
