\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    object_name,
    bytes
FROM (
    VALUES
        (
            'delivery_event_parent_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch16.delivery_event'::pg_catalog.regclass
            )
        ),
        (
            'delivery_event_partitions_total',
            (
                SELECT pg_catalog.sum(
                           pg_catalog.pg_total_relation_size(
                               child.oid
                           )
                       )
                FROM pg_catalog.pg_inherits AS inheritance
                JOIN pg_catalog.pg_class AS child
                  ON child.oid = inheritance.inhrelid
                WHERE inheritance.inhparent =
                          'shop_ch16.delivery_event'::pg_catalog.regclass
            )
        ),
        (
            'geofence_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch16.geofence_version'::pg_catalog.regclass
            )
        ),
        (
            'hub_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch16.delivery_hub'::pg_catalog.regclass
            )
        ),
        (
            'ingest_total',
            pg_catalog.pg_total_relation_size(
                'shop_ch16.ingest_attempt'::pg_catalog.regclass
            )
        )
) AS size_fact(object_name, bytes)
ORDER BY object_name;
