\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    extension_catalog.extname AS extension_name,
    extension_catalog.extversion AS object_version,
    pg_catalog.pg_get_userbyid(
        extension_catalog.extowner
    ) AS owner_name,
    namespace.nspname AS schema_name,
    extension_catalog.extrelocatable AS relocatable,
    available.superuser,
    available.trusted,
    coalesce(
        pg_catalog.array_to_string(
            available.requires,
            ','
        ),
        ''
    ) AS requires,
    (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_depend AS dependency
        WHERE dependency.refclassid =
                  'pg_catalog.pg_extension'::pg_catalog.regclass
          AND dependency.refobjid = extension_catalog.oid
          AND dependency.deptype = 'e'
    ) AS member_count,
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
WHERE extension_catalog.extname IN ('pg_trgm', 'vector')
ORDER BY extension_catalog.extname;
