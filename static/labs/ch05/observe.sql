\set ON_ERROR_STOP on
\ir context.sql

\pset format unaligned
\pset tuples_only on
\pset fieldsep '|'

BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY;

SELECT
    pg_catalog.pg_current_snapshot()::text AS snapshot_text
\gset

SELECT 'session_pid=' || pg_catalog.pg_backend_pid();
SELECT 'transaction_isolation=' ||
       pg_catalog.current_setting('transaction_isolation');
SELECT 'transaction_read_only=' ||
       pg_catalog.current_setting('transaction_read_only');
SELECT 'assigned_xid_before_write=' ||
       COALESCE(
           pg_catalog.pg_current_xact_id_if_assigned()::text,
           '<none>'
       );
SELECT 'snapshot=' || :'snapshot_text';
SELECT 'snapshot_xmin=' ||
       pg_catalog.pg_snapshot_xmin(
           :'snapshot_text'::pg_catalog.pg_snapshot
       )::text;
SELECT 'snapshot_xmax=' ||
       pg_catalog.pg_snapshot_xmax(
           :'snapshot_text'::pg_catalog.pg_snapshot
       )::text;
SELECT 'snapshot_in_progress_count=' ||
       pg_catalog.count(*)::text
FROM pg_catalog.pg_snapshot_xip(
         :'snapshot_text'::pg_catalog.pg_snapshot
     );

SELECT
    'backend_snapshot=' ||
    COALESCE(a.backend_xid::text, '<none>') || '|' ||
    COALESCE(a.backend_xmin::text, '<none>') || '|' ||
    COALESCE(a.wait_event_type, '<none>') || '|' ||
    COALESCE(a.wait_event, '<none>')
FROM pg_catalog.pg_stat_activity AS a
WHERE a.pid = pg_catalog.pg_backend_pid();

SELECT
    'tuple_diagnostic=' ||
    o.order_id::text || '|' ||
    o.xmin::text || '|' ||
    o.xmax::text || '|' ||
    o.ctid::text || '|' ||
    o.request_fingerprint
FROM shop.sales_order AS o
WHERE o.order_id = 1002;

SELECT 'wal_positions=' ||
       pg_catalog.pg_current_wal_insert_lsn()::text || '|' ||
       pg_catalog.pg_current_wal_lsn()::text || '|' ||
       pg_catalog.pg_current_wal_flush_lsn()::text;

COMMIT;
