\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
\ir context.sql

SELECT
    extension_catalog.extname AS extension_name,
    extension_catalog.extversion AS extension_version,
    namespace.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(
        extension_catalog.extowner
    ) AS owner_name,
    extension_catalog.extrelocatable AS relocatable,
    COALESCE(
        pg_catalog.obj_description(
            extension_catalog.oid,
            'pg_extension'
        ),
        ''
    ) AS comment
FROM pg_catalog.pg_extension AS extension_catalog
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = extension_catalog.extnamespace
WHERE extension_catalog.extname IN (
    'btree_gist',
    'pg_trgm',
    'plpgsql',
    'postgis',
    'postgres_fdw',
    'vector'
)
ORDER BY extension_catalog.extname;

COMMIT;
