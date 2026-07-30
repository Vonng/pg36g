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
    event.event_id,
    zone.zone_id,
    zone.version
FROM shop_ch16.delivery_event AS event
JOIN shop_ch16.geofence_version AS zone
  ON zone.valid_during @> event.occurred_at
 AND shop_ch16_ext.ST_Covers(
         zone.zone_geom,
         event.location
     )
WHERE event.occurred_at >=
          TIMESTAMPTZ '2026-03-08 00:00:00+00'
  AND event.occurred_at <
          TIMESTAMPTZ '2026-03-09 00:00:00+00'
  AND zone.zone_id = 'central'
ORDER BY event.occurred_at, event.event_id;
