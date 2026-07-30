\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH candidate (
    candidate,
    extension_name,
    package_alias,
    decision
) AS (
    VALUES
        (
            'bounded-fuzzy-search',
            'pg_trgm',
            'pgsql-main',
            'accept'
        ),
        (
            'semantic-retrieval',
            'vector',
            'pgvector',
            'pilot'
        ),
        (
            'distributed-sharding',
            'citus',
            'citus',
            'reject'
        )
)
SELECT
    candidate.candidate,
    candidate.extension_name,
    candidate.package_alias,
    candidate.decision,
    available.name IS NOT NULL AS locally_available,
    coalesce(
        available.default_version,
        ''
    ) AS default_version,
    coalesce(
        installed.extversion,
        ''
    ) AS installed_version
FROM candidate
LEFT JOIN pg_catalog.pg_available_extensions AS available
  ON available.name = candidate.extension_name
LEFT JOIN pg_catalog.pg_extension AS installed
  ON installed.extname = candidate.extension_name
ORDER BY candidate.candidate;
