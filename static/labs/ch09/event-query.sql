\ir plan-context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT event_id, occurred_at, event_kind
FROM shop_private.ch09_event_probe
WHERE occurred_at >= timestamptz '2025-01-03 07:33:20+00'
  AND occurred_at <  timestamptz '2025-01-03 07:43:20+00'
ORDER BY occurred_at;
