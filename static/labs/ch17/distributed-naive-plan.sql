\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

EXPLAIN (
    ANALYZE,
    VERBOSE,
    BUFFERS,
    COSTS OFF,
    SUMMARY OFF,
    TIMING OFF
)
SELECT *
FROM shop_ch17.distributed_tenant_month
ORDER BY tenant_id, month_start;
