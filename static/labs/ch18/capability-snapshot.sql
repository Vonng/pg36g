\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
\ir context.sql

WITH extension_state AS (
    SELECT extname, extversion
    FROM pg_catalog.pg_extension
),
schema_state AS (
    SELECT
        namespace.nspname,
        COALESCE(
            pg_catalog.obj_description(
                namespace.oid,
                'pg_namespace'
            ),
            ''
        ) AS marker
    FROM pg_catalog.pg_namespace AS namespace
)
SELECT capability_id, lifecycle, evidence
FROM (
    SELECT
        1 AS ord,
        'relational-core'::text AS capability_id,
        'accepted'::text AS lifecycle,
        CASE WHEN EXISTS (
            SELECT 1
            FROM shop_private.schema_version
            WHERE version = 1
              AND description = 'ch04 reliable physical model'
        ) THEN 'ch04-v1'
          ELSE 'missing'
        END AS evidence
    UNION ALL
    SELECT
        2,
        'atomic-database-logic',
        'accepted-with-scope',
        CASE WHEN EXISTS (
            SELECT 1
            FROM shop_ch13.schema_version
            WHERE version = 1
              AND description = 'ch13 routine guard lab'
        ) THEN 'ch13-routine-guard-v1'
          ELSE 'missing'
        END
    UNION ALL
    SELECT
        3,
        'lexical-and-fuzzy-search',
        'accepted',
        COALESCE(
            (
                SELECT 'pg_trgm:' || extversion
                FROM extension_state
                WHERE extname = 'pg_trgm'
            ),
            'missing'
        )
    UNION ALL
    SELECT
        4,
        'semantic-search',
        'pilot',
        COALESCE(
            (
                SELECT 'vector:' || extversion
                FROM extension_state
                WHERE extname = 'vector'
            ),
            'missing'
        )
    UNION ALL
    SELECT
        5,
        'spatiotemporal',
        'conditional',
        COALESCE(
            (
                SELECT pg_catalog.string_agg(
                    extname || ':' || extversion,
                    ',' ORDER BY extname
                )
                FROM extension_state
                WHERE extname IN ('btree_gist', 'postgis')
                HAVING pg_catalog.count(*) = 2
            ),
            'missing'
        )
    UNION ALL
    SELECT
        6,
        'analytical-federation',
        'lab-only',
        COALESCE(
            (
                SELECT 'postgres_fdw:' || extversion
                FROM extension_state
                WHERE extname = 'postgres_fdw'
            ),
            'missing'
        )
    UNION ALL
    SELECT
        7,
        'search-quality-fixture',
        'accepted',
        CASE WHEN EXISTS (
            SELECT 1
            FROM schema_state
            WHERE nspname = 'shop_ch15'
              AND marker =
                  'pg36 ch15 search quality lab; safe to rebuild'
        ) THEN 'ch15-search-v1'
          ELSE 'missing'
        END
    UNION ALL
    SELECT
        8,
        'spatiotemporal-fixture',
        'accepted',
        CASE WHEN EXISTS (
            SELECT 1
            FROM schema_state
            WHERE nspname = 'shop_ch16'
              AND marker =
                  'pg36 ch16 spatiotemporal lab; safe to rebuild'
        ) THEN 'ch16-spatiotemporal-v1'
          ELSE 'missing'
        END
    UNION ALL
    SELECT
        9,
        'analytics-fixture',
        'accepted',
        CASE WHEN EXISTS (
            SELECT 1
            FROM schema_state
            WHERE nspname = 'shop_ch17'
              AND marker =
                  'pg36 ch17 analytics fdw lab; safe to rebuild'
        ) THEN 'ch17-analytics-v1'
          ELSE 'missing'
        END
) AS capability
ORDER BY ord;

COMMIT;
