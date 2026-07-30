\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH business_rows AS (
    SELECT
        'attempt'::text AS kind,
        attempt_id AS sort_key,
        pg_catalog.concat_ws(
            '|',
            attempt_id,
            event_id,
            occurred_at,
            received_at,
            courier_id,
            event_type,
            longitude,
            latitude,
            source_sequence
        ) AS payload
    FROM shop_ch16.ingest_attempt

    UNION ALL

    SELECT
        'registry',
        event_id,
        pg_catalog.concat_ws(
            '|',
            event_id,
            canonical_attempt_id,
            first_received_at,
            last_received_at,
            attempt_count,
            payload_fingerprint
        )
    FROM shop_ch16.event_registry

    UNION ALL

    SELECT
        'geofence',
        zone_id || '|' ||
            pg_catalog.lpad(version::text, 4, '0'),
        pg_catalog.concat_ws(
            '|',
            zone_id,
            version,
            valid_during,
            shop_ch16_ext.ST_AsEWKT(zone_geom)
        )
    FROM shop_ch16.geofence_version

    UNION ALL

    SELECT
        'hub',
        hub_id,
        pg_catalog.concat_ws(
            '|',
            hub_id,
            hub_name,
            shop_ch16_ext.ST_AsEWKT(location)
        )
    FROM shop_ch16.delivery_hub

    UNION ALL

    SELECT
        'event',
        event_id,
        pg_catalog.concat_ws(
            '|',
            event_id,
            occurred_at,
            received_at,
            courier_id,
            event_type,
            source_sequence,
            shop_ch16_ext.ST_AsEWKT(location)
        )
    FROM shop_ch16.delivery_event

    UNION ALL

    SELECT
        'membership',
        event_id || '|' || zone_id || '|' ||
            pg_catalog.lpad(zone_version::text, 4, '0'),
        pg_catalog.concat_ws(
            '|',
            event_id,
            zone_id,
            zone_version
        )
    FROM shop_ch16.event_zone_membership
),
business_checksum AS (
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           ) AS checksum
    FROM business_rows
),
partition_counts AS (
    SELECT
        tableoid::pg_catalog.regclass::text AS partition_name,
        pg_catalog.count(*) AS event_count
    FROM shop_ch16.delivery_event
    GROUP BY tableoid
),
fact AS (
    SELECT
        'release'::text AS key,
        '1.4-proposal'::text AS value

    UNION ALL

    SELECT 'fixture', fixture_version
    FROM shop_ch16.fixture_meta

    UNION ALL

    SELECT
        'attempts',
        pg_catalog.count(*)::text
    FROM shop_ch16.ingest_attempt

    UNION ALL

    SELECT
        'events',
        pg_catalog.count(*)::text
    FROM shop_ch16.delivery_event

    UNION ALL

    SELECT
        'duplicate_registry',
        pg_catalog.string_agg(
            event_id || ':' || attempt_count::text,
            ',' ORDER BY event_id
        )
    FROM shop_ch16.event_registry
    WHERE attempt_count > 1

    UNION ALL

    SELECT
        'late_events',
        pg_catalog.string_agg(
            event_id,
            ',' ORDER BY occurred_at, event_id
        )
    FROM shop_ch16.event_lateness
    WHERE is_late

    UNION ALL

    SELECT
        'partition_counts',
        pg_catalog.string_agg(
            partition_name || ':' || event_count::text,
            ',' ORDER BY partition_name
        )
    FROM partition_counts

    UNION ALL

    SELECT
        'memberships',
        pg_catalog.count(*)::text
    FROM shop_ch16.event_zone_membership

    UNION ALL

    SELECT
        'central_day8',
        pg_catalog.string_agg(
            event_id,
            ',' ORDER BY occurred_at, event_id
        )
    FROM shop_ch16.event_zone_membership
    WHERE zone_id = 'central'
      AND occurred_at >=
              TIMESTAMPTZ '2026-03-08 00:00:00+00'
      AND occurred_at <
              TIMESTAMPTZ '2026-03-09 00:00:00+00'

    UNION ALL

    SELECT
        'extensions',
        pg_catalog.string_agg(
            extname || ':' || extversion,
            ',' ORDER BY extname
        )
    FROM pg_catalog.pg_extension
    WHERE extname IN ('btree_gist', 'postgis')

    UNION ALL

    SELECT
        'business_checksum',
        checksum
    FROM business_checksum
)
SELECT key, value
FROM fact
ORDER BY key;
