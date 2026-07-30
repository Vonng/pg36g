\set ON_ERROR_STOP on
\pset pager off
\ir ../ch05/verify.sql
\ir context.sql

DO $verify$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch10 deterministic concurrency lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch10_inventory',
        'shop_private.ch10_doctor',
        'shop_private.ch10_deadlock_probe',
        'shop_private.ch10_job',
        'shop_private.ch10_payment_request',
        'shop_private.ch10_outbox'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NULL
           OR pg_catalog.obj_description(
                  relation_oid::oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'ch10 relation or marker verification failed: %',
                relation_name;
        END IF;
    END LOOP;

    IF (
        SELECT (available, version) <> (70, 2)
        FROM shop_private.ch10_inventory
        WHERE sku_id = 1001
    )
       OR (
        SELECT (available, version) <> (100, 0)
        FROM shop_private.ch10_inventory
        WHERE sku_id = 1002
    )
       OR (SELECT count(*) FROM shop_private.ch10_inventory) <> 2 THEN
        RAISE EXCEPTION 'ch10 inventory final state drifted';
    END IF;

    IF (
        SELECT count(*) FILTER (WHERE on_call) <> 1
            OR count(*) FILTER (WHERE NOT on_call) <> 1
        FROM shop_private.ch10_doctor
    ) THEN
        RAISE EXCEPTION 'ch10 serializable doctor invariant drifted';
    END IF;

    IF (
        SELECT count(*) <> 2
            OR min(value) <> 1
            OR max(value) <> 1
        FROM shop_private.ch10_deadlock_probe
    ) THEN
        RAISE EXCEPTION 'ch10 deadlock recovery state drifted';
    END IF;

    IF (
        SELECT count(*) <> 6
            OR count(*) FILTER (WHERE job_state = 'running') <> 6
            OR count(DISTINCT claimed_by) <> 2
        FROM shop_private.ch10_job
    )
       OR EXISTS (
           SELECT 1
           FROM shop_private.ch10_job
           GROUP BY claimed_by
           HAVING count(*) <> 3
       ) THEN
        RAISE EXCEPTION 'ch10 SKIP LOCKED claim state drifted';
    END IF;

    IF (SELECT count(*) FROM shop_private.ch10_payment_request) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM shop_private.ch10_payment_request
           WHERE idempotency_key = 'idem-order-1001'
             AND request_fingerprint =
                 'sha256:amount=3000;currency=CNY;merchant=demo'
             AND payment_id IN ('pay-demo-a', 'pay-demo-b')
             AND amount_minor = 3000
             AND payment_state = 'accepted'
             AND response ->> 'payment_id' = payment_id
             AND response ->> 'state' = 'accepted'
       )
       OR (SELECT count(*) FROM shop_private.ch10_outbox) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM shop_private.ch10_outbox
           WHERE event_key = 'payment-accepted:' || aggregate_key
             AND aggregate_key IN ('pay-demo-a', 'pay-demo-b')
             AND event_type = 'payment.accepted'
             AND payload ->> 'payment_id' = aggregate_key
             AND EXISTS (
                 SELECT 1
                 FROM shop_private.ch10_payment_request AS payment
                 WHERE payment.payment_id =
                       shop_private.ch10_outbox.aggregate_key
             )
       ) THEN
        RAISE EXCEPTION 'ch10 payment idempotency state drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch10-%'
    ) THEN
        RAISE EXCEPTION 'a ch10 worker is still connected';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_locks
        WHERE locktype = 'advisory'
          AND classid = 3610::oid
          AND objid BETWEEN 1001::oid AND 1016::oid
    ) THEN
        RAISE EXCEPTION 'a ch10 advisory barrier remains';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=ch10-concurrency-v1';
SELECT 'inventory=70/version:2';
SELECT 'doctors_on_call=1';
SELECT 'jobs_running=6/duplicate_claims:0';
SELECT 'payments=1/outbox=1';
SELECT 'active_lab_workers=0';
SELECT 'remaining_advisory_barriers=0';
