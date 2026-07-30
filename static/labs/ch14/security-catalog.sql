\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    'app_schema_usage' AS key,
    pg_catalog.has_schema_privilege(
        'pg36_app',
        'shop_ch14',
        'USAGE'
    )::text AS value
UNION ALL
SELECT
    'app_review_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch14.extension_review',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_doc_select',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch14.candidate_doc',
        'SELECT'
    )::text
UNION ALL
SELECT
    'app_doc_insert',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch14.candidate_doc',
        'INSERT'
    )::text
UNION ALL
SELECT
    'app_doc_update',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch14.candidate_doc',
        'UPDATE'
    )::text
UNION ALL
SELECT
    'app_doc_delete',
    pg_catalog.has_table_privilege(
        'pg36_app',
        'shop_ch14.candidate_doc',
        'DELETE'
    )::text
UNION ALL
SELECT
    'pg_trgm_owned_by_owner',
    (
        SELECT pg_catalog.pg_get_userbyid(extowner) =
                   'pg36_owner'
        FROM pg_catalog.pg_extension
        WHERE extname = 'pg_trgm'
    )::text
UNION ALL
SELECT
    'vector_owned_by_superuser',
    (
        SELECT role.rolsuper
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_roles AS role
          ON role.oid = extension_catalog.extowner
        WHERE extension_catalog.extname = 'vector'
    )::text
ORDER BY key;
