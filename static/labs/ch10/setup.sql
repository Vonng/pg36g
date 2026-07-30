\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch10 deterministic concurrency lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch10_inventory',
        'shop_private.ch10_doctor',
        'shop_private.ch10_deadlock_probe',
        'shop_private.ch10_job',
        'shop_private.ch10_payment_request',
        'shop_private.ch10_outbox'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'refusing collision: % lacks the ch10 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch10_outbox;
DROP TABLE IF EXISTS shop_private.ch10_payment_request;
DROP TABLE IF EXISTS shop_private.ch10_job;
DROP TABLE IF EXISTS shop_private.ch10_deadlock_probe;
DROP TABLE IF EXISTS shop_private.ch10_doctor;
DROP TABLE IF EXISTS shop_private.ch10_inventory;

CREATE TABLE shop_private.ch10_inventory (
    sku_id bigint PRIMARY KEY,
    available integer NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ch10_inventory_available_check
        CHECK (available >= 0),
    CONSTRAINT ch10_inventory_version_check
        CHECK (version >= 0)
);

CREATE TABLE shop_private.ch10_doctor (
    doctor_id integer PRIMARY KEY,
    doctor_name text NOT NULL UNIQUE,
    on_call boolean NOT NULL
);

CREATE TABLE shop_private.ch10_deadlock_probe (
    row_id integer PRIMARY KEY,
    value integer NOT NULL
);

CREATE TABLE shop_private.ch10_job (
    job_id integer PRIMARY KEY,
    job_state text NOT NULL,
    claimed_by text,
    claimed_at timestamptz,
    payload jsonb NOT NULL,
    CONSTRAINT ch10_job_state_check
        CHECK (job_state IN ('queued', 'running', 'done')),
    CONSTRAINT ch10_job_claim_shape_check
        CHECK (
            (job_state = 'queued'
             AND claimed_by IS NULL
             AND claimed_at IS NULL)
            OR
            (job_state <> 'queued'
             AND claimed_by IS NOT NULL
             AND claimed_at IS NOT NULL)
        )
);

CREATE TABLE shop_private.ch10_payment_request (
    idempotency_key text PRIMARY KEY,
    request_fingerprint text NOT NULL,
    payment_id text NOT NULL UNIQUE,
    amount_minor bigint NOT NULL,
    payment_state text NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ch10_payment_amount_check
        CHECK (amount_minor > 0),
    CONSTRAINT ch10_payment_state_check
        CHECK (payment_state IN ('accepted', 'declined'))
);

CREATE TABLE shop_private.ch10_outbox (
    event_key text PRIMARY KEY,
    aggregate_key text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

ALTER TABLE shop_private.ch10_inventory OWNER TO pg36_owner;
ALTER TABLE shop_private.ch10_doctor OWNER TO pg36_owner;
ALTER TABLE shop_private.ch10_deadlock_probe OWNER TO pg36_owner;
ALTER TABLE shop_private.ch10_job OWNER TO pg36_owner;
ALTER TABLE shop_private.ch10_payment_request OWNER TO pg36_owner;
ALTER TABLE shop_private.ch10_outbox OWNER TO pg36_owner;

COMMENT ON TABLE shop_private.ch10_inventory IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch10_doctor IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch10_deadlock_probe IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch10_job IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch10_payment_request IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch10_outbox IS
    'pg36 ch10 deterministic concurrency lab; safe to rebuild';

INSERT INTO shop_private.ch10_inventory (
    sku_id,
    available,
    version,
    updated_at
)
VALUES
    (1001, 100, 0, timestamptz '2025-01-01 00:00:00+00'),
    (1002, 100, 0, timestamptz '2025-01-01 00:00:00+00');

INSERT INTO shop_private.ch10_doctor (
    doctor_id,
    doctor_name,
    on_call
)
VALUES
    (1, 'Ada', true),
    (2, 'Linus', true);

INSERT INTO shop_private.ch10_deadlock_probe (row_id, value)
VALUES (1, 0), (2, 0);

INSERT INTO shop_private.ch10_job (
    job_id,
    job_state,
    claimed_by,
    claimed_at,
    payload
)
SELECT
    job_id,
    'queued',
    NULL,
    NULL,
    pg_catalog.jsonb_build_object('job_id', job_id)
FROM pg_catalog.generate_series(1, 6) AS seed(job_id);

ANALYZE shop_private.ch10_inventory;
ANALYZE shop_private.ch10_doctor;
ANALYZE shop_private.ch10_deadlock_probe;
ANALYZE shop_private.ch10_job;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=ch10-concurrency-v1';
SELECT 'inventory=100,100/version:0,0';
SELECT 'doctors_on_call=2';
SELECT 'jobs_queued=6';
SELECT 'payments=0/outbox=0';
