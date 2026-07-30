\ir plan-context.sql
SET plan_cache_mode TO force_generic_plan;

PREPARE ch07_partition_probe(date) AS
SELECT event_id
FROM shop_private.ch07_event_probe
WHERE occurred_on = $1;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
EXECUTE ch07_partition_probe(date '2025-05-15');
