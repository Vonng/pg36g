\set ON_ERROR_STOP on

\if :{?run_id}
\else
  \echo 'run_id is required'
  \quit 64
\endif

DELETE FROM pg36_ch21.recovery_probe
WHERE run_id = :'run_id';
