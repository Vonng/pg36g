\set customer_id random_zipfian(1, :customer_count, 1.08)
SELECT
    order_id,
    product_id,
    quantity,
    amount_cents,
    status,
    placed_at
FROM shopbench.order_history
WHERE customer_id = :customer_id
ORDER BY order_id DESC
LIMIT 5;
