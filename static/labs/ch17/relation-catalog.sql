\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    relation.relkind,
    relation.relname AS relation_name,
    pg_catalog.pg_get_userbyid(
        relation.relowner
    ) AS owner,
    pg_catalog.obj_description(
        relation.oid,
        'pg_class'
    ) AS marker,
    CASE
        WHEN relation.relispartition THEN
            pg_catalog.pg_get_expr(
                relation.relpartbound,
                relation.oid
            )
        ELSE NULL
    END AS partition_bound,
    CASE
        WHEN relation.relkind = 'f' THEN
            server_catalog.srvname
        ELSE NULL
    END AS foreign_server
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
LEFT JOIN pg_catalog.pg_foreign_table AS foreign_table
  ON foreign_table.ftrelid = relation.oid
LEFT JOIN pg_catalog.pg_foreign_server AS server_catalog
  ON server_catalog.oid = foreign_table.ftserver
WHERE namespace.nspname = 'shop_ch17'
ORDER BY relation.relkind, relation.relname;
