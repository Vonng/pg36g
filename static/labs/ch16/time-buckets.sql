\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    pg_catalog.to_char(
        bucket_start AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
    ) AS bucket_start,
    event_count,
    late_event_count
FROM shop_ch16.quarter_hour_volume
ORDER BY bucket_start;
