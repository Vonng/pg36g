INSERT INTO shop_ch16.fixture_meta (
    fixture_version,
    attempts_identity,
    geofences_identity,
    hubs_identity,
    event_time_basis,
    partition_timezone,
    coordinate_contract,
    text_license,
    coordinate_license,
    frozen_at
)
VALUES (
    'ch16-spatiotemporal-v1',
    'frozen-attempts.csv',
    'frozen-geofences.csv',
    'frozen-hubs.csv',
    'occurred_at',
    'UTC',
    'synthetic longitude/latitude in EPSG:4326',
    'project-owned synthetic fixture; repository terms apply',
    'synthetic coordinates; no external geodata license',
    TIMESTAMPTZ '2026-07-29 00:00:00+00'
);

INSERT INTO shop_ch16.ingest_attempt (
    attempt_id,
    event_id,
    occurred_at,
    received_at,
    courier_id,
    event_type,
    longitude,
    latitude,
    source_sequence
)
VALUES
    (
        'a001', 'e001',
        TIMESTAMPTZ '2026-03-07 23:55:00+00',
        TIMESTAMPTZ '2026-03-08 08:00:00+00',
        'c1', 'position', -74.00000, 40.71000, 1
    ),
    (
        'a002', 'e002',
        TIMESTAMPTZ '2026-03-08 06:55:00+00',
        TIMESTAMPTZ '2026-03-08 06:55:10+00',
        'c1', 'pickup', -74.00500, 40.70500, 2
    ),
    (
        'a003', 'e003',
        TIMESTAMPTZ '2026-03-08 07:05:00+00',
        TIMESTAMPTZ '2026-03-08 07:05:20+00',
        'c1', 'position', -73.99000, 40.71000, 3
    ),
    (
        'a004', 'e003',
        TIMESTAMPTZ '2026-03-08 07:05:00+00',
        TIMESTAMPTZ '2026-03-08 07:06:00+00',
        'c1', 'position', -73.99000, 40.71000, 3
    ),
    (
        'a005', 'e004',
        TIMESTAMPTZ '2026-03-08 11:55:00+00',
        TIMESTAMPTZ '2026-03-08 12:10:00+00',
        'c1', 'position', -73.98500, 40.71000, 4
    ),
    (
        'a006', 'e005',
        TIMESTAMPTZ '2026-03-08 12:00:00+00',
        TIMESTAMPTZ '2026-03-08 12:00:05+00',
        'c1', 'position', -73.98500, 40.71000, 5
    ),
    (
        'a007', 'e006',
        TIMESTAMPTZ '2026-03-08 12:05:00+00',
        TIMESTAMPTZ '2026-03-08 12:05:05+00',
        'c1', 'delivered', -73.98200, 40.71500, 6
    ),
    (
        'a008', 'e007',
        TIMESTAMPTZ '2026-03-08 15:00:00+00',
        TIMESTAMPTZ '2026-03-08 15:00:08+00',
        'c2', 'pickup', -73.87500, 40.65000, 1
    ),
    (
        'a009', 'e008',
        TIMESTAMPTZ '2026-03-08 23:59:59+00',
        TIMESTAMPTZ '2026-03-09 00:00:04+00',
        'c2', 'position', -73.99500, 40.71800, 2
    ),
    (
        'a010', 'e009',
        TIMESTAMPTZ '2026-03-09 00:00:00+00',
        TIMESTAMPTZ '2026-03-09 00:00:03+00',
        'c2', 'position', -74.00500, 40.70200, 3
    ),
    (
        'a011', 'e010',
        TIMESTAMPTZ '2026-03-09 10:00:00+00',
        TIMESTAMPTZ '2026-03-09 10:00:07+00',
        'c2', 'position', -74.05000, 40.75000, 4
    ),
    (
        'a012', 'e011',
        TIMESTAMPTZ '2026-03-09 18:00:00+00',
        TIMESTAMPTZ '2026-03-09 18:00:06+00',
        'c2', 'delivered', -73.97500, 40.71500, 5
    ),
    (
        'a013', 'e012',
        TIMESTAMPTZ '2026-03-09 23:30:00+00',
        TIMESTAMPTZ '2026-03-09 23:30:09+00',
        'c3', 'pickup', -73.86000, 40.66000, 1
    );

WITH payload_consistency AS (
    SELECT
        event_id,
        pg_catalog.count(
            DISTINCT pg_catalog.concat_ws(
                '|',
                occurred_at::text,
                courier_id,
                event_type,
                longitude::text,
                latitude::text,
                source_sequence::text
            )
        ) AS payload_variants
    FROM shop_ch16.ingest_attempt
    GROUP BY event_id
),
canonical AS (
    SELECT DISTINCT ON (attempt.event_id)
        attempt.event_id,
        attempt.attempt_id AS canonical_attempt_id,
        attempt.received_at AS first_received_at
    FROM shop_ch16.ingest_attempt AS attempt
    ORDER BY
        attempt.event_id,
        attempt.received_at,
        attempt.attempt_id
)
INSERT INTO shop_ch16.event_registry (
    event_id,
    canonical_attempt_id,
    first_received_at,
    last_received_at,
    attempt_count,
    payload_fingerprint
)
SELECT
    attempt.event_id,
    canonical.canonical_attempt_id,
    canonical.first_received_at,
    pg_catalog.max(attempt.received_at),
    pg_catalog.count(*)::integer,
    pg_catalog.md5(
        pg_catalog.min(
            pg_catalog.concat_ws(
                '|',
                attempt.occurred_at::text,
                attempt.courier_id,
                attempt.event_type,
                attempt.longitude::text,
                attempt.latitude::text,
                attempt.source_sequence::text
            )
        )
    )
FROM shop_ch16.ingest_attempt AS attempt
JOIN payload_consistency AS consistency
  ON consistency.event_id = attempt.event_id
 AND consistency.payload_variants = 1
JOIN canonical
  ON canonical.event_id = attempt.event_id
GROUP BY
    attempt.event_id,
    canonical.canonical_attempt_id,
    canonical.first_received_at;

INSERT INTO shop_ch16.geofence_version (
    zone_id,
    version,
    valid_during,
    zone_geom
)
VALUES
    (
        'airport',
        1,
        pg_catalog.tstzrange(
            TIMESTAMPTZ '2026-03-07 00:00:00+00',
            TIMESTAMPTZ '2026-03-10 00:00:00+00',
            '[)'
        ),
        shop_ch16_ext.ST_GeomFromText(
            'POLYGON((-73.9 40.63,-73.85 40.63,-73.85 40.67,-73.9 40.67,-73.9 40.63))',
            4326
        )::shop_ch16_ext.geometry(Polygon, 4326)
    ),
    (
        'central',
        1,
        pg_catalog.tstzrange(
            TIMESTAMPTZ '2026-03-07 00:00:00+00',
            TIMESTAMPTZ '2026-03-08 12:00:00+00',
            '[)'
        ),
        shop_ch16_ext.ST_GeomFromText(
            'POLYGON((-74.01 40.7,-73.99 40.7,-73.99 40.72,-74.01 40.72,-74.01 40.7))',
            4326
        )::shop_ch16_ext.geometry(Polygon, 4326)
    ),
    (
        'central',
        2,
        pg_catalog.tstzrange(
            TIMESTAMPTZ '2026-03-08 12:00:00+00',
            TIMESTAMPTZ '2026-03-10 00:00:00+00',
            '[)'
        ),
        shop_ch16_ext.ST_GeomFromText(
            'POLYGON((-74.01 40.7,-73.98 40.7,-73.98 40.72,-74.01 40.72,-74.01 40.7))',
            4326
        )::shop_ch16_ext.geometry(Polygon, 4326)
    ),
    (
        'east',
        1,
        pg_catalog.tstzrange(
            TIMESTAMPTZ '2026-03-07 00:00:00+00',
            TIMESTAMPTZ '2026-03-10 00:00:00+00',
            '[)'
        ),
        shop_ch16_ext.ST_GeomFromText(
            'POLYGON((-73.99 40.7,-73.97 40.7,-73.97 40.72,-73.99 40.72,-73.99 40.7))',
            4326
        )::shop_ch16_ext.geometry(Polygon, 4326)
    );

INSERT INTO shop_ch16.delivery_hub (
    hub_id,
    hub_name,
    location
)
VALUES
    (
        'airport',
        'Airport Hub',
        shop_ch16_ext.ST_SetSRID(
            shop_ch16_ext.ST_Point(-73.87500, 40.65000),
            4326
        )::shop_ch16_ext.geometry(Point, 4326)
    ),
    (
        'central',
        'Central Hub',
        shop_ch16_ext.ST_SetSRID(
            shop_ch16_ext.ST_Point(-74.00000, 40.71000),
            4326
        )::shop_ch16_ext.geometry(Point, 4326)
    ),
    (
        'east',
        'East Hub',
        shop_ch16_ext.ST_SetSRID(
            shop_ch16_ext.ST_Point(-73.98000, 40.71000),
            4326
        )::shop_ch16_ext.geometry(Point, 4326)
    );

INSERT INTO shop_ch16.delivery_event (
    occurred_at,
    event_id,
    received_at,
    courier_id,
    event_type,
    location,
    source_sequence
)
SELECT
    attempt.occurred_at,
    registry.event_id,
    registry.first_received_at,
    attempt.courier_id,
    attempt.event_type,
    shop_ch16_ext.ST_SetSRID(
        shop_ch16_ext.ST_Point(
            attempt.longitude::double precision,
            attempt.latitude::double precision
        ),
        4326
    )::shop_ch16_ext.geometry(Point, 4326),
    attempt.source_sequence
FROM shop_ch16.event_registry AS registry
JOIN shop_ch16.ingest_attempt AS attempt
  ON attempt.attempt_id = registry.canonical_attempt_id;
