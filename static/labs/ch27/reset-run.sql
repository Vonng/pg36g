\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

DO $guard$
BEGIN
    IF current_database() <> 'pg36_tuning'
       OR current_user <> 'dbuser_pg36tune'
       OR pg_is_in_recovery() THEN
        RAISE EXCEPTION
            'chapter 27 reset target guard failed: db=%, user=%, recovery=%',
            current_database(),
            current_user,
            pg_is_in_recovery();
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM shopbench.fixture_marker
        WHERE marker = 'pg36-ch27-disposable-tuning-fixture-v1'
          AND scale_factor = 8
    ) THEN
        RAISE EXCEPTION 'chapter 27 fixture marker is missing';
    END IF;
END
$guard$;

SET lock_timeout = '5s';
SET statement_timeout = '30s';
SET synchronous_commit = on;

TRUNCATE TABLE shopbench.order_live RESTART IDENTITY;
TRUNCATE TABLE shopbench.inventory;

INSERT INTO shopbench.inventory (product_id, quantity, updated_at)
SELECT
    product_id,
    (1000000 + product_id % 1000)::integer,
    timestamptz '2026-01-01 00:00:00+00'
FROM shopbench.product;

ANALYZE shopbench.inventory;
ANALYZE shopbench.order_live;

SELECT jsonb_build_object(
    'inventory_rows', (SELECT count(*) FROM shopbench.inventory),
    'live_order_rows', (SELECT count(*) FROM shopbench.order_live)
);
