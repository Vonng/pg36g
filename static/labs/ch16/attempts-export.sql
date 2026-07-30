\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        attempt_id,
        event_id,
        pg_catalog.to_char(
            occurred_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        ) AS occurred_at,
        pg_catalog.to_char(
            received_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        ) AS received_at,
        courier_id,
        event_type,
        pg_catalog.to_char(
            longitude,
            'FM999990.00000'
        ) AS longitude,
        pg_catalog.to_char(
            latitude,
            'FM999990.00000'
        ) AS latitude,
        source_sequence
    FROM shop_ch16.ingest_attempt
    ORDER BY attempt_id
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
