\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    event_id,
    zone_id,
    zone_version,
    pg_catalog.to_char(
        occurred_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
    ) AS occurred_at
FROM shop_ch16.event_zone_membership
ORDER BY event_id, zone_id, zone_version;
