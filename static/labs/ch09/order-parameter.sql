\ir plan-context.sql

\if :{?plan_mode}
\else
  DO $parameter_error$
  BEGIN
      RAISE EXCEPTION 'plan_mode is required';
  END
  $parameter_error$;
\endif

SET plan_cache_mode TO :plan_mode;

PREPARE ch09_order_lookup(bigint, text) AS
SELECT order_no, placed_at, amount_minor
FROM shop_private.ch09_order_probe
WHERE customer_id = $1
  AND order_status = $2
ORDER BY placed_at DESC
LIMIT 20;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
EXECUTE ch09_order_lookup(42, 'placed');
