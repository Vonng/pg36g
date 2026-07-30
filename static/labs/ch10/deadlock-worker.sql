\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker unknown
\endif
\if :{?first_row}
\else
  \set first_row 0
\endif
\if :{?second_row}
\else
  \set second_row 0
\endif
\if :{?gate}
\else
  \set gate 0
\endif

BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE shop_private.ch10_deadlock_probe
SET value = value + 1
WHERE row_id = :first_row;

SELECT pg_catalog.format(
    'worker=%s/first_locked=%s',
    :'worker',
    :first_row
);

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);

UPDATE shop_private.ch10_deadlock_probe
SET value = value + 1
WHERE row_id = :second_row;

COMMIT;
