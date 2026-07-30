\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned

WITH database_fact AS (
    SELECT
        datname,
        pg_catalog.pg_encoding_to_char(
            encoding
        ) AS encoding,
        CASE datlocprovider
            WHEN 'b' THEN 'builtin'
            WHEN 'c' THEN 'libc'
            WHEN 'i' THEN 'icu'
            ELSE datlocprovider::text
        END AS locale_provider,
        datcollate,
        datctype,
        datlocale,
        datcollversion
    FROM pg_catalog.pg_database
    WHERE datname = current_database()
),
extension_fact AS (
    SELECT COALESCE(
        pg_catalog.jsonb_object_agg(
            extname,
            extversion
            ORDER BY extname
        ),
        '{}'::pg_catalog.jsonb
    ) AS extensions
    FROM pg_catalog.pg_extension
),
control_fact AS (
    SELECT
        system_identifier::text,
        pg_control_version,
        catalog_version_no
    FROM pg_catalog.pg_control_system()
),
checkpoint_fact AS (
    SELECT timeline_id
    FROM pg_catalog.pg_control_checkpoint()
)
SELECT pg_catalog.jsonb_pretty(
    pg_catalog.jsonb_build_object(
        'schema', 'pg36-ch19-postgresql-facts-v1',
        'cluster_name', current_setting('cluster_name'),
        'database', current_database(),
        'session_user', session_user,
        'server_version', current_setting('server_version'),
        'server_version_num',
            current_setting('server_version_num')::integer,
        'in_recovery', pg_catalog.pg_is_in_recovery(),
        'system_identifier', control_fact.system_identifier,
        'timeline_id', checkpoint_fact.timeline_id,
        'pg_control_version', control_fact.pg_control_version,
        'catalog_version_no', control_fact.catalog_version_no,
        'settings', pg_catalog.jsonb_build_object(
            'block_size_bytes',
                current_setting('block_size')::integer,
            'wal_segment_size_bytes',
                pg_catalog.pg_size_bytes(
                    current_setting('wal_segment_size')
                ),
            'data_checksums',
                current_setting('data_checksums'),
            'timezone',
                current_setting('TimeZone'),
            'password_encryption',
                current_setting('password_encryption'),
            'ssl',
                current_setting('ssl'),
            'archive_mode',
                current_setting('archive_mode'),
            'max_connections',
                current_setting('max_connections')::integer,
            'shared_buffers_bytes',
                pg_catalog.pg_size_bytes(
                    current_setting('shared_buffers')
                ),
            'shared_preload_libraries',
                current_setting('shared_preload_libraries')
        ),
        'database_identity', pg_catalog.to_jsonb(database_fact),
        'extensions', extension_fact.extensions
    )
)
FROM database_fact
CROSS JOIN extension_fact
CROSS JOIN control_fact
CROSS JOIN checkpoint_fact;
