\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker unknown
\endif
\if :{?doctor_id}
\else
  \set doctor_id 0
\endif
\if :{?gate}
\else
  \set gate 0
\endif
\if :{?serializable}
\else
  \set serializable false
\endif

\if :serializable
  BEGIN ISOLATION LEVEL SERIALIZABLE;
\else
  BEGIN ISOLATION LEVEL REPEATABLE READ;
\endif

SELECT count(*) AS observed_on_call
FROM shop_private.ch10_doctor
WHERE on_call
\gset

\if :serializable
  SELECT pg_catalog.format(
      'worker=%s/isolation=serializable/observed_on_call=%s',
      :'worker',
      :observed_on_call
  );
\else
  SELECT pg_catalog.format(
      'worker=%s/isolation=repeatable-read/observed_on_call=%s',
      :'worker',
      :observed_on_call
  );
\endif

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

UPDATE shop_private.ch10_doctor
SET on_call = false
WHERE doctor_id = :doctor_id;

COMMIT;
