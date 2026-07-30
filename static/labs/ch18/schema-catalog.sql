\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
\ir context.sql

SELECT
    namespace.nspname AS schema_name,
    pg_catalog.pg_get_userbyid(
        namespace.nspowner
    ) AS owner_name,
    COALESCE(
        pg_catalog.obj_description(
            namespace.oid,
            'pg_namespace'
        ),
        ''
    ) AS comment,
    (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = namespace.oid
          AND relation.relkind IN (
              'r',
              'p',
              'v',
              'm',
              'f',
              'S'
          )
    ) AS relation_count,
    (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = namespace.oid
    ) AS routine_count
FROM pg_catalog.pg_namespace AS namespace
WHERE namespace.nspname IN (
    'shop',
    'shop_private',
    'shop_ch13',
    'shop_ch14',
    'shop_ch15',
    'shop_ch16',
    'shop_ch16_ext',
    'shop_ch17',
    'shop_ch17_ext'
)
ORDER BY namespace.nspname;

COMMIT;
