\ir plan-context.sql

\if :{?plan_mode}
\else
  DO $parameter_plan_error$
  BEGIN
      RAISE EXCEPTION 'plan_mode is required';
  END
  $parameter_plan_error$;
\endif
\if :{?tenant_id}
\else
  DO $parameter_plan_error$
  BEGIN
      RAISE EXCEPTION 'tenant_id is required';
  END
  $parameter_plan_error$;
\endif

SET plan_cache_mode TO :plan_mode;

PREPARE ch07_tenant_probe(bigint) AS
SELECT probe_id, tenant_id, payload
FROM shop_private.ch07_plan_probe
WHERE tenant_id = $1;

EXPLAIN (
    ANALYZE,
    BUFFERS,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
EXECUTE ch07_tenant_probe(:tenant_id);
