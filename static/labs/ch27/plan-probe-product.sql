\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off
SET plan_cache_mode = :'probe_mode';
SET statement_timeout = '5s';
SET default_transaction_read_only = on;
PREPARE ch27_product (bigint) AS
SELECT
    p.product_id,
    p.category,
    p.price_cents,
    p.product_name,
    i.quantity
FROM shopbench.product AS p
JOIN shopbench.inventory AS i
  USING (product_id)
WHERE p.product_id = $1;
EXPLAIN (FORMAT JSON, COSTS FALSE, SETTINGS TRUE)
EXECUTE ch27_product(:probe_value);
