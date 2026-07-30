\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\echo '[setup] refuse collisions with non-ch07 objects'

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch07 deterministic planner lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch07_plan_probe',
        'shop_private.ch07_event_probe'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'refusing collision: % does not carry the ch07 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch07_event_probe CASCADE;
DROP TABLE IF EXISTS shop_private.ch07_plan_probe CASCADE;

\echo '[setup] build a deterministic correlated and skewed relation'

CREATE TABLE shop_private.ch07_plan_probe (
    probe_id bigint PRIMARY KEY,
    tenant_id bigint NOT NULL,
    region text NOT NULL,
    order_status text NOT NULL,
    placed_at timestamptz NOT NULL,
    amount_minor integer NOT NULL,
    payload text NOT NULL,
    CONSTRAINT ch07_plan_probe_region_check
        CHECK (region IN ('east', 'west', 'north', 'south')),
    CONSTRAINT ch07_plan_probe_status_check
        CHECK (order_status IN ('paid', 'cancelled', 'pending', 'refunded'))
);

ALTER TABLE shop_private.ch07_plan_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch07_plan_probe IS
    'pg36 ch07 deterministic planner lab; safe to rebuild';

INSERT INTO shop_private.ch07_plan_probe (
    probe_id,
    tenant_id,
    region,
    order_status,
    placed_at,
    amount_minor,
    payload
)
SELECT
    gs,
    CASE
        WHEN gs <= 90000 THEN 1
        ELSE 2 + ((gs - 90001) / 10)
    END,
    CASE (gs - 1) % 4
        WHEN 0 THEN 'east'
        WHEN 1 THEN 'west'
        WHEN 2 THEN 'north'
        ELSE 'south'
    END,
    CASE (gs - 1) % 4
        WHEN 0 THEN 'paid'
        WHEN 1 THEN 'cancelled'
        WHEN 2 THEN 'pending'
        ELSE 'refunded'
    END,
    timestamptz '2025-01-01 00:00:00+00'
        + (gs * interval '1 second'),
    (gs % 10000)::integer,
    pg_catalog.repeat('x', 128)
FROM pg_catalog.generate_series(1, 100000) AS seed(gs);

CREATE INDEX ch07_plan_probe_tenant_idx
    ON shop_private.ch07_plan_probe (tenant_id);

ANALYZE shop_private.ch07_plan_probe;

\echo '[setup] build four deterministic quarterly partitions'

CREATE TABLE shop_private.ch07_event_probe (
    event_id bigint NOT NULL,
    occurred_on date NOT NULL,
    tenant_id bigint NOT NULL,
    payload text NOT NULL
) PARTITION BY RANGE (occurred_on);

ALTER TABLE shop_private.ch07_event_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch07_event_probe IS
    'pg36 ch07 deterministic planner lab; safe to rebuild';

CREATE TABLE shop_private.ch07_event_probe_2025q1
    PARTITION OF shop_private.ch07_event_probe
    FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');
CREATE TABLE shop_private.ch07_event_probe_2025q2
    PARTITION OF shop_private.ch07_event_probe
    FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');
CREATE TABLE shop_private.ch07_event_probe_2025q3
    PARTITION OF shop_private.ch07_event_probe
    FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');
CREATE TABLE shop_private.ch07_event_probe_2025q4
    PARTITION OF shop_private.ch07_event_probe
    FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');

INSERT INTO shop_private.ch07_event_probe (
    event_id,
    occurred_on,
    tenant_id,
    payload
)
SELECT
    row_number() OVER (ORDER BY d, n),
    d,
    1 + ((extract(doy FROM d)::integer + n) % 100),
    pg_catalog.repeat('e', 32)
FROM pg_catalog.generate_series(
         date '2025-01-01',
         date '2025-12-31',
         interval '1 day'
     ) AS days(d)
CROSS JOIN pg_catalog.generate_series(1, 10) AS copies(n);

ANALYZE shop_private.ch07_event_probe_2025q1;
ANALYZE shop_private.ch07_event_probe_2025q2;
ANALYZE shop_private.ch07_event_probe_2025q3;
ANALYZE shop_private.ch07_event_probe_2025q4;

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'plan_probe_rows=' || count(*)
FROM shop_private.ch07_plan_probe;
SELECT 'hot_tenant_rows=' || count(*)
FROM shop_private.ch07_plan_probe
WHERE tenant_id = 1;
SELECT 'cold_tenant_rows=' || count(*)
FROM shop_private.ch07_plan_probe
WHERE tenant_id = 1001;
SELECT 'correlated_pair_rows=' || count(*)
FROM shop_private.ch07_plan_probe
WHERE region = 'east'
  AND order_status = 'paid';
SELECT 'impossible_pair_rows=' || count(*)
FROM shop_private.ch07_plan_probe
WHERE region = 'east'
  AND order_status = 'cancelled';
SELECT 'partition_rows=' || count(*)
FROM shop_private.ch07_event_probe;
SELECT 'partition_parent_stats_before=' || count(*)
FROM pg_catalog.pg_stats
WHERE schemaname = 'shop_private'
  AND tablename = 'ch07_event_probe';
