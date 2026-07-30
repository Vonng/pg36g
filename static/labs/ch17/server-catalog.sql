\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    server_catalog.srvname AS server_name,
    wrapper.fdwname AS wrapper_name,
    pg_catalog.pg_get_userbyid(
        server_catalog.srvowner
    ) AS owner,
    pg_catalog.array_to_string(
        server_catalog.srvoptions,
        ','
    ) AS server_options,
    pg_catalog.obj_description(
        server_catalog.oid,
        'pg_foreign_server'
    ) AS marker
FROM pg_catalog.pg_foreign_server AS server_catalog
JOIN pg_catalog.pg_foreign_data_wrapper AS wrapper
  ON wrapper.oid = server_catalog.srvfdw
WHERE server_catalog.srvname IN (
    'pg36_ch17_shard_a',
    'pg36_ch17_shard_b'
)
ORDER BY server_catalog.srvname;
