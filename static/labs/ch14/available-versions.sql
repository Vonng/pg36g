\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    name AS extension_name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    coalesce(schema, '') AS required_schema,
    coalesce(
        pg_catalog.array_to_string(requires, ','),
        ''
    ) AS requires
FROM pg_catalog.pg_available_extension_versions
WHERE name IN ('pg_trgm', 'vector')
ORDER BY
    name,
    string_to_array(version, '.')::integer[];
