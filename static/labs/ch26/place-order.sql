\set customer_id random(1, :customer_count)
\set product_id random_zipfian(1, :product_count, 1.10)
\set quantity random(1, 3)

BEGIN;

SELECT price_cents
FROM shopbench.product
WHERE product_id = :product_id
\gset

UPDATE shopbench.inventory
SET
    quantity = quantity - :quantity,
    updated_at = clock_timestamp()
WHERE product_id = :product_id
  AND quantity >= :quantity;

WITH next_order AS (
    SELECT nextval(
        pg_get_serial_sequence(
            'shopbench.order_live',
            'order_id'
        )::regclass
    ) AS order_id
)
INSERT INTO shopbench.order_live (
    order_id,
    customer_id,
    product_id,
    quantity,
    amount_cents,
    status,
    placed_at,
    request_ref
)
SELECT
    next_order.order_id,
    :customer_id,
    :product_id,
    (:quantity)::smallint,
    (:price_cents)::integer * (:quantity)::integer,
    'accepted',
    clock_timestamp(),
    'ch26-' || (:client_id)::text
        || '-' || (:random_seed)::text
        || '-' || (:default_seed)::text
        || '-' || next_order.order_id::text
FROM next_order;

COMMIT;
