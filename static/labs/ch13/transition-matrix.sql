\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH state(value) AS (
    VALUES
        ('created'::text),
        ('paid'::text),
        ('packing'::text),
        ('shipped'::text),
        ('completed'::text),
        ('canceled'::text),
        ('expired'::text)
)
SELECT
    old_state.value AS old_status,
    new_state.value AS new_status,
    shop_ch13.allowed_transition(
        old_state.value,
        new_state.value
    ) AS allowed
FROM state AS old_state
CROSS JOIN state AS new_state
ORDER BY old_status, new_status;
