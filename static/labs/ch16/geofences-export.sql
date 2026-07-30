\set ON_ERROR_STOP on
\pset pager off

COPY (
    SELECT
        zone_id,
        version,
        pg_catalog.to_char(
            pg_catalog.lower(valid_during) AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        ) AS valid_from,
        pg_catalog.to_char(
            pg_catalog.upper(valid_during) AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        ) AS valid_to,
        shop_ch16_ext.ST_AsText(zone_geom) AS wkt
    FROM shop_ch16.geofence_version
    ORDER BY zone_id, version
) TO STDOUT WITH (
    FORMAT csv,
    HEADER true
);
