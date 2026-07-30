\set ON_ERROR_STOP on
\ir context.sql

DO $verify$
BEGIN
    IF (SELECT count(*) FROM shop.ch02_fixture) <> 100 THEN
        RAISE EXCEPTION 'expected 100 fixture rows';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.ch02_fixture AS f
        WHERE f.sku <> 'SKU-' || pg_catalog.lpad(f.fixture_id::text, 4, '0')
           OR f.label <> 'fixture-' ||
                         pg_catalog.substr(
                             pg_catalog.md5('label:' || f.fixture_id),
                             1,
                             12
                         )
           OR f.amount <> (
               ((f.fixture_id * 37) % 10000)::numeric / 100
           )::numeric(10,2)
           OR f.payload <> pg_catalog.md5('pg36:' || f.fixture_id)
    ) THEN
        RAISE EXCEPTION 'one or more fixture rows are not deterministic';
    END IF;
END
$verify$;

SELECT key || '=' || value AS state
FROM (
    SELECT 1, 'status', 'ok'
    UNION ALL
    SELECT 2, 'database', current_database()
    UNION ALL
    SELECT 3, 'effective_role', current_user
    UNION ALL
    SELECT 4, 'row_count', count(*)::text
      FROM shop.ch02_fixture
    UNION ALL
    SELECT 5, 'min_id', min(fixture_id)::text
      FROM shop.ch02_fixture
    UNION ALL
    SELECT 6, 'max_id', max(fixture_id)::text
      FROM shop.ch02_fixture
    UNION ALL
    SELECT 7, 'checksum',
           pg_catalog.md5(
               string_agg(
                   fixture_id || '|' || sku || '|' || payload,
                   E'\n'
                   ORDER BY fixture_id
               )
           )
      FROM shop.ch02_fixture
) AS snapshot(ord, key, value)
ORDER BY ord;
