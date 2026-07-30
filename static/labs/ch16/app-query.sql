\set ON_ERROR_STOP on
\pset pager off

SELECT
    event_id,
    zone_id,
    zone_version
FROM shop_ch16.event_zone_membership
WHERE occurred_at >=
          TIMESTAMPTZ '2026-03-08 00:00:00+00'
  AND occurred_at <
          TIMESTAMPTZ '2026-03-09 00:00:00+00'
  AND zone_id = 'central'
ORDER BY occurred_at, event_id;
