\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    routine.oid::pg_catalog.regprocedure::text AS signature,
    routine.prokind,
    language.lanname AS language,
    routine.provolatile,
    routine.proisstrict,
    routine.proparallel,
    routine.prosecdef,
    coalesce(
        pg_catalog.array_to_string(routine.proconfig, ','),
        ''
    ) AS proconfig,
    pg_catalog.obj_description(
        routine.oid,
        'pg_proc'
    ) AS marker
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = routine.pronamespace
JOIN pg_catalog.pg_language AS language
  ON language.oid = routine.prolang
WHERE namespace.nspname = 'shop_ch13'
ORDER BY signature;
