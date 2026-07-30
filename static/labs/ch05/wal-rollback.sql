\set ON_ERROR_STOP on
\ir context.sql

\pset format unaligned
\pset tuples_only on

SELECT
    request_fingerprint AS baseline_fingerprint
FROM shop.sales_order
WHERE order_id = 1002
\gset

SELECT
    pg_catalog.pg_current_wal_insert_lsn() AS lsn_before
\gset

BEGIN;

UPDATE shop.sales_order
SET request_fingerprint =
        pg_catalog.md5('ch05-wal-rollback-' || order_id::text)
WHERE order_id = 1002;

SELECT
    pg_catalog.pg_current_xact_id_if_assigned()::text AS write_xid
\gset

ROLLBACK;

SELECT
    pg_catalog.pg_current_wal_insert_lsn() AS lsn_after
\gset

SELECT
    (
        pg_catalog.pg_wal_lsn_diff(
            :'lsn_after'::pg_catalog.pg_lsn,
            :'lsn_before'::pg_catalog.pg_lsn
        ) > 0
    ) AS wal_insert_advanced,
    (
        SELECT request_fingerprint = :'baseline_fingerprint'
        FROM shop.sales_order
        WHERE order_id = 1002
    ) AS state_restored,
    pg_catalog.pg_wal_lsn_diff(
        :'lsn_after'::pg_catalog.pg_lsn,
        :'lsn_before'::pg_catalog.pg_lsn
    )::text AS wal_bytes_observed
\gset

\if :wal_insert_advanced
\else
  DO $wal_error$
  BEGIN
      RAISE EXCEPTION 'rollback probe did not advance the WAL insert location';
  END
  $wal_error$;
\endif

\if :state_restored
\else
  DO $wal_error$
  BEGIN
      RAISE EXCEPTION 'rollback probe changed persistent order state';
  END
  $wal_error$;
\endif

SELECT 'write_xid=' || :'write_xid';
SELECT 'wal_lsn_before=' || :'lsn_before';
SELECT 'wal_lsn_after=' || :'lsn_after';
SELECT 'wal_bytes_observed=' || :'wal_bytes_observed';
SELECT 'wal_insert_advanced=' || :'wal_insert_advanced';
SELECT 'state_restored=' || :'state_restored';
SELECT 'synchronous_commit=' ||
       pg_catalog.current_setting('synchronous_commit');
SELECT 'fsync=' || pg_catalog.current_setting('fsync');
SELECT 'full_page_writes=' ||
       pg_catalog.current_setting('full_page_writes');
