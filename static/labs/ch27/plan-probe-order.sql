\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off
SET plan_cache_mode = :'probe_mode';
SET statement_timeout = '5s';
SET default_transaction_read_only = on;
PREPARE ch27_order (bigint) AS
SELECT
    order_id,
    product_id,
    quantity,
    amount_cents,
    status,
    placed_at
FROM shopbench.order_history
WHERE customer_id = $1
ORDER BY order_id DESC
LIMIT 5;
EXPLAIN (FORMAT JSON, COSTS FALSE, SETTINGS TRUE)
EXECUTE ch27_order(:probe_value);
