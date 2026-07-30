\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    extension_catalog.extname AS extension_name,
    extension_catalog.extversion AS extension_version,
    namespace.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(
        extension_catalog.extowner
    ) AS owner,
    extension_catalog.extrelocatable AS relocatable,
    available.trusted,
    available.superuser,
    pg_catalog.obj_description(
        extension_catalog.oid,
        'pg_extension'
    ) AS marker
FROM pg_catalog.pg_extension AS extension_catalog
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = extension_catalog.extnamespace
JOIN pg_catalog.pg_available_extension_versions AS available
  ON available.name = extension_catalog.extname
 AND available.version = extension_catalog.extversion
WHERE extension_catalog.extname IN (
    'btree_gist',
    'postgis'
)
ORDER BY extension_catalog.extname;
