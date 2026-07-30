\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    index_relation.relname AS index_name,
    access_method.amname AS access_method,
    operator_namespace.nspname || '.' ||
        operator_class.opcname AS operator_class,
    index_catalog.indisvalid AS is_valid,
    index_catalog.indisready AS is_ready,
    index_catalog.indislive AS is_live,
    pg_catalog.pg_get_indexdef(
        index_relation.oid
    ) AS index_definition,
    pg_catalog.obj_description(
        index_relation.oid,
        'pg_class'
    ) AS marker
FROM pg_catalog.pg_index AS index_catalog
JOIN pg_catalog.pg_class AS index_relation
  ON index_relation.oid = index_catalog.indexrelid
JOIN pg_catalog.pg_class AS table_relation
  ON table_relation.oid = index_catalog.indrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = table_relation.relnamespace
JOIN pg_catalog.pg_am AS access_method
  ON access_method.oid = index_relation.relam
JOIN pg_catalog.pg_opclass AS operator_class
  ON operator_class.oid = index_catalog.indclass[0]
JOIN pg_catalog.pg_namespace AS operator_namespace
  ON operator_namespace.oid = operator_class.opcnamespace
WHERE namespace.nspname = 'shop_ch14'
  AND index_relation.relname IN (
      'candidate_doc_title_trgm_idx',
      'candidate_doc_embedding_hnsw_idx'
  )
ORDER BY index_relation.relname;
