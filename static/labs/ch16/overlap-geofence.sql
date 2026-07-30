\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SET ROLE pg36_owner;

INSERT INTO shop_ch16.geofence_version (
    zone_id,
    version,
    valid_during,
    zone_geom
)
SELECT
    'central',
    99,
    pg_catalog.tstzrange(
        TIMESTAMPTZ '2026-03-08 11:00:00+00',
        TIMESTAMPTZ '2026-03-08 13:00:00+00',
        '[)'
    ),
    zone_geom
FROM shop_ch16.geofence_version
WHERE zone_id = 'central'
  AND version = 1;
