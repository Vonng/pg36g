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
WHERE date_trunc('month', occurred_on::timestamp)
      = timestamp '2025-05-01 00:00:00';
