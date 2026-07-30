\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    source,
    target,
    coalesce(path, '') AS path
FROM pg_catalog.pg_extension_update_paths('pg_trgm')
WHERE source = '1.3'
   OR target = '1.6'
ORDER BY source, target;
