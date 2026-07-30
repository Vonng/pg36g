\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT key, value
FROM (
    VALUES
        (
            1,
            'app_schema_usage',
            pg_catalog.has_schema_privilege(
                'pg36_app',
                'shop_ch13',
                'USAGE'
            )::text
        ),
        (
            2,
            'app_order_select',
            pg_catalog.has_table_privilege(
                'pg36_app',
                'shop_ch13.sales_order',
                'SELECT'
            )::text
        ),
        (
            3,
            'app_order_update',
            pg_catalog.has_table_privilege(
                'pg36_app',
                'shop_ch13.sales_order',
                'UPDATE'
            )::text
        ),
        (
            4,
            'app_payment_insert',
            pg_catalog.has_table_privilege(
                'pg36_app',
                'shop_ch13.payment',
                'INSERT'
            )::text
        ),
        (
            5,
            'app_snapshot_execute',
            pg_catalog.has_function_privilege(
                'pg36_app',
                'shop_ch13.order_snapshot(bigint)',
                'EXECUTE'
            )::text
        ),
        (
            6,
            'app_transition_execute',
            pg_catalog.has_function_privilege(
                'pg36_app',
                'shop_ch13.transition_order(bigint,bigint,text,text)',
                'EXECUTE'
            )::text
        ),
        (
            7,
            'app_capture_execute',
            pg_catalog.has_function_privilege(
                'pg36_app',
                'shop_ch13.capture_payment(bigint,bigint,text,bigint,text)',
                'EXECUTE'
            )::text
        ),
        (
            8,
            'app_guard_execute',
            pg_catalog.has_function_privilege(
                'pg36_app',
                'shop_ch13.guard_order_transition()',
                'EXECUTE'
            )::text
        ),
        (
            9,
            'app_procedure_execute',
            pg_catalog.has_function_privilege(
                'pg36_app',
                'shop_ch13.expire_stale_orders(timestamptz,integer,integer)',
                'EXECUTE'
            )::text
        ),
        (
            10,
            'public_transition_execute',
            (
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_catalog.aclexplode(
                        coalesce(
                            routine.proacl,
                            pg_catalog.acldefault(
                                'f',
                                routine.proowner
                            )
                        )
                    ) AS privilege
                    WHERE privilege.grantee = 0
                      AND privilege.privilege_type = 'EXECUTE'
                )
                FROM pg_catalog.pg_proc AS routine
                WHERE routine.oid =
                    'shop_ch13.transition_order(bigint,bigint,text,text)'
                    ::pg_catalog.regprocedure
            )::text
        )
) AS result(ord, key, value)
ORDER BY ord;
