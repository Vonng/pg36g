\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    invalid_paid_orders integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM shop_ch13.schema_version
        WHERE version = 1
          AND description = 'ch13 routine guard lab'
    ) THEN
        RAISE EXCEPTION 'ch13 schema version marker is missing';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.sales_order
    ) <> 13 THEN
        RAISE EXCEPTION 'ch13 order count drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.sales_order
        WHERE status = 'created'
    ) <> 3 OR (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.sales_order
        WHERE status = 'paid'
    ) <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.sales_order
        WHERE status = 'canceled'
    ) <> 4 OR (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.sales_order
        WHERE status = 'expired'
    ) <> 5 THEN
        RAISE EXCEPTION 'ch13 final status distribution drifted';
    END IF;

    SELECT pg_catalog.count(*)
    INTO invalid_paid_orders
    FROM shop_ch13.sales_order AS target
    LEFT JOIN LATERAL (
        SELECT coalesce(
                   pg_catalog.sum(payment.amount_minor)
                       FILTER (
                           WHERE payment.status = 'captured'
                       ),
                   0
               ) AS captured_minor
        FROM shop_ch13.payment AS payment
        WHERE payment.order_id = target.order_id
    ) AS payment_total ON true
    WHERE (
        target.status = 'paid'
        AND payment_total.captured_minor
            IS DISTINCT FROM target.total_minor
    ) OR (
        target.status <> 'paid'
        AND payment_total.captured_minor <> 0
    );

    IF invalid_paid_orders <> 0 THEN
        RAISE EXCEPTION 'paid-order invariant is violated';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.payment
    ) <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.order_history
    ) <> 10 OR (
        SELECT pg_catalog.count(*)
        FROM shop_ch13.statement_audit
    ) <> 6 OR (
        SELECT pg_catalog.sum(affected_count)
        FROM shop_ch13.statement_audit
    ) <> 10 THEN
        RAISE EXCEPTION 'ch13 audit relationship drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM shop_ch13.statement_audit
        WHERE affected_count = 3
          AND order_ids = ARRAY[
              105::bigint,
              106::bigint,
              107::bigint
          ]
          AND actor = 'bulk-lab'
    ) THEN
        RAISE EXCEPTION 'statement-level bulk audit evidence is missing';
    END IF;

    IF (
        SELECT pg_catalog.array_agg(
                   affected_count
                   ORDER BY order_ids[1]
               )
        FROM shop_ch13.statement_audit
        WHERE actor = 'ch13-maintenance'
    ) IS DISTINCT FROM ARRAY[2, 2, 1] THEN
        RAISE EXCEPTION 'procedure batch boundaries drifted';
    END IF;

    IF pg_catalog.has_table_privilege(
           'pg36_app',
           'shop_ch13.sales_order',
           'UPDATE'
       ) OR NOT pg_catalog.has_function_privilege(
           'pg36_app',
           'shop_ch13.transition_order(bigint,bigint,text,text)',
           'EXECUTE'
       ) OR pg_catalog.has_function_privilege(
           'pg36_app',
           'shop_ch13.guard_order_transition()',
           'EXECUTE'
       ) THEN
        RAISE EXCEPTION 'ch13 least-privilege contract drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch13-%'
    ) THEN
        RAISE EXCEPTION 'a ch13 worker is still active';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=ch13-routine-guard-v1';
SELECT 'boundary=check+before-trigger+deferred-constraint+command-function';
SELECT 'failures=42501/P3613/P3614/P3616/P3618/2D000';
SELECT 'procedure_batches=2/2/1';
SELECT 'audit=10-rows/6-statements';
