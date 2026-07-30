\set product_id random_zipfian(1, :product_count, 1.15)
SELECT
    p.product_id,
    p.category,
    p.price_cents,
    p.product_name,
    i.quantity
FROM shopbench.product AS p
JOIN shopbench.inventory AS i
  USING (product_id)
WHERE p.product_id = :product_id;
