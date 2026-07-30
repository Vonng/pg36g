\ir plan-context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT order_no, placed_at, amount_minor
FROM shop_private.ch09_order_probe
WHERE customer_id = 42
  AND order_status = 'placed'
ORDER BY placed_at DESC
LIMIT 20;
