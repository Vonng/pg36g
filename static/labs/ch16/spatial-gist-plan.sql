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
SELECT event_id
FROM shop_ch16.delivery_event
WHERE occurred_at >=
          TIMESTAMPTZ '2026-03-08 00:00:00+00'
  AND occurred_at <
          TIMESTAMPTZ '2026-03-09 00:00:00+00'
  AND shop_ch16_ext.ST_DWithin(
          location_geog,
          shop_ch16_ext.ST_SetSRID(
              shop_ch16_ext.ST_MakePoint(
                  -74.00000,
                  40.71000
              ),
              4326
          )::shop_ch16_ext.geography,
          1500
      )
ORDER BY occurred_at, event_id;
