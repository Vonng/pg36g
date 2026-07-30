\ir plan-context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT warehouse_id, available, reserved, updated_at
FROM shop_private.ch09_inventory_probe
WHERE sku_id = 4242
ORDER BY warehouse_id;
