\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

\if :{?probe_mode}
\else
  \warn 'plan-probe-counts.sql requires -v probe_mode=<auto|force_generic_plan>'
  \quit 64
\endif

SET plan_cache_mode = :'probe_mode';
SET statement_timeout = '5s';
SET default_transaction_read_only = on;

PREPARE ch27_product (bigint) AS
SELECT
    p.product_id,
    p.category,
    p.price_cents,
    p.product_name,
    i.quantity
FROM shopbench.product AS p
JOIN shopbench.inventory AS i
  USING (product_id)
WHERE p.product_id = $1;

PREPARE ch27_order (bigint) AS
SELECT
    order_id,
    product_id,
    quantity,
    amount_cents,
    status,
    placed_at
FROM shopbench.order_history
WHERE customer_id = $1
ORDER BY order_id DESC
LIMIT 5;

\o /dev/null
EXECUTE ch27_product(1);
EXECUTE ch27_product(8000);
EXECUTE ch27_product(16000);
EXECUTE ch27_product(2);
EXECUTE ch27_product(15999);
EXECUTE ch27_product(3);
EXECUTE ch27_product(15998);
EXECUTE ch27_product(4);
EXECUTE ch27_product(15997);
EXECUTE ch27_product(5);
EXECUTE ch27_order(1);
EXECUTE ch27_order(40000);
EXECUTE ch27_order(80000);
EXECUTE ch27_order(2);
EXECUTE ch27_order(79999);
EXECUTE ch27_order(3);
EXECUTE ch27_order(79998);
EXECUTE ch27_order(4);
EXECUTE ch27_order(79997);
EXECUTE ch27_order(5);
\o

SELECT jsonb_build_object(
    'requested_mode', :'probe_mode',
    'effective_mode', current_setting('plan_cache_mode'),
    'prepared', (
        SELECT jsonb_agg(
            jsonb_build_object(
                'name', name,
                'generic_plans', generic_plans,
                'custom_plans', custom_plans,
                'parameter_types', parameter_types
            )
            ORDER BY name
        )
        FROM pg_prepared_statements
        WHERE name LIKE 'ch27_%'
    )
);
