\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    function_oid regprocedure;
    expected_marker constant text :=
        'pg36 ch11 deterministic release lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch11_order',
        'shop_private.ch11_migration_state',
        'shop_private.ch11_default_probe',
        'shop_private.ch11_default_probe_result',
        'shop_private.ch11_event',
        'shop_private.ch11_event_2025q1'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'refusing collision: % lacks the ch11 marker',
                relation_name;
        END IF;
    END LOOP;

    function_oid := pg_catalog.to_regprocedure(
        'shop_private.ch11_sync_shipping_code()'
    );
    IF function_oid IS NOT NULL
       AND pg_catalog.obj_description(
               function_oid::oid,
               'pg_proc'
           ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'refusing collision: ch11_sync_shipping_code() lacks marker';
    END IF;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch11_event CASCADE;
DROP TABLE IF EXISTS shop_private.ch11_event_2025q1;
DROP TABLE IF EXISTS shop_private.ch11_default_probe_result;
DROP TABLE IF EXISTS shop_private.ch11_default_probe;
DROP TABLE IF EXISTS shop_private.ch11_order;
DROP TABLE IF EXISTS shop_private.ch11_migration_state;
DROP FUNCTION IF EXISTS shop_private.ch11_sync_shipping_code();

CREATE TABLE shop_private.ch11_order (
    order_id bigint PRIMARY KEY,
    order_ref text NOT NULL UNIQUE,
    shipping_method text NOT NULL,
    created_at timestamptz NOT NULL,
    payload text NOT NULL,
    CONSTRAINT ch11_order_shipping_method_check
        CHECK (
            shipping_method IN ('standard', 'express', 'pickup')
        )
);

CREATE TABLE shop_private.ch11_migration_state (
    migration_id text PRIMARY KEY,
    phase text NOT NULL,
    source_rows bigint NOT NULL,
    target_rows bigint,
    rows_migrated bigint NOT NULL DEFAULT 0,
    batches integer NOT NULL DEFAULT 0,
    last_order_id bigint NOT NULL DEFAULT 0,
    expanded_at timestamptz,
    migrated_at timestamptz,
    validated_at timestamptz,
    switched_at timestamptz,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ch11_migration_phase_check
        CHECK (
            phase IN (
                'legacy',
                'expanded',
                'backfilling',
                'migrated',
                'validated',
                'switched'
            )
        ),
    CONSTRAINT ch11_migration_progress_check
        CHECK (
            source_rows >= 0
            AND target_rows >= 0
            AND rows_migrated >= 0
            AND batches >= 0
            AND last_order_id >= 0
        )
);

ALTER TABLE shop_private.ch11_order OWNER TO pg36_owner;
ALTER TABLE shop_private.ch11_migration_state OWNER TO pg36_owner;

COMMENT ON TABLE shop_private.ch11_order IS
    'pg36 ch11 deterministic release lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch11_migration_state IS
    'pg36 ch11 deterministic release lab; safe to rebuild';

INSERT INTO shop_private.ch11_order (
    order_id,
    order_ref,
    shipping_method,
    created_at,
    payload
)
SELECT
    seed.order_id,
    'ch11-' || pg_catalog.lpad(seed.order_id::text, 8, '0'),
    CASE seed.order_id % 3
        WHEN 0 THEN 'standard'
        WHEN 1 THEN 'express'
        ELSE 'pickup'
    END,
    timestamptz '2025-01-01 00:00:00+00'
        + seed.order_id * interval '1 second',
    pg_catalog.repeat(
        pg_catalog.md5(seed.order_id::text),
        3
    )
FROM pg_catalog.generate_series(1, 50000) AS seed(order_id);

INSERT INTO shop_private.ch11_migration_state (
    migration_id,
    phase,
    source_rows,
    target_rows,
    rows_migrated,
    batches,
    last_order_id,
    updated_at
)
VALUES (
    'shipping-code-v1',
    'legacy',
    50000,
    NULL,
    0,
    0,
    0,
    timestamptz '2025-01-01 00:00:00+00'
);

ANALYZE shop_private.ch11_order;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=ch11-release-v1';
SELECT 'phase=' || phase
FROM shop_private.ch11_migration_state
WHERE migration_id = 'shipping-code-v1';
SELECT 'orders=' || count(*)
FROM shop_private.ch11_order;
SELECT 'shipping_code_column=' ||
       CASE
           WHEN EXISTS (
               SELECT 1
               FROM pg_catalog.pg_attribute
               WHERE attrelid =
                     'shop_private.ch11_order'::regclass
                 AND attname = 'shipping_code'
                 AND attnum > 0
                 AND NOT attisdropped
           )
           THEN 'present'
           ELSE 'absent'
       END;
