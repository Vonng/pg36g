\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT event_id
FROM shop_ch16.delivery_event
WHERE (
          occurred_at AT TIME ZONE 'UTC'
      )::date = DATE '2026-03-08'
ORDER BY occurred_at, event_id;
