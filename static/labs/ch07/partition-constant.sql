\ir plan-context.sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT event_id
FROM shop_private.ch07_event_probe
WHERE occurred_on = date '2025-05-15';
