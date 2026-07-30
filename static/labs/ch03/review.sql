\set ON_ERROR_STOP on
\ir context.sql

BEGIN;

DO $expected_constraints$
BEGIN
    BEGIN
        INSERT INTO shop.product (
            product_id,
            sku,
            product_name,
            current_unit_price,
            active,
            created_at
        )
        VALUES (
            199,
            'SKU-COFFEE',
            'Duplicate SKU',
            1,
            true,
            '2026-07-29 10:00:00+00'
        );
        RAISE EXCEPTION 'expected duplicate SKU to fail';
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'expected: duplicate SKU rejected';
    END;

    BEGIN
        INSERT INTO shop.sales_order_item (
            order_id,
            line_no,
            product_id,
            sku_snapshot,
            product_name_snapshot,
            unit_price,
            quantity
        )
        VALUES (
            1001,
            99,
            999999,
            'MISSING',
            'Missing Product',
            1,
            1
        );
        RAISE EXCEPTION 'expected missing product to fail';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'expected: missing product rejected';
    END;

    BEGIN
        INSERT INTO shop.sales_order_item (
            order_id,
            line_no,
            product_id,
            sku_snapshot,
            product_name_snapshot,
            unit_price,
            quantity
        )
        VALUES (
            1001,
            99,
            101,
            'SKU-COFFEE',
            'Coffee Beans',
            88,
            0
        );
        RAISE EXCEPTION 'expected zero quantity to fail';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'expected: zero quantity rejected';
    END;
END
$expected_constraints$;

INSERT INTO shop.product (
    product_id,
    sku,
    product_name,
    current_unit_price,
    active,
    created_at
)
VALUES (
    999,
    'SKU-OPEN-DECISION',
    'Scale Is Not Closed Yet',
    0.123456789,
    true,
    '2026-07-29 10:01:00+00'
);

INSERT INTO shop.sales_order (
    order_id,
    order_no,
    customer_id,
    request_key,
    request_fingerprint,
    buyer_email,
    order_status,
    placed_at,
    created_by_trace_id
)
VALUES (
    998,
    'ORD-OPEN-STATUS',
    1,
    'open-status-001',
    pg_catalog.md5('open-status'),
    'alice@example.test',
    'teleported',
    '2026-07-29 10:02:00+00',
    'trace-open-status'
);

INSERT INTO shop.sales_order (
    order_id,
    order_no,
    customer_id,
    request_key,
    request_fingerprint,
    buyer_email,
    order_status,
    placed_at,
    created_by_trace_id
)
VALUES (
    999,
    'ORD-OPEN-AGGREGATE',
    1,
    'open-aggregate-001',
    pg_catalog.md5('open-aggregate'),
    'alice@example.test',
    'paid',
    '2026-07-29 10:03:00+00',
    'trace-open-aggregate'
);

SELECT key || '=' || value AS review_result
FROM (
    SELECT 1, 'duplicate_business_key_rejected', 'true'
    UNION ALL
    SELECT 2, 'orphan_reference_rejected', 'true'
    UNION ALL
    SELECT 3, 'nonpositive_quantity_rejected', 'true'
    UNION ALL
    SELECT 4, 'arbitrary_money_scale_still_allowed',
           (scale(current_unit_price) = 9)::text
      FROM shop.product
     WHERE product_id = 999
    UNION ALL
    SELECT 5, 'arbitrary_order_status_still_allowed',
           (order_status = 'teleported')::text
      FROM shop.sales_order
     WHERE order_id = 998
    UNION ALL
    SELECT 6, 'paid_without_items_or_payment_still_possible',
           (
               NOT EXISTS (
                   SELECT 1
                   FROM shop.sales_order_item
                   WHERE order_id = 999
               )
               AND NOT EXISTS (
                   SELECT 1
                   FROM shop.payment
                   WHERE order_id = 999
               )
           )::text
) AS review(ord, key, value)
ORDER BY ord;

ROLLBACK;

\echo '[review] all deliberate changes rolled back'
