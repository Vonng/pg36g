\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT key, value
FROM (
    SELECT
        1 AS ord,
        'orders'::text AS key,
        pg_catalog.count(*)::text AS value
    FROM shop_ch13.sales_order

    UNION ALL

    SELECT
        2,
        'status_created',
        pg_catalog.count(*)::text
    FROM shop_ch13.sales_order
    WHERE status = 'created'

    UNION ALL

    SELECT
        3,
        'status_paid',
        pg_catalog.count(*)::text
    FROM shop_ch13.sales_order
    WHERE status = 'paid'

    UNION ALL

    SELECT
        4,
        'status_canceled',
        pg_catalog.count(*)::text
    FROM shop_ch13.sales_order
    WHERE status = 'canceled'

    UNION ALL

    SELECT
        5,
        'status_expired',
        pg_catalog.count(*)::text
    FROM shop_ch13.sales_order
    WHERE status = 'expired'

    UNION ALL

    SELECT
        6,
        'payments',
        pg_catalog.count(*)::text
    FROM shop_ch13.payment

    UNION ALL

    SELECT
        7,
        'history_rows',
        pg_catalog.count(*)::text
    FROM shop_ch13.order_history

    UNION ALL

    SELECT
        8,
        'audit_statements',
        pg_catalog.count(*)::text
    FROM shop_ch13.statement_audit

    UNION ALL

    SELECT
        9,
        'audit_affected_sum',
        coalesce(
            pg_catalog.sum(affected_count),
            0
        )::text
    FROM shop_ch13.statement_audit

    UNION ALL

    SELECT
        10,
        'max_audit_batch',
        coalesce(
            pg_catalog.max(affected_count),
            0
        )::text
    FROM shop_ch13.statement_audit

    UNION ALL

    SELECT
        11,
        'captured_minor',
        coalesce(
            pg_catalog.sum(amount_minor)
                FILTER (WHERE status = 'captured'),
            0
        )::text
    FROM shop_ch13.payment

    UNION ALL

    SELECT
        12,
        'business_checksum',
        pg_catalog.md5(
            (
                SELECT pg_catalog.string_agg(
                    pg_catalog.format(
                        'O|%s|%s|%s',
                        order_id,
                        status,
                        version
                    ),
                    E'\n'
                    ORDER BY order_id
                )
                FROM shop_ch13.sales_order
            )
            || E'\n' ||
            (
                SELECT pg_catalog.string_agg(
                    pg_catalog.format(
                        'P|%s|%s|%s|%s',
                        order_id,
                        payment_ref,
                        amount_minor,
                        status
                    ),
                    E'\n'
                    ORDER BY order_id, payment_ref
                )
                FROM shop_ch13.payment
            )
            || E'\n' ||
            (
                SELECT pg_catalog.string_agg(
                    pg_catalog.format(
                        'H|%s|%s|%s|%s|%s|%s',
                        order_id,
                        old_status,
                        new_status,
                        old_version,
                        new_version,
                        actor
                    ),
                    E'\n'
                    ORDER BY order_id
                )
                FROM shop_ch13.order_history
            )
            || E'\n' ||
            (
                SELECT pg_catalog.string_agg(
                    pg_catalog.format(
                        'A|%s|%s|%s',
                        affected_count,
                        order_ids,
                        actor
                    ),
                    E'\n'
                    ORDER BY order_ids::text
                )
                FROM shop_ch13.statement_audit
            )
        )
) AS result(ord, key, value)
ORDER BY ord;
