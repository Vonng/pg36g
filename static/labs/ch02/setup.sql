\set ON_ERROR_STOP on
\ir context.sql

BEGIN;

CREATE TABLE IF NOT EXISTS shop.ch02_fixture (
    fixture_id integer PRIMARY KEY,
    sku        text NOT NULL UNIQUE,
    label      text NOT NULL,
    amount     numeric(10,2) NOT NULL CHECK (amount >= 0),
    payload    text NOT NULL
);

DO $shape_guard$
DECLARE
    actual_shape text[];
    expected_shape constant text[] := ARRAY[
        'fixture_id:integer:not-null',
        'sku:text:not-null',
        'label:text:not-null',
        'amount:numeric(10,2):not-null',
        'payload:text:not-null'
    ];
BEGIN
    SELECT pg_catalog.array_agg(
               pg_catalog.format(
                   '%s:%s:%s',
                   a.attname,
                   pg_catalog.format_type(a.atttypid, a.atttypmod),
                   CASE WHEN a.attnotnull THEN 'not-null' ELSE 'nullable' END
               )
               ORDER BY a.attnum
           )
      INTO actual_shape
      FROM pg_catalog.pg_attribute AS a
     WHERE a.attrelid = 'shop.ch02_fixture'::regclass
       AND a.attnum > 0
       AND NOT a.attisdropped;

    IF actual_shape IS DISTINCT FROM expected_shape THEN
        RAISE EXCEPTION
            'shop.ch02_fixture shape drifted: expected %, got %',
            expected_shape,
            actual_shape;
    END IF;
END
$shape_guard$;

TRUNCATE TABLE shop.ch02_fixture;

INSERT INTO shop.ch02_fixture (fixture_id, sku, label, amount, payload)
SELECT
    n,
    'SKU-' || pg_catalog.lpad(n::text, 4, '0'),
    'fixture-' || pg_catalog.substr(pg_catalog.md5('label:' || n), 1, 12),
    (((n * 37) % 10000)::numeric / 100)::numeric(10,2),
    pg_catalog.md5('pg36:' || n)
FROM pg_catalog.generate_series(1, 100) AS g(n)
ORDER BY n;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE shop.ch02_fixture
TO pg36_app;

GRANT SELECT
ON TABLE shop.ch02_fixture
TO pg36_ro;

COMMIT;

\echo '[setup] deterministic fixture is ready'
