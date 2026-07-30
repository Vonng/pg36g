\ir plan-context.sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT probe_id
FROM shop_private.ch07_plan_probe
WHERE region = 'east'
  AND order_status = 'paid';
