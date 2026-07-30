\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET enable_seqscan = off;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT
    hub_id,
    hub_name
FROM shop_ch16.delivery_hub
WHERE shop_ch16_ext.ST_DWithin(
    location,
    shop_ch16_ext.ST_SetSRID(
        shop_ch16_ext.ST_MakePoint(
            -73.98200,
            40.71200
        ),
        4326
    ),
    0.02
)
ORDER BY hub_id;
