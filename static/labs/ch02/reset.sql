\set ON_ERROR_STOP on

\if :{?confirm_reset}
\else
  \set confirm_reset ''
\endif

SELECT :'confirm_reset' = 'RESET_CH02_FIXTURE' AS reset_confirmed
\gset

\if :reset_confirmed
  \echo '[reset] confirmation accepted'
\else
  \warn '[reset] refused: pass -v confirm_reset=RESET_CH02_FIXTURE'
  DO $reset_error$
  BEGIN
      RAISE EXCEPTION 'reset confirmation is required';
  END
  $reset_error$;
\endif

\ir context.sql
DROP TABLE IF EXISTS shop.ch02_fixture;
\echo '[reset] removed shop.ch02_fixture only'
