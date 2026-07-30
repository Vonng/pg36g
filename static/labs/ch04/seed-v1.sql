\set ON_ERROR_STOP on
\ir context.sql

BEGIN;

DO $version_guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
    ) THEN
        RAISE EXCEPTION
            'seed-v1 requires the ch04 physical model v1';
    END IF;
END
$version_guard$;

TRUNCATE TABLE
    shop.payment,
    shop.sales_order_item,
    shop.sales_order,
    shop.product,
    shop.customer
RESTART IDENTITY;

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
    active,
    created_at,
    currency_code,
    current_unit_price_minor
)
VALUES
    (101, 'SKU-COFFEE', 'Coffee Beans', true,
     '2026-07-29 08:10:00+00', 'CNY', 8800),
    (102, 'SKU-MUG', 'PostgreSQL Mug', true,
     '2026-07-29 08:11:00+00', 'CNY', 3990),
    (103, 'SKU-GIFT', 'Gift Card', true,
     '2026-07-29 08:12:00+00', 'CNY', 10000);

INSERT INTO shop.sales_order (
    order_id,
    order_no,
    customer_id,
    request_key,
    request_fingerprint,
    buyer_email,
    order_status,
    placed_at,
    created_by_trace_id,
    currency_code,
    paid_at,
    cancelled_at
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
        'trace-order-1001',
        'CNY',
        '2026-07-29 09:01:00+00',
        NULL
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
        'trace-order-1002',
        'CNY',
        NULL,
        NULL
    );

INSERT INTO shop.sales_order_item (
    order_id,
    line_no,
    product_id,
    sku_snapshot,
    product_name_snapshot,
    quantity,
    currency_code,
    unit_price_minor
)
VALUES
    (1001, 1, 101, 'SKU-COFFEE', 'Coffee Beans',
     1, 'CNY', 8800),
    (1001, 2, 102, 'SKU-MUG', 'PostgreSQL Mug',
     2, 'CNY', 3990),
    (1002, 1, 103, 'SKU-GIFT', 'Gift Card',
     1, 'CNY', 10000);

INSERT INTO shop.payment (
    payment_id,
    order_id,
    provider,
    provider_payment_ref,
    idempotency_key,
    request_fingerprint,
    payment_status,
    occurred_at,
    trace_id,
    currency_code,
    amount_minor,
    failure_code
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
        '2026-07-29 09:01:00+00',
        'trace-payment-5001',
        'CNY',
        16780,
        NULL
    ),
    (
        5002,
        1002,
        'demo-pay',
        'pay-ref-1002',
        'capture-1002-001',
        pg_catalog.md5('1002|100.00|capture'),
        'declined',
        '2026-07-29 09:06:00+00',
        'trace-payment-5002',
        'CNY',
        10000,
        'DEMO_DECLINED'
    );

DO $identity_sequences$
DECLARE
    identity_spec record;
    sequence_name regclass;
    maximum_id bigint;
BEGIN
    FOR identity_spec IN
        SELECT *
        FROM (
            VALUES
                ('customer', 'customer_id'),
                ('product', 'product_id'),
                ('sales_order', 'order_id'),
                ('payment', 'payment_id')
        ) AS spec(table_name, column_name)
    LOOP
        sequence_name :=
            pg_catalog.pg_get_serial_sequence(
                pg_catalog.format(
                    '%I.%I',
                    'shop',
                    identity_spec.table_name
                ),
                identity_spec.column_name
            )::regclass;

        EXECUTE pg_catalog.format(
            'SELECT max(%I) FROM %I.%I',
            identity_spec.column_name,
            'shop',
            identity_spec.table_name
        )
        INTO maximum_id;

        PERFORM pg_catalog.setval(
            sequence_name,
            maximum_id,
            true
        );
    END LOOP;
END
$identity_sequences$;

COMMIT;

\echo '[seed] ch04 deterministic physical-model sample is ready'
