\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

RESET ROLE;
SET track_functions = 'all';
SET ROLE pg36_owner;

BEGIN;

DO $probe$
BEGIN
    PERFORM *
    FROM shop_ch13.order_snapshot(108);

    PERFORM *
    FROM shop_ch13.transition_order(
        108,
        0,
        'canceled',
        'stats-probe'
    );
END
$probe$;

SELECT
    function_stats.funcid::pg_catalog.regprocedure::text
        AS signature,
    function_stats.calls,
    function_stats.total_time >= 0 AS total_time_nonnegative,
    function_stats.self_time >= 0 AS self_time_nonnegative
FROM pg_catalog.pg_stat_xact_user_functions AS function_stats
JOIN pg_catalog.pg_proc AS routine
  ON routine.oid = function_stats.funcid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = routine.pronamespace
WHERE namespace.nspname = 'shop_ch13'
ORDER BY signature;

ROLLBACK;
