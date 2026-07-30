\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    before_filenode,
    fast_filenode,
    volatile_filenode,
    fast_has_missing,
    fast_missing_value,
    volatile_has_missing,
    fast_wal_bytes,
    volatile_wal_bytes,
    row_count
FROM shop_private.ch11_default_probe_result;
