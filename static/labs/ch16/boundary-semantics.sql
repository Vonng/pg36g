\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH probes (
    scenario,
    event_id,
    zone_id,
    zone_version
) AS (
    VALUES
        ('shared_boundary', 'e003', 'central', 1),
        ('shared_boundary', 'e003', 'east', 1),
        ('before_expansion', 'e004', 'central', 1),
        ('at_expansion', 'e005', 'central', 2)
)
SELECT
    probe.scenario,
    probe.event_id,
    probe.zone_id,
    probe.zone_version,
    shop_ch16_ext.ST_Covers(
        zone.zone_geom,
        event.location
    ) AS covers,
    shop_ch16_ext.ST_Contains(
        zone.zone_geom,
        event.location
    ) AS contains,
    shop_ch16_ext.ST_Touches(
        zone.zone_geom,
        event.location
    ) AS touches
FROM probes AS probe
JOIN shop_ch16.delivery_event AS event
  ON event.event_id = probe.event_id
JOIN shop_ch16.geofence_version AS zone
  ON zone.zone_id = probe.zone_id
 AND zone.version = probe.zone_version
ORDER BY
    probe.scenario,
    probe.event_id,
    probe.zone_id;
