\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

DO $data_collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch16');
    expected_marker constant text :=
        'pg36 ch16 spatiotemporal lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = schema_oid
              )
          ) <> 'pg36_owner' THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch16 identity drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND pg_catalog.obj_description(
                  relation.oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker
    )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opclass AS operator_class
           WHERE operator_class.opcnamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opfamily AS operator_family
           WHERE operator_family.opfnamespace = schema_oid
       ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch16 object inventory drifted';
    END IF;
END
$data_collision_guard$;

DROP VIEW IF EXISTS shop_ch16.quarter_hour_volume;
DROP VIEW IF EXISTS shop_ch16.event_zone_membership;
DROP VIEW IF EXISTS shop_ch16.event_lateness;
DROP TABLE IF EXISTS shop_ch16.delivery_event;
DROP TABLE IF EXISTS shop_ch16.delivery_hub;
DROP TABLE IF EXISTS shop_ch16.geofence_version;
DROP TABLE IF EXISTS shop_ch16.event_registry;
DROP TABLE IF EXISTS shop_ch16.ingest_attempt;
DROP TABLE IF EXISTS shop_ch16.fixture_meta;
DROP SCHEMA IF EXISTS shop_ch16;

DO $extension_collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch16_ext');
    expected_marker constant text :=
        'pg36 ch16 spatiotemporal lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_extension
            WHERE extname IN ('btree_gist', 'postgis')
        ) THEN
            RAISE EXCEPTION
                'refusing collision: ch16 extensions exist without their schema';
        END IF;
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = schema_oid
              )
          ) <> 'pg36_owner' THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch16_ext identity drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_extension
        WHERE extnamespace = schema_oid
    ) <> 2
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           WHERE extension_catalog.extname = 'btree_gist'
             AND extension_catalog.extversion = '1.8'
             AND extension_catalog.extnamespace = schema_oid
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
             AND extension_catalog.extnamespace = schema_oid
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION
            'refusing collision: ch16 extension inventory drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
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
                   AND dependency.objid = index_catalog.indrelid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
                  WHERE index_catalog.indexrelid = relation.oid
              )
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch16_ext has non-extension relations';
    END IF;
END
$extension_collision_guard$;

DROP EXTENSION IF EXISTS postgis;
DROP EXTENSION IF EXISTS btree_gist;
DROP SCHEMA IF EXISTS shop_ch16_ext;

CREATE SCHEMA shop_ch16_ext AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch16_ext IS
    'pg36 ch16 spatiotemporal lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch16_ext FROM PUBLIC;

SET ROLE pg36_owner;

CREATE EXTENSION btree_gist
    WITH SCHEMA shop_ch16_ext
    VERSION '1.8';

RESET ROLE;

CREATE EXTENSION postgis
    WITH SCHEMA shop_ch16_ext
    VERSION '3.6.4';

COMMENT ON EXTENSION btree_gist IS
    'pg36 ch16 spatiotemporal lab; safe to rebuild';
COMMENT ON EXTENSION postgis IS
    'pg36 ch16 spatiotemporal lab; safe to rebuild';

GRANT USAGE ON SCHEMA shop_ch16_ext
TO pg36_owner, pg36_app;

SET ROLE pg36_owner;

CREATE SCHEMA shop_ch16 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch16 IS
    'pg36 ch16 spatiotemporal lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch16 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch16 TO pg36_app;

CREATE TABLE shop_ch16.fixture_meta (
    fixture_version text PRIMARY KEY,
    attempts_identity text NOT NULL,
    geofences_identity text NOT NULL,
    hubs_identity text NOT NULL,
    event_time_basis text NOT NULL,
    partition_timezone text NOT NULL,
    coordinate_contract text NOT NULL,
    text_license text NOT NULL,
    coordinate_license text NOT NULL,
    frozen_at timestamptz NOT NULL
);

CREATE TABLE shop_ch16.ingest_attempt (
    attempt_id text PRIMARY KEY,
    event_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    courier_id text NOT NULL,
    event_type text NOT NULL,
    longitude numeric(8, 5) NOT NULL,
    latitude numeric(7, 5) NOT NULL,
    source_sequence integer NOT NULL,
    CONSTRAINT ingest_attempt_time_order
        CHECK (received_at >= occurred_at),
    CONSTRAINT ingest_attempt_event_type
        CHECK (
            event_type IN (
                'pickup',
                'position',
                'delivered'
            )
        ),
    CONSTRAINT ingest_attempt_longitude
        CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT ingest_attempt_latitude
        CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT ingest_attempt_sequence
        CHECK (source_sequence > 0)
);

CREATE INDEX ingest_attempt_event_idx
    ON shop_ch16.ingest_attempt (
        event_id,
        received_at,
        attempt_id
    );

CREATE TABLE shop_ch16.event_registry (
    event_id text PRIMARY KEY,
    canonical_attempt_id text NOT NULL
        REFERENCES shop_ch16.ingest_attempt(attempt_id)
        ON DELETE RESTRICT,
    first_received_at timestamptz NOT NULL,
    last_received_at timestamptz NOT NULL,
    attempt_count integer NOT NULL,
    payload_fingerprint text NOT NULL,
    CONSTRAINT event_registry_receive_order
        CHECK (last_received_at >= first_received_at),
    CONSTRAINT event_registry_attempt_count
        CHECK (attempt_count > 0),
    CONSTRAINT event_registry_fingerprint_shape
        CHECK (
            payload_fingerprint ~ '^[0-9a-f]{32}$'
        )
);

CREATE TABLE shop_ch16.geofence_version (
    zone_id text NOT NULL,
    version integer NOT NULL,
    valid_during tstzrange NOT NULL,
    zone_geom shop_ch16_ext.geometry(Polygon, 4326) NOT NULL,
    PRIMARY KEY (zone_id, version),
    CONSTRAINT geofence_version_no_overlap
        EXCLUDE USING gist (
            zone_id shop_ch16_ext.gist_text_ops WITH =,
            valid_during WITH &&
        ),
    CONSTRAINT geofence_version_positive
        CHECK (version > 0),
    CONSTRAINT geofence_version_nonempty
        CHECK (
            NOT pg_catalog.isempty(valid_during)
            AND pg_catalog.lower(valid_during) IS NOT NULL
            AND pg_catalog.upper(valid_during) IS NOT NULL
        ),
    CONSTRAINT geofence_version_half_open
        CHECK (
            pg_catalog.lower_inc(valid_during)
            AND NOT pg_catalog.upper_inc(valid_during)
        ),
    CONSTRAINT geofence_version_valid_geometry
        CHECK (
            shop_ch16_ext.ST_IsValid(zone_geom)
            AND shop_ch16_ext.ST_SRID(zone_geom) = 4326
        )
);

CREATE INDEX geofence_version_geom_gist_idx
    ON shop_ch16.geofence_version
    USING gist (
        zone_geom shop_ch16_ext.gist_geometry_ops_2d
    );

CREATE TABLE shop_ch16.delivery_hub (
    hub_id text PRIMARY KEY,
    hub_name text NOT NULL,
    location shop_ch16_ext.geometry(Point, 4326) NOT NULL,
    CONSTRAINT delivery_hub_srid
        CHECK (
            shop_ch16_ext.ST_SRID(location) = 4326
        )
);

CREATE INDEX delivery_hub_location_spgist_idx
    ON shop_ch16.delivery_hub
    USING spgist (
        location shop_ch16_ext.spgist_geometry_ops_2d
    );

CREATE TABLE shop_ch16.delivery_event (
    occurred_at timestamptz NOT NULL,
    event_id text NOT NULL
        REFERENCES shop_ch16.event_registry(event_id)
        ON DELETE RESTRICT,
    received_at timestamptz NOT NULL,
    courier_id text NOT NULL,
    event_type text NOT NULL,
    location shop_ch16_ext.geometry(Point, 4326) NOT NULL,
    location_geog shop_ch16_ext.geography(Point, 4326)
        GENERATED ALWAYS AS (
            location::shop_ch16_ext.geography
        ) STORED,
    source_sequence integer NOT NULL,
    PRIMARY KEY (occurred_at, event_id),
    CONSTRAINT delivery_event_time_order
        CHECK (received_at >= occurred_at),
    CONSTRAINT delivery_event_type
        CHECK (
            event_type IN (
                'pickup',
                'position',
                'delivered'
            )
        ),
    CONSTRAINT delivery_event_srid
        CHECK (
            shop_ch16_ext.ST_SRID(location) = 4326
        ),
    CONSTRAINT delivery_event_sequence
        CHECK (source_sequence > 0)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE shop_ch16.delivery_event_20260307
    PARTITION OF shop_ch16.delivery_event
    FOR VALUES FROM (
        TIMESTAMPTZ '2026-03-07 00:00:00+00'
    ) TO (
        TIMESTAMPTZ '2026-03-08 00:00:00+00'
    );

CREATE TABLE shop_ch16.delivery_event_20260308
    PARTITION OF shop_ch16.delivery_event
    FOR VALUES FROM (
        TIMESTAMPTZ '2026-03-08 00:00:00+00'
    ) TO (
        TIMESTAMPTZ '2026-03-09 00:00:00+00'
    );

CREATE TABLE shop_ch16.delivery_event_20260309
    PARTITION OF shop_ch16.delivery_event
    FOR VALUES FROM (
        TIMESTAMPTZ '2026-03-09 00:00:00+00'
    ) TO (
        TIMESTAMPTZ '2026-03-10 00:00:00+00'
    );

CREATE INDEX event_20260307_courier_time_idx
    ON shop_ch16.delivery_event_20260307 (
        courier_id,
        occurred_at
    );
CREATE INDEX event_20260308_courier_time_idx
    ON shop_ch16.delivery_event_20260308 (
        courier_id,
        occurred_at
    );
CREATE INDEX event_20260309_courier_time_idx
    ON shop_ch16.delivery_event_20260309 (
        courier_id,
        occurred_at
    );

CREATE INDEX event_20260307_location_gist_idx
    ON shop_ch16.delivery_event_20260307
    USING gist (
        location shop_ch16_ext.gist_geometry_ops_2d
    );
CREATE INDEX event_20260308_location_gist_idx
    ON shop_ch16.delivery_event_20260308
    USING gist (
        location shop_ch16_ext.gist_geometry_ops_2d
    );
CREATE INDEX event_20260309_location_gist_idx
    ON shop_ch16.delivery_event_20260309
    USING gist (
        location shop_ch16_ext.gist_geometry_ops_2d
    );

CREATE INDEX event_20260307_geog_gist_idx
    ON shop_ch16.delivery_event_20260307
    USING gist (
        location_geog shop_ch16_ext.gist_geography_ops
    );
CREATE INDEX event_20260308_geog_gist_idx
    ON shop_ch16.delivery_event_20260308
    USING gist (
        location_geog shop_ch16_ext.gist_geography_ops
    );
CREATE INDEX event_20260309_geog_gist_idx
    ON shop_ch16.delivery_event_20260309
    USING gist (
        location_geog shop_ch16_ext.gist_geography_ops
    );

\ir fixture.sql

CREATE VIEW shop_ch16.event_lateness AS
SELECT
    event.occurred_at,
    event.event_id,
    event.received_at,
    event.courier_id,
    event.event_type,
    event.source_sequence,
    extract(
        epoch FROM (
            event.received_at - event.occurred_at
        )
    )::bigint AS delay_seconds,
    (
        event.received_at - event.occurred_at
    ) > INTERVAL '5 minutes' AS is_late
FROM shop_ch16.delivery_event AS event;

CREATE VIEW shop_ch16.event_zone_membership AS
SELECT
    event.occurred_at,
    event.event_id,
    event.courier_id,
    event.event_type,
    zone.zone_id,
    zone.version AS zone_version,
    event.location
FROM shop_ch16.delivery_event AS event
JOIN shop_ch16.geofence_version AS zone
  ON zone.valid_during @> event.occurred_at
 AND shop_ch16_ext.ST_Covers(
         zone.zone_geom,
         event.location
     );

CREATE VIEW shop_ch16.quarter_hour_volume AS
SELECT
    pg_catalog.date_bin(
        INTERVAL '15 minutes',
        event.occurred_at,
        TIMESTAMPTZ '2001-01-01 00:00:00+00'
    ) AS bucket_start,
    pg_catalog.count(*) AS event_count,
    pg_catalog.count(*) FILTER (
        WHERE lateness.is_late
    ) AS late_event_count
FROM shop_ch16.delivery_event AS event
JOIN shop_ch16.event_lateness AS lateness
  USING (occurred_at, event_id)
GROUP BY bucket_start;

DO $mark_relations$
DECLARE
    relation record;
    marker constant text :=
        'pg36 ch16 spatiotemporal lab; safe to rebuild';
BEGIN
    FOR relation IN
        SELECT
            namespace.nspname AS schema_name,
            catalog.relname AS relation_name,
            catalog.relkind
        FROM pg_catalog.pg_class AS catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = catalog.relnamespace
        WHERE namespace.nspname = 'shop_ch16'
    LOOP
        IF relation.relkind IN ('r', 'p') THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON TABLE %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind IN ('i', 'I') THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON INDEX %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind = 'v' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON VIEW %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSE
            RAISE EXCEPTION
                'unexpected ch16 relation kind: %.% %',
                relation.schema_name,
                relation.relation_name,
                relation.relkind;
        END IF;
    END LOOP;
END
$mark_relations$;

GRANT SELECT ON
    shop_ch16.delivery_event,
    shop_ch16.delivery_hub,
    shop_ch16.event_lateness,
    shop_ch16.event_zone_membership,
    shop_ch16.quarter_hour_volume
TO pg36_app;

ANALYZE shop_ch16.ingest_attempt;
ANALYZE shop_ch16.event_registry;
ANALYZE shop_ch16.geofence_version;
ANALYZE shop_ch16.delivery_hub;
ANALYZE shop_ch16.delivery_event;

RESET ROLE;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=fixture-ready';
SELECT 'attempts=' ||
       pg_catalog.count(*)::text
FROM shop_ch16.ingest_attempt;
SELECT 'events=' ||
       pg_catalog.count(*)::text
FROM shop_ch16.delivery_event;
SELECT 'geofence_versions=' ||
       pg_catalog.count(*)::text
FROM shop_ch16.geofence_version;
SELECT 'postgis=' ||
       extversion
FROM pg_catalog.pg_extension
WHERE extname = 'postgis';
