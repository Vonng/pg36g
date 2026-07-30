\set ON_ERROR_STOP on
\ir plan-context.sql

SELECT
    table_class.relname AS table_name,
    index_class.relname AS index_name,
    access_method.amname AS access_method,
    index_catalog.indisvalid,
    index_catalog.indisready,
    index_catalog.indisunique,
    index_catalog.indnkeyatts,
    index_catalog.indnatts,
    pg_catalog.pg_relation_size(index_catalog.indexrelid)
        AS index_bytes,
    pg_catalog.pg_get_indexdef(index_catalog.indexrelid)
        AS index_definition
FROM pg_catalog.pg_index AS index_catalog
JOIN pg_catalog.pg_class AS index_class
  ON index_class.oid = index_catalog.indexrelid
JOIN pg_catalog.pg_class AS table_class
  ON table_class.oid = index_catalog.indrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_class.relnamespace
JOIN pg_catalog.pg_am AS access_method
  ON access_method.oid = index_class.relam
WHERE namespace.nspname = 'shop_private'
  AND table_class.relname LIKE 'ch09_%'
ORDER BY table_class.relname, index_class.relname;
