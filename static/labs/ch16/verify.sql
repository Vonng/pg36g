\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    data_schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch16');
    extension_schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch16_ext');
    expected_marker constant text :=
        'pg36 ch16 spatiotemporal lab; safe to rebuild';
    actual_checksum text;
BEGIN
    IF data_schema_oid IS NULL
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = data_schema_oid
              )
          ) <> 'pg36_owner'
       OR pg_catalog.obj_description(
              data_schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'ch16 data schema identity or marker drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = data_schema_oid
          AND (
              relation.relname <> ALL (ARRAY[
                  'fixture_meta',
                  'fixture_meta_pkey',
                  'ingest_attempt',
                  'ingest_attempt_pkey',
                  'ingest_attempt_event_idx',
                  'event_registry',
                  'event_registry_pkey',
                  'geofence_version',
                  'geofence_version_pkey',
                  'geofence_version_no_overlap',
                  'geofence_version_geom_gist_idx',
                  'delivery_hub',
                  'delivery_hub_pkey',
                  'delivery_hub_location_spgist_idx',
                  'delivery_event',
                  'delivery_event_pkey',
                  'delivery_event_20260307',
                  'delivery_event_20260307_pkey',
                  'event_20260307_courier_time_idx',
                  'event_20260307_location_gist_idx',
                  'event_20260307_geog_gist_idx',
                  'delivery_event_20260308',
                  'delivery_event_20260308_pkey',
                  'event_20260308_courier_time_idx',
                  'event_20260308_location_gist_idx',
                  'event_20260308_geog_gist_idx',
                  'delivery_event_20260309',
                  'delivery_event_20260309_pkey',
                  'event_20260309_courier_time_idx',
                  'event_20260309_location_gist_idx',
                  'event_20260309_geog_gist_idx',
                  'event_lateness',
                  'event_zone_membership',
                  'quarter_hour_volume'
              ])
              OR pg_catalog.obj_description(
                     relation.oid,
                     'pg_class'
                 ) IS DISTINCT FROM expected_marker
          )
    )
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_class AS relation
           WHERE relation.relnamespace = data_schema_oid
       ) <> 34 THEN
        RAISE EXCEPTION
            'ch16 data relation inventory or marker drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = data_schema_oid
    )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace =
                     data_schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opclass AS operator_class
           WHERE operator_class.opcnamespace =
                     data_schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opfamily AS operator_family
           WHERE operator_family.opfnamespace =
                     data_schema_oid
       ) THEN
        RAISE EXCEPTION
            'ch16 data schema contains unexpected catalog objects';
    END IF;

    IF extension_schema_oid IS NULL
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = extension_schema_oid
              )
          ) <> 'pg36_owner'
       OR pg_catalog.obj_description(
              extension_schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'ch16 extension schema identity or marker drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_extension
        WHERE extnamespace = extension_schema_oid
    ) <> 2
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           WHERE extension_catalog.extname = 'btree_gist'
             AND extension_catalog.extversion = '1.8'
             AND extension_catalog.extnamespace =
                     extension_schema_oid
             AND extension_catalog.extrelocatable
             AND pg_catalog.pg_get_userbyid(
                     extension_catalog.extowner
                 ) = 'pg36_owner'
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           JOIN pg_catalog.pg_roles AS role
             ON role.oid = extension_catalog.extowner
           WHERE extension_catalog.extname = 'postgis'
             AND extension_catalog.extversion = '3.6.4'
             AND extension_catalog.extnamespace =
                     extension_schema_oid
             AND NOT extension_catalog.extrelocatable
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION
            'ch16 extension inventory, version, or owner drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = extension_schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_class'::pg_catalog.regclass
                AND dependency.objid = relation.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_type'::pg_catalog.regclass
                AND dependency.objid = relation.reltype
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
          AND NOT (
              relation.relkind IN ('i', 'I')
              AND EXISTS (
                  SELECT 1
                  FROM pg_catalog.pg_index AS index_catalog
                  JOIN pg_catalog.pg_depend AS dependency
                    ON dependency.classid =
                           'pg_catalog.pg_class'::pg_catalog.regclass
                   AND dependency.objid =
                           index_catalog.indrelid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
                  WHERE index_catalog.indexrelid =
                            relation.oid
              )
          )
    )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace = extension_schema_oid
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_proc'::pg_catalog.regclass
                   AND dependency.objid = routine.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_type AS type_catalog
           WHERE type_catalog.typnamespace = extension_schema_oid
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_type'::pg_catalog.regclass
                   AND dependency.objid = type_catalog.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace =
                     extension_schema_oid
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_operator'::pg_catalog.regclass
                   AND dependency.objid = operator_catalog.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opclass AS operator_class
           WHERE operator_class.opcnamespace =
                     extension_schema_oid
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_opclass'::pg_catalog.regclass
                   AND dependency.objid = operator_class.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opfamily AS operator_family
           WHERE operator_family.opfnamespace =
                     extension_schema_oid
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_opfamily'::pg_catalog.regclass
                   AND dependency.objid = operator_family.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       ) THEN
        RAISE EXCEPTION
            'ch16 extension schema contains unmanaged objects';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch16.fixture_meta
        WHERE fixture_version = 'ch16-spatiotemporal-v1'
          AND attempts_identity = 'frozen-attempts.csv'
          AND geofences_identity = 'frozen-geofences.csv'
          AND hubs_identity = 'frozen-hubs.csv'
          AND event_time_basis = 'occurred_at'
          AND partition_timezone = 'UTC'
          AND coordinate_contract =
              'synthetic longitude/latitude in EPSG:4326'
          AND frozen_at =
              TIMESTAMPTZ '2026-07-29 00:00:00+00'
    ) <> 1 THEN
        RAISE EXCEPTION
            'ch16 fixture identity drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch16.ingest_attempt
    ) <> 13
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch16.event_registry
       ) <> 12
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch16.delivery_event
       ) <> 12
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch16.geofence_version
       ) <> 4
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch16.delivery_hub
       ) <> 3
       OR (
           SELECT pg_catalog.string_agg(
                      event_id || ':' || attempt_count::text,
                      ',' ORDER BY event_id
                  )
           FROM shop_ch16.event_registry
           WHERE attempt_count > 1
       ) <> 'e003:2'
       OR (
           SELECT canonical_attempt_id
           FROM shop_ch16.event_registry
           WHERE event_id = 'e003'
       ) <> 'a003' THEN
        RAISE EXCEPTION
            'ch16 fixture cardinality or deduplication drifted';
    END IF;

    IF (
        SELECT pg_catalog.string_agg(
                   tableoid::pg_catalog.regclass::text ||
                   ':' || event_count::text,
                   ',' ORDER BY
                       tableoid::pg_catalog.regclass::text
               )
        FROM (
            SELECT
                tableoid,
                pg_catalog.count(*) AS event_count
            FROM shop_ch16.delivery_event
            GROUP BY tableoid
        ) AS per_partition
    ) <>
       'shop_ch16.delivery_event_20260307:1,' ||
       'shop_ch16.delivery_event_20260308:7,' ||
       'shop_ch16.delivery_event_20260309:4'
       OR (
           SELECT tableoid
           FROM shop_ch16.delivery_event
           WHERE event_id = 'e008'
       ) <> 'shop_ch16.delivery_event_20260308'::pg_catalog.regclass
       OR (
           SELECT tableoid
           FROM shop_ch16.delivery_event
           WHERE event_id = 'e009'
       ) <> 'shop_ch16.delivery_event_20260309'::pg_catalog.regclass
       OR pg_catalog.pg_get_partkeydef(
              'shop_ch16.delivery_event'::pg_catalog.regclass
          ) <> 'RANGE (occurred_at)' THEN
        RAISE EXCEPTION
            'ch16 partition bounds, routing, or counts drifted';
    END IF;

    IF (
        SELECT occurred_at AT TIME ZONE 'America/New_York'
        FROM shop_ch16.delivery_event
        WHERE event_id = 'e002'
    ) <> TIMESTAMP '2026-03-08 01:55:00'
       OR (
           SELECT occurred_at AT TIME ZONE
                      'America/New_York'
           FROM shop_ch16.delivery_event
           WHERE event_id = 'e003'
       ) <> TIMESTAMP '2026-03-08 03:05:00'
       OR (
           SELECT later.occurred_at - earlier.occurred_at
           FROM shop_ch16.delivery_event AS earlier
           JOIN shop_ch16.delivery_event AS later
             ON earlier.event_id = 'e002'
            AND later.event_id = 'e003'
       ) <> INTERVAL '10 minutes'
       OR NOT EXISTS (
           SELECT 1
           FROM shop_ch16.delivery_event AS earlier
           JOIN shop_ch16.delivery_event AS later
             ON earlier.event_id = 'e004'
            AND later.event_id = 'e005'
            AND earlier.occurred_at < later.occurred_at
            AND earlier.received_at > later.received_at
       )
       OR (
           SELECT pg_catalog.string_agg(
                      event_id,
                      ',' ORDER BY occurred_at, event_id
                  )
           FROM shop_ch16.event_lateness
           WHERE is_late
       ) <> 'e001,e004' THEN
        RAISE EXCEPTION
            'ch16 DST, late, or out-of-order facts drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop_ch16.geofence_version
        WHERE NOT pg_catalog.lower_inc(valid_during)
           OR pg_catalog.upper_inc(valid_during)
           OR pg_catalog.isempty(valid_during)
           OR shop_ch16_ext.ST_SRID(zone_geom) <> 4326
           OR NOT shop_ch16_ext.ST_IsValid(zone_geom)
    )
       OR EXISTS (
           SELECT 1
           FROM shop_ch16.geofence_version AS left_zone
           JOIN shop_ch16.geofence_version AS right_zone
             ON left_zone.zone_id = right_zone.zone_id
            AND left_zone.version < right_zone.version
            AND left_zone.valid_during &&
                right_zone.valid_during
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_constraint AS constraint_catalog
           WHERE constraint_catalog.conrelid =
                     'shop_ch16.geofence_version'::pg_catalog.regclass
             AND constraint_catalog.conname =
                     'geofence_version_no_overlap'
             AND constraint_catalog.contype = 'x'
             AND constraint_catalog.convalidated
       ) THEN
        RAISE EXCEPTION
            'ch16 geofence range or geometry contract drifted';
    END IF;

    IF (
        SELECT pg_catalog.string_agg(
                   event_id || ':' || zone_id || ':' ||
                   zone_version::text,
                   ',' ORDER BY event_id, zone_id, zone_version
               )
        FROM shop_ch16.event_zone_membership
    ) <>
       'e001:central:1,e002:central:1,' ||
       'e003:central:1,e003:east:1,e004:east:1,' ||
       'e005:central:2,e005:east:1,' ||
       'e006:central:2,e006:east:1,' ||
       'e007:airport:1,e008:central:2,' ||
       'e009:central:2,e011:east:1,e012:airport:1'
       OR NOT EXISTS (
           SELECT 1
           FROM shop_ch16.delivery_event AS event
           JOIN shop_ch16.geofence_version AS zone
             ON zone.zone_id = 'central'
            AND zone.version = 1
           WHERE event.event_id = 'e003'
             AND shop_ch16_ext.ST_Covers(
                     zone.zone_geom,
                     event.location
                 )
             AND NOT shop_ch16_ext.ST_Contains(
                         zone.zone_geom,
                         event.location
                     )
             AND shop_ch16_ext.ST_Touches(
                     zone.zone_geom,
                     event.location
                 )
       )
       OR NOT EXISTS (
           SELECT 1
           FROM shop_ch16.delivery_event AS event
           JOIN shop_ch16.geofence_version AS zone
             ON zone.zone_id = 'central'
            AND zone.version = 2
           WHERE event.event_id = 'e005'
             AND shop_ch16_ext.ST_Contains(
                     zone.zone_geom,
                     event.location
                 )
       ) THEN
        RAISE EXCEPTION
            'ch16 membership, boundary, or version facts drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute
        WHERE attribute.attrelid =
                  'shop_ch16.delivery_event'::pg_catalog.regclass
          AND attribute.attname = 'location_geog'
          AND attribute.attgenerated = 's'
    )
       OR EXISTS (
           SELECT 1
           FROM shop_ch16.delivery_event
           WHERE shop_ch16_ext.ST_SRID(location) <> 4326
              OR shop_ch16_ext.ST_SRID(
                     location_geog::shop_ch16_ext.geometry
                 ) <> 4326
       ) THEN
        RAISE EXCEPTION
            'ch16 generated geography or SRID contract drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_catalog.indexrelid
        WHERE index_relation.relnamespace = data_schema_oid
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
          AND index_catalog.indisvalid
          AND index_catalog.indisready
          AND index_catalog.indislive
    ) <> 13
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           JOIN pg_catalog.pg_namespace AS operator_namespace
             ON operator_namespace.oid =
                    operator_class.opcnamespace
           WHERE index_relation.oid =
                     'shop_ch16.delivery_hub_location_spgist_idx'
                     ::pg_catalog.regclass
             AND access_method.amname = 'spgist'
             AND operator_class.opcname =
                     'spgist_geometry_ops_2d'
             AND operator_namespace.nspname =
                     'shop_ch16_ext'
       )
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           JOIN pg_catalog.pg_namespace AS operator_namespace
             ON operator_namespace.oid =
                    operator_class.opcnamespace
           WHERE index_relation.relnamespace = data_schema_oid
             AND index_relation.relname LIKE
                     'event_%_geog_gist_idx'
             AND access_method.amname = 'gist'
             AND operator_class.opcname =
                     'gist_geography_ops'
             AND operator_namespace.nspname =
                     'shop_ch16_ext'
       ) <> 3 THEN
        RAISE EXCEPTION
            'ch16 index validity, access method, or opclass drifted';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
               'pg36_app',
               'shop_ch16',
               'USAGE'
           )
       OR NOT pg_catalog.has_schema_privilege(
                  'pg36_app',
                  'shop_ch16_ext',
                  'USAGE'
              )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch16.delivery_event',
                  'SELECT'
              )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch16.event_zone_membership',
                  'SELECT'
              )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch16.delivery_event',
              'INSERT,UPDATE,DELETE'
          ) THEN
        RAISE EXCEPTION
            'ch16 application privilege boundary drifted';
    END IF;

    WITH business_rows AS (
        SELECT
            'attempt'::text AS kind,
            attempt_id AS sort_key,
            pg_catalog.concat_ws(
                '|',
                attempt_id,
                event_id,
                occurred_at,
                received_at,
                courier_id,
                event_type,
                longitude,
                latitude,
                source_sequence
            ) AS payload
        FROM shop_ch16.ingest_attempt

        UNION ALL

        SELECT
            'registry',
            event_id,
            pg_catalog.concat_ws(
                '|',
                event_id,
                canonical_attempt_id,
                first_received_at,
                last_received_at,
                attempt_count,
                payload_fingerprint
            )
        FROM shop_ch16.event_registry

        UNION ALL

        SELECT
            'geofence',
            zone_id || '|' ||
                pg_catalog.lpad(version::text, 4, '0'),
            pg_catalog.concat_ws(
                '|',
                zone_id,
                version,
                valid_during,
                shop_ch16_ext.ST_AsEWKT(zone_geom)
            )
        FROM shop_ch16.geofence_version

        UNION ALL

        SELECT
            'hub',
            hub_id,
            pg_catalog.concat_ws(
                '|',
                hub_id,
                hub_name,
                shop_ch16_ext.ST_AsEWKT(location)
            )
        FROM shop_ch16.delivery_hub

        UNION ALL

        SELECT
            'event',
            event_id,
            pg_catalog.concat_ws(
                '|',
                event_id,
                occurred_at,
                received_at,
                courier_id,
                event_type,
                source_sequence,
                shop_ch16_ext.ST_AsEWKT(location)
            )
        FROM shop_ch16.delivery_event

        UNION ALL

        SELECT
            'membership',
            event_id || '|' || zone_id || '|' ||
                pg_catalog.lpad(zone_version::text, 4, '0'),
            pg_catalog.concat_ws(
                '|',
                event_id,
                zone_id,
                zone_version
            )
        FROM shop_ch16.event_zone_membership
    )
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           )
    INTO actual_checksum
    FROM business_rows;

    IF actual_checksum <>
           '53f51cef1f0bed1a5c2fc89bfad109f4' THEN
        RAISE EXCEPTION
            'ch16 business checksum drifted: %',
            actual_checksum;
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=frozen-byte-identical';
SELECT 'time=event+ingest+validity';
SELECT 'space=geometry+geography+4326';
SELECT 'partition=utc-range-1+7+4';
SELECT 'membership=14';
SELECT 'business_checksum=53f51cef1f0bed1a5c2fc89bfad109f4';
