\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    hub.hub_id,
    nearest.event_id AS nearest_event_id,
    pg_catalog.round(
        shop_ch16_ext.ST_Distance(
            hub.location::shop_ch16_ext.geography,
            nearest.location_geog
        )
    )::bigint AS distance_meters,
    shop_ch16_ext.ST_DWithin(
        hub.location::shop_ch16_ext.geography,
        nearest.location_geog,
        1000
    ) AS within_1km
FROM shop_ch16.delivery_hub AS hub
CROSS JOIN LATERAL (
    SELECT
        event.event_id,
        event.location_geog
    FROM shop_ch16.delivery_event AS event
    ORDER BY
        event.location
        OPERATOR(shop_ch16_ext.<->)
        hub.location,
        event.event_id
    LIMIT 1
) AS nearest
ORDER BY hub.hub_id;
