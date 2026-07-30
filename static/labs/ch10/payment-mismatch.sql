\set ON_ERROR_STOP on
\ir context.sql

BEGIN ISOLATION LEVEL READ COMMITTED;

INSERT INTO shop_private.ch10_payment_request (
    idempotency_key,
    request_fingerprint,
    payment_id,
    amount_minor,
    payment_state,
    response,
    created_at
)
VALUES (
    'idem-order-1001',
    'sha256:amount=9999;currency=CNY;merchant=demo',
    'pay-demo-other',
    9999,
    'accepted',
    '{"payment_id":"pay-demo-other","state":"accepted"}'::jsonb,
    timestamptz '2025-01-01 00:08:00+00'
)
ON CONFLICT (idempotency_key) DO NOTHING;

DO $mismatch$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM shop_private.ch10_payment_request
        WHERE idempotency_key = 'idem-order-1001'
          AND request_fingerprint =
              'sha256:amount=9999;currency=CNY;merchant=demo'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'idempotency key reused with another payload';
    END IF;
END
$mismatch$;

COMMIT;
