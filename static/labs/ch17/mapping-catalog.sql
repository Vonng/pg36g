\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    server_catalog.srvname AS server_name,
    CASE
        WHEN mapping.umuser = 0 THEN 'PUBLIC'
        ELSE pg_catalog.pg_get_userbyid(mapping.umuser)
    END AS local_user,
    pg_catalog.array_to_string(
        mapping.umoptions,
        ','
    ) AS mapping_options
FROM pg_catalog.pg_user_mapping AS mapping
JOIN pg_catalog.pg_foreign_server AS server_catalog
  ON server_catalog.oid = mapping.umserver
WHERE server_catalog.srvname IN (
    'pg36_ch17_shard_a',
    'pg36_ch17_shard_b'
)
ORDER BY server_catalog.srvname, local_user;
