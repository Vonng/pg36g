\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

CREATE TABLE shop_private.ch11_event (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload text NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE shop_private.ch11_event_2025q1 (
    LIKE shop_private.ch11_event
        INCLUDING DEFAULTS
        INCLUDING CONSTRAINTS
);

ALTER TABLE shop_private.ch11_event_2025q1
    ADD CONSTRAINT ch11_event_2025q1_bound
    CHECK (
        occurred_at >= timestamptz '2025-01-01 00:00:00+00'
        AND occurred_at < timestamptz '2025-04-01 00:00:00+00'
    );

ALTER TABLE shop_private.ch11_event OWNER TO pg36_owner;
ALTER TABLE shop_private.ch11_event_2025q1 OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch11_event IS
    'pg36 ch11 deterministic release lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch11_event_2025q1 IS
    'pg36 ch11 deterministic release lab; safe to rebuild';

INSERT INTO shop_private.ch11_event_2025q1 (
    event_id,
    occurred_at,
    payload
)
SELECT
    event_id,
    timestamptz '2025-01-01 00:00:00+00'
        + event_id * interval '3 minutes',
    pg_catalog.md5(event_id::text)
FROM pg_catalog.generate_series(1, 20000) AS seed(event_id);

ANALYZE shop_private.ch11_event_2025q1;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'partition_fixture=standalone-with-validated-check';
SELECT 'rows=' || count(*)
FROM shop_private.ch11_event_2025q1;
