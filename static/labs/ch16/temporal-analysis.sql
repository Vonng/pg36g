\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH dst_events AS (
    SELECT
        event_id,
        occurred_at,
        occurred_at AT TIME ZONE
            'America/New_York' AS local_time
    FROM shop_ch16.delivery_event
    WHERE event_id IN ('e002', 'e003')
),
fact AS (
    SELECT
        'dst_e002_local'::text AS key,
        pg_catalog.to_char(
            local_time,
            'YYYY-MM-DD HH24:MI:SS'
        ) AS value
    FROM dst_events
    WHERE event_id = 'e002'

    UNION ALL

    SELECT
        'dst_e003_local',
        pg_catalog.to_char(
            local_time,
            'YYYY-MM-DD HH24:MI:SS'
        )
    FROM dst_events
    WHERE event_id = 'e003'

    UNION ALL

    SELECT
        'dst_elapsed_seconds',
        extract(
            epoch FROM (
                pg_catalog.max(occurred_at) -
                pg_catalog.min(occurred_at)
            )
        )::bigint::text
    FROM dst_events

    UNION ALL

    SELECT
        'late_event_ids',
        pg_catalog.string_agg(
            event_id,
            ',' ORDER BY occurred_at, event_id
        )
    FROM shop_ch16.event_lateness
    WHERE is_late

    UNION ALL

    SELECT
        'out_of_order_pair',
        earlier.event_id || '->' || later.event_id
    FROM shop_ch16.delivery_event AS earlier
    JOIN shop_ch16.delivery_event AS later
      ON earlier.event_id = 'e004'
     AND later.event_id = 'e005'
     AND earlier.occurred_at < later.occurred_at
     AND earlier.received_at > later.received_at

    UNION ALL

    SELECT
        'duplicate_event',
        event_id || ':' || attempt_count::text
    FROM shop_ch16.event_registry
    WHERE attempt_count > 1

    UNION ALL

    SELECT
        'utc_day8_events',
        pg_catalog.count(*)::text
    FROM shop_ch16.delivery_event
    WHERE occurred_at >=
              TIMESTAMPTZ '2026-03-08 00:00:00+00'
      AND occurred_at <
              TIMESTAMPTZ '2026-03-09 00:00:00+00'

    UNION ALL

    SELECT
        'partition_boundary',
        pg_catalog.string_agg(
            event_id || '=' ||
            tableoid::pg_catalog.regclass::text,
            ';' ORDER BY occurred_at, event_id
        )
    FROM shop_ch16.delivery_event
    WHERE event_id IN ('e008', 'e009')
)
SELECT key, value
FROM fact
ORDER BY key;
