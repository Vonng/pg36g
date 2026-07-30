\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker unknown
\endif
\if :{?gate}
\else
  \set gate 0
\endif

BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT count(*) AS observed_before
FROM shop_private.ch10_payment_request
WHERE idempotency_key = 'idem-order-1001'
\gset

SELECT pg_catalog.format(
    'worker=%s/observed_before=%s',
    :'worker',
    :observed_before
);

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

WITH inserted AS (
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
        'sha256:amount=3000;currency=CNY;merchant=demo',
        'pay-demo-' || :'worker',
        3000,
        'accepted',
        pg_catalog.jsonb_build_object(
            'payment_id',
            'pay-demo-' || :'worker',
            'state',
            'accepted'
        ),
        timestamptz '2025-01-01 00:07:00+00'
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING 1
)
SELECT count(*) AS inserted
FROM inserted
\gset

\if :inserted
  INSERT INTO shop_private.ch10_outbox (
      event_key,
      aggregate_key,
      event_type,
      payload,
      created_at
  )
  SELECT
      'payment-accepted:' || payment_id,
      payment_id,
      'payment.accepted',
      response,
      timestamptz '2025-01-01 00:07:00+00'
  FROM shop_private.ch10_payment_request
  WHERE idempotency_key = 'idem-order-1001';
\endif

SELECT
    request_fingerprint =
        'sha256:amount=3000;currency=CNY;merchant=demo'
        AS same_payload,
    response::text AS response_text
FROM shop_private.ch10_payment_request
WHERE idempotency_key = 'idem-order-1001'
\gset

\if :same_payload
\else
  DO $mismatch$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P0001',
          MESSAGE = 'idempotency key reused with another payload';
  END
  $mismatch$;
\endif

SELECT pg_catalog.format(
    'worker=%s/inserted=%s/response=%s',
    :'worker',
    :inserted,
    :'response_text'
);

COMMIT;
