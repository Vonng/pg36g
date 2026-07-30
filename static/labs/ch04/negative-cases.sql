\set ON_ERROR_STOP on
\ir context.sql

BEGIN;
SET LOCAL TimeZone = 'UTC';

DO $negative_cases$
DECLARE
    actual_constraint text;
    generated_customer_id bigint;
    generated_payment_id bigint;
BEGIN
    BEGIN
        INSERT INTO shop.product (
            sku,
            product_name,
            active,
            currency_code,
            current_unit_price_minor
        )
        VALUES (
            'SKU-BAD-CURRENCY',
            'Bad Currency',
            true,
            'USD',
            100
        );
        RAISE EXCEPTION
            'negative case accepted unsupported currency';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint <> 'product_currency_supported' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        INSERT INTO shop.customer (
            customer_ref,
            email,
            display_name
        )
        VALUES (
            'CUST-UPPERCASE-EMAIL',
            'UpperCase@example.test',
            'Invalid Email Case'
        );
        RAISE EXCEPTION
            'negative case accepted noncanonical email';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint <> 'customer_email_canonical' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        UPDATE shop.sales_order
        SET order_status = 'draft',
            placed_at = NULL
        WHERE order_id = 1002;
        RAISE EXCEPTION
            'negative case accepted reverse order transition';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint
               <> 'sales_order_status_transition' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        UPDATE shop.sales_order
        SET order_status = 'paid'
        WHERE order_id = 1002;
        RAISE EXCEPTION
            'negative case accepted paid order without paid_at';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint
               <> 'sales_order_state_time_consistent' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        INSERT INTO shop.sales_order (
            order_no,
            customer_id,
            request_key,
            request_fingerprint,
            buyer_email,
            order_status,
            placed_at,
            created_by_trace_id,
            currency_code
        )
        VALUES (
            'ORD-20260729-0001',
            2,
            'duplicate-order-number',
            pg_catalog.md5('duplicate-order-number'),
            'bob@example.test',
            'placed',
            '2026-07-29 10:00:00+00',
            'trace-duplicate-order-number',
            'CNY'
        );
        RAISE EXCEPTION
            'negative case accepted duplicate order number';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint <> 'sales_order_order_no_key' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        INSERT INTO shop.sales_order_item (
            order_id,
            line_no,
            product_id,
            sku_snapshot,
            product_name_snapshot,
            quantity,
            currency_code,
            unit_price_minor,
            line_total_minor
        )
        VALUES (
            1002,
            2,
            103,
            'SKU-GIFT',
            'Gift Card',
            1,
            'CNY',
            10000,
            1
        );
        RAISE EXCEPTION
            'negative case accepted an explicit generated value';
    EXCEPTION
        WHEN SQLSTATE '428C9' THEN
            NULL;
    END;

    INSERT INTO shop.customer (
        customer_ref,
        email,
        display_name
    )
    VALUES (
        'CUST-IDENTITY-PROBE',
        'identity-probe@example.test',
        'Identity Probe'
    )
    RETURNING customer_id
    INTO generated_customer_id;

    IF generated_customer_id <= 2 THEN
        RAISE EXCEPTION
            'identity sequence did not advance past migrated keys';
    END IF;

    INSERT INTO shop.payment (
        order_id,
        provider,
        provider_payment_ref,
        idempotency_key,
        request_fingerprint,
        payment_status,
        occurred_at,
        trace_id,
        currency_code,
        amount_minor
    )
    VALUES (
        1002,
        'demo-pay',
        'pay-ref-1002-retry',
        'capture-1002-002',
        pg_catalog.md5('1002|10000|capture-retry'),
        'pending',
        '2026-07-29 09:07:00+00',
        'trace-payment-retry',
        'CNY',
        10000
    )
    RETURNING payment_id
    INTO generated_payment_id;

    UPDATE shop.payment
    SET payment_status = 'captured'
    WHERE payment_id = generated_payment_id;

    UPDATE shop.sales_order
    SET
        order_status = 'paid',
        paid_at = '2026-07-29 09:07:00+00'
    WHERE order_id = 1002;

    IF (
        SELECT captured_amount_minor
        FROM shop_api.order_summary
        WHERE order_id = 1002
    ) <> 10000 THEN
        RAISE EXCEPTION
            'positive transition path produced the wrong total';
    END IF;
END
$negative_cases$;

SET LOCAL ROLE pg36_app;

INSERT INTO shop.sales_order (
    order_no,
    customer_id,
    request_key,
    request_fingerprint,
    buyer_email,
    order_status,
    placed_at,
    created_by_trace_id,
    currency_code
)
VALUES (
    'ORD-20260729-APP-PROBE',
    2,
    'app-transition-probe',
    pg_catalog.md5('app-transition-probe'),
    'bob@example.test',
    'draft',
    NULL,
    'trace-app-transition-probe',
    'CNY'
)
RETURNING order_id AS app_order_id
\gset

UPDATE shop.sales_order
SET
    order_status = 'placed',
    placed_at = '2026-07-29 11:00:00+00'
WHERE order_id = :app_order_id;

INSERT INTO shop.payment (
    order_id,
    provider,
    provider_payment_ref,
    idempotency_key,
    request_fingerprint,
    payment_status,
    occurred_at,
    trace_id,
    currency_code,
    amount_minor
)
VALUES (
    :app_order_id,
    'demo-pay',
    'pay-ref-app-probe',
    'capture-app-probe',
    pg_catalog.md5('app-probe|500|capture'),
    'pending',
    '2026-07-29 11:01:00+00',
    'trace-payment-app-probe',
    'CNY',
    500
)
RETURNING payment_id AS app_payment_id
\gset

UPDATE shop.payment
SET payment_status = 'captured'
WHERE payment_id = :app_payment_id;

UPDATE shop.sales_order
SET
    order_status = 'paid',
    paid_at = '2026-07-29 11:01:00+00'
WHERE order_id = :app_order_id;

SELECT (
           SELECT order_status = 'paid'
           FROM shop.sales_order
           WHERE order_id = :app_order_id
       )
       AND (
           SELECT captured_amount_minor = 500
           FROM shop_api.order_summary
           WHERE order_id = :app_order_id
       ) AS app_transition_ok
\gset

\if :app_transition_ok
\else
  DO $app_transition_error$
  BEGIN
      RAISE EXCEPTION
          'pg36_app identity or transition path drifted';
  END
  $app_transition_error$;
\endif

SET LOCAL ROLE pg36_owner;

DO $time_cases$
DECLARE
    first_occurrence timestamptz;
    second_occurrence timestamptz;
BEGIN
    first_occurrence :=
        '2026-11-01 01:30:00-04'::timestamptz;
    second_occurrence :=
        '2026-11-01 01:30:00-05'::timestamptz;

    IF first_occurrence = second_occurrence
       OR second_occurrence - first_occurrence <> interval '1 hour'
    THEN
        RAISE EXCEPTION
            'explicit-offset DST instants were collapsed';
    END IF;

    IF (
        '2026-07-29 09:00:00+00'::timestamptz
        AT TIME ZONE 'Asia/Shanghai'
    ) <> timestamp '2026-07-29 17:00:00' THEN
        RAISE EXCEPTION 'business-zone projection drifted';
    END IF;
END
$time_cases$;

\echo 'negative_cases=all_rejected'
\echo 'positive_identity_and_transition=ok'
\echo 'pg36_app_security_definer_path=ok'
\echo 'dst_explicit_offset_case=ok'

ROLLBACK;
