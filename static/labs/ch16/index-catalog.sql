\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    index_relation.relname AS index_name,
    table_relation.relname AS table_name,
    access_method.amname AS access_method,
    pg_catalog.string_agg(
        operator_namespace.nspname || '.' ||
            operator_class.opcname,
        ',' ORDER BY operator_position.ordinality
    ) AS operator_classes,
    index_catalog.indisvalid AS is_valid,
    index_catalog.indisready AS is_ready,
    index_catalog.indislive AS is_live,
    pg_catalog.pg_relation_size(
        index_relation.oid
    ) AS index_bytes,
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
CROSS JOIN LATERAL
    pg_catalog.unnest(
        index_catalog.indclass::oid[]
    ) WITH ORDINALITY AS operator_position(
        operator_class_oid,
        ordinality
    )
JOIN pg_catalog.pg_opclass AS operator_class
  ON operator_class.oid =
         operator_position.operator_class_oid
JOIN pg_catalog.pg_namespace AS operator_namespace
  ON operator_namespace.oid =
         operator_class.opcnamespace
WHERE namespace.nspname = 'shop_ch16'
  AND index_relation.relname IN (
      'ingest_attempt_event_idx',
      'geofence_version_no_overlap',
      'geofence_version_geom_gist_idx',
      'delivery_hub_location_spgist_idx',
      'event_20260307_courier_time_idx',
      'event_20260307_location_gist_idx',
      'event_20260307_geog_gist_idx',
      'event_20260308_courier_time_idx',
      'event_20260308_location_gist_idx',
      'event_20260308_geog_gist_idx',
      'event_20260309_courier_time_idx',
      'event_20260309_location_gist_idx',
      'event_20260309_geog_gist_idx'
  )
GROUP BY
    index_relation.oid,
    index_relation.relname,
    table_relation.relname,
    access_method.amname,
    index_catalog.indisvalid,
    index_catalog.indisready,
    index_catalog.indislive
ORDER BY index_relation.relname;
