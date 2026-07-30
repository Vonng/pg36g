\set ON_ERROR_STOP on
\ir context.sql

BEGIN;

TRUNCATE TABLE
    shop.payment,
    shop.sales_order_item,
    shop.sales_order,
    shop.product,
    shop.customer;

INSERT INTO shop.customer (
    customer_id,
    customer_ref,
    email,
    display_name,
    created_at
)
VALUES
    (1, 'CUST-ALICE', 'alice@example.test', 'Alice',
     '2026-07-29 08:00:00+00'),
    (2, 'CUST-BOB', 'bob@example.test', 'Bob',
     '2026-07-29 08:05:00+00');

INSERT INTO shop.product (
    product_id,
    sku,
    product_name,
    current_unit_price,
    active,
    created_at
)
VALUES
    (101, 'SKU-COFFEE', 'Coffee Beans', 88.00, true,
     '2026-07-29 08:10:00+00'),
    (102, 'SKU-MUG', 'PostgreSQL Mug', 39.90, true,
     '2026-07-29 08:11:00+00'),
    (103, 'SKU-GIFT', 'Gift Card', 100.00, true,
     '2026-07-29 08:12:00+00');

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
VALUES
    (
        1001,
        'ORD-20260729-0001',
        1,
        'checkout-alice-001',
        pg_catalog.md5('alice|coffee:1|mug:2'),
        'alice@example.test',
        'paid',
        '2026-07-29 09:00:00+00',
        'trace-order-1001'
    ),
    (
        1002,
        'ORD-20260729-0002',
        2,
        'checkout-bob-001',
        pg_catalog.md5('bob|gift:1'),
        'bob@example.test',
        'placed',
        '2026-07-29 09:05:00+00',
        'trace-order-1002'
    );

INSERT INTO shop.sales_order_item (
    order_id,
    line_no,
    product_id,
    sku_snapshot,
    product_name_snapshot,
    unit_price,
    quantity
)
VALUES
    (1001, 1, 101, 'SKU-COFFEE', 'Coffee Beans', 88.00, 1),
    (1001, 2, 102, 'SKU-MUG', 'PostgreSQL Mug', 39.90, 2),
    (1002, 1, 103, 'SKU-GIFT', 'Gift Card', 100.00, 1);

INSERT INTO shop.payment (
    payment_id,
    order_id,
    provider,
    provider_payment_ref,
    idempotency_key,
    request_fingerprint,
    payment_status,
    amount,
    occurred_at,
    trace_id
)
VALUES
    (
        5001,
        1001,
        'demo-pay',
        'pay-ref-1001',
        'capture-1001-001',
        pg_catalog.md5('1001|167.80|capture'),
        'captured',
        167.80,
        '2026-07-29 09:01:00+00',
        'trace-payment-5001'
    ),
    (
        5002,
        1002,
        'demo-pay',
        'pay-ref-1002',
        'capture-1002-001',
        pg_catalog.md5('1002|100.00|capture'),
        'declined',
        100.00,
        '2026-07-29 09:06:00+00',
        'trace-payment-5002'
    );

COMMIT;

\echo '[seed] ch03 deterministic sample is ready'
