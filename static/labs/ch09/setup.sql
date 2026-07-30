\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\echo '[setup] refuse collisions with non-ch09 objects'

DO $collision_guard$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch09 deterministic index lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch09_order_probe',
        'shop_private.ch09_inventory_probe',
        'shop_private.ch09_search_probe',
        'shop_private.ch09_event_probe',
        'shop_private.ch09_write_base',
        'shop_private.ch09_write_indexed',
        'shop_private.ch09_unique_probe'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NOT NULL
           AND pg_catalog.obj_description(
                   relation_oid::oid,
                   'pg_class'
               ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'refusing collision: % does not carry the ch09 marker',
                relation_name;
        END IF;
    END LOOP;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_private.ch09_unique_probe;
DROP TABLE IF EXISTS shop_private.ch09_write_indexed;
DROP TABLE IF EXISTS shop_private.ch09_write_base;
DROP TABLE IF EXISTS shop_private.ch09_event_probe;
DROP TABLE IF EXISTS shop_private.ch09_search_probe;
DROP TABLE IF EXISTS shop_private.ch09_inventory_probe;
DROP TABLE IF EXISTS shop_private.ch09_order_probe;

\echo '[setup] order fixture: 5 percent placed, 1000 customers'

CREATE TABLE shop_private.ch09_order_probe (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    order_status text NOT NULL,
    placed_at timestamptz NOT NULL,
    order_no text NOT NULL,
    amount_minor bigint NOT NULL,
    note text NOT NULL,
    CONSTRAINT ch09_order_probe_status_check
        CHECK (order_status IN ('draft', 'placed', 'paid', 'cancelled'))
);

ALTER TABLE shop_private.ch09_order_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_order_probe IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_order_probe (
    order_id,
    customer_id,
    order_status,
    placed_at,
    order_no,
    amount_minor,
    note
)
SELECT
    gs,
    1 + ((gs - 1) % 1000),
    CASE ((gs - 1) / 1000) % 20
        WHEN 0 THEN 'placed'
        WHEN 1 THEN 'draft'
        WHEN 2 THEN 'cancelled'
        ELSE 'paid'
    END,
    timestamptz '2025-01-01 00:00:00+00'
        + gs * interval '1 second',
    'LAB-ORDER-' || pg_catalog.lpad(gs::text, 9, '0'),
    1000 + (gs % 100000),
    pg_catalog.repeat('o', 96)
FROM pg_catalog.generate_series(1, 200000) AS seed(gs);

\echo '[setup] inventory fixture: existing warehouse-first primary key'

CREATE TABLE shop_private.ch09_inventory_probe (
    warehouse_id integer NOT NULL,
    sku_id bigint NOT NULL,
    available integer NOT NULL,
    reserved integer NOT NULL,
    updated_at timestamptz NOT NULL,
    payload text NOT NULL,
    CONSTRAINT ch09_inventory_probe_pkey
        PRIMARY KEY (warehouse_id, sku_id),
    CONSTRAINT ch09_inventory_probe_quantity_check
        CHECK (available >= 0 AND reserved >= 0)
);

ALTER TABLE shop_private.ch09_inventory_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_inventory_probe IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_inventory_probe (
    warehouse_id,
    sku_id,
    available,
    reserved,
    updated_at,
    payload
)
SELECT
    warehouse_id,
    sku_id,
    (sku_id * 13 + warehouse_id) % 500,
    (sku_id * 7 + warehouse_id) % 20,
    timestamptz '2025-01-01 00:00:00+00'
        + (warehouse_id * interval '1 day')
        + (sku_id * interval '1 second'),
    pg_catalog.repeat('i', 64)
FROM pg_catalog.generate_series(1, 30) AS warehouses(warehouse_id)
CROSS JOIN pg_catalog.generate_series(1, 10000) AS skus(sku_id)
ORDER BY warehouse_id, sku_id;

\echo '[setup] search fixture: generated tsvector with 100 target rows'

CREATE TABLE shop_private.ch09_search_probe (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    description text NOT NULL,
    tags text[] NOT NULL,
    attributes jsonb NOT NULL,
    search_document tsvector
        GENERATED ALWAYS AS (
            pg_catalog.to_tsvector(
                'simple'::regconfig,
                product_name || ' ' || description
            )
        ) STORED
);

ALTER TABLE shop_private.ch09_search_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_search_probe IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_search_probe (
    product_id,
    product_name,
    description,
    tags,
    attributes
)
SELECT
    gs,
    CASE WHEN gs % 1000 = 0
         THEN 'PostgreSQL Observability Mug'
         ELSE 'Catalog Product ' || gs
    END,
    CASE WHEN gs % 1000 = 0
         THEN 'postgresql observability field guide'
         ELSE 'ordinary catalog item for deterministic search'
    END,
    CASE WHEN gs % 1000 = 0
         THEN ARRAY['postgresql', 'observability']
         ELSE ARRAY['catalog', 'ordinary']
    END,
    pg_catalog.jsonb_build_object(
        'color', CASE gs % 3
            WHEN 0 THEN 'red'
            WHEN 1 THEN 'green'
            ELSE 'blue'
        END,
        'bucket', gs % 100
    )
FROM pg_catalog.generate_series(1, 100000) AS seed(gs);

\echo '[setup] event fixture: physically ordered time series'

CREATE TABLE shop_private.ch09_event_probe (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    event_kind integer NOT NULL,
    payload text NOT NULL
);

ALTER TABLE shop_private.ch09_event_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_event_probe IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_event_probe (
    event_id,
    occurred_at,
    event_kind,
    payload
)
SELECT
    gs,
    timestamptz '2025-01-01 00:00:00+00'
        + gs * interval '1 second',
    (gs % 32)::integer,
    pg_catalog.repeat('e', 64)
FROM pg_catalog.generate_series(1, 400000) AS seed(gs)
ORDER BY gs;

\echo '[setup] twin write fixtures for HOT and WAL comparison'

CREATE TABLE shop_private.ch09_write_base (
    row_id bigint PRIMARY KEY,
    stable_key bigint NOT NULL,
    volatile_counter integer NOT NULL,
    payload text NOT NULL
) WITH (
    fillfactor = 50,
    autovacuum_enabled = false
);

CREATE TABLE shop_private.ch09_write_indexed (
    row_id bigint PRIMARY KEY,
    stable_key bigint NOT NULL,
    volatile_counter integer NOT NULL,
    payload text NOT NULL
) WITH (
    fillfactor = 50,
    autovacuum_enabled = false
);

ALTER TABLE shop_private.ch09_write_base OWNER TO pg36_owner;
ALTER TABLE shop_private.ch09_write_indexed OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_write_base IS
    'pg36 ch09 deterministic index lab; safe to rebuild';
COMMENT ON TABLE shop_private.ch09_write_indexed IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_write_base
SELECT gs, gs % 10000, 0, pg_catalog.repeat('w', 96)
FROM pg_catalog.generate_series(1, 50000) AS seed(gs);

INSERT INTO shop_private.ch09_write_indexed
SELECT *
FROM shop_private.ch09_write_base
ORDER BY row_id;

CREATE INDEX ch09_write_indexed_counter_idx
    ON shop_private.ch09_write_indexed (volatile_counter);

\echo '[setup] duplicate fixture for failed unique concurrent build'

CREATE TABLE shop_private.ch09_unique_probe (
    row_id bigint PRIMARY KEY,
    external_ref text NOT NULL
);

ALTER TABLE shop_private.ch09_unique_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch09_unique_probe IS
    'pg36 ch09 deterministic index lab; safe to rebuild';

INSERT INTO shop_private.ch09_unique_probe
SELECT
    gs,
    'duplicate-ref-' || ((gs + 1) / 2)
FROM pg_catalog.generate_series(1, 10000) AS seed(gs);

ANALYZE shop_private.ch09_order_probe;
ANALYZE shop_private.ch09_inventory_probe;
ANALYZE shop_private.ch09_search_probe;
ANALYZE shop_private.ch09_event_probe;
ANALYZE shop_private.ch09_write_base;
ANALYZE shop_private.ch09_write_indexed;
ANALYZE shop_private.ch09_unique_probe;

VACUUM (FREEZE, ANALYZE) shop_private.ch09_write_base;
VACUUM (FREEZE, ANALYZE) shop_private.ch09_write_indexed;

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'order_rows=' || count(*)
FROM shop_private.ch09_order_probe;
SELECT 'order_placed_rows=' || count(*)
FROM shop_private.ch09_order_probe
WHERE order_status = 'placed';
SELECT 'inventory_rows=' || count(*)
FROM shop_private.ch09_inventory_probe;
SELECT 'inventory_sku_4242_rows=' || count(*)
FROM shop_private.ch09_inventory_probe
WHERE sku_id = 4242;
SELECT 'search_rows=' || count(*)
FROM shop_private.ch09_search_probe;
SELECT 'search_target_rows=' || count(*)
FROM shop_private.ch09_search_probe
WHERE search_document @@
      pg_catalog.plainto_tsquery(
          'simple'::regconfig,
          'postgresql observability'
      );
SELECT 'event_rows=' || count(*)
FROM shop_private.ch09_event_probe;
SELECT 'write_rows_each=' || count(*)
FROM shop_private.ch09_write_base;
SELECT 'duplicate_groups=' || count(*)
FROM (
    SELECT external_ref
    FROM shop_private.ch09_unique_probe
    GROUP BY external_ref
    HAVING count(*) = 2
) AS duplicate_set;
