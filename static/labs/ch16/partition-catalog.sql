\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    child.relname AS partition_name,
    pg_catalog.pg_get_expr(
        child.relpartbound,
        child.oid
    ) AS partition_bound,
    pg_catalog.count(event.event_id) AS event_count,
    pg_catalog.min(event.occurred_at) AS min_occurred_at,
    pg_catalog.max(event.occurred_at) AS max_occurred_at,
    pg_catalog.pg_get_userbyid(
        child.relowner
    ) AS owner,
    pg_catalog.obj_description(
        child.oid,
        'pg_class'
    ) AS marker
FROM pg_catalog.pg_inherits AS inheritance
JOIN pg_catalog.pg_class AS parent
  ON parent.oid = inheritance.inhparent
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = parent.relnamespace
JOIN pg_catalog.pg_class AS child
  ON child.oid = inheritance.inhrelid
LEFT JOIN shop_ch16.delivery_event AS event
  ON event.tableoid = child.oid
WHERE namespace.nspname = 'shop_ch16'
  AND parent.relname = 'delivery_event'
GROUP BY
    child.oid,
    child.relname,
    child.relpartbound,
    child.relowner
ORDER BY child.relname;
