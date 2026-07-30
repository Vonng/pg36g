\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    extension_catalog.extname AS extension_name,
    dependency.classid::pg_catalog.regclass::text
        AS member_catalog,
    pg_catalog.count(*) AS member_count
FROM pg_catalog.pg_extension AS extension_catalog
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.refclassid =
         'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.refobjid = extension_catalog.oid
 AND dependency.deptype = 'e'
WHERE extension_catalog.extname IN ('pg_trgm', 'vector')
GROUP BY
    extension_catalog.extname,
    dependency.classid
ORDER BY
    extension_catalog.extname,
    member_catalog;
