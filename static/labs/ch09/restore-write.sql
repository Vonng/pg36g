\set ON_ERROR_STOP on
\ir context.sql

VACUUM (ANALYZE) shop_private.ch09_write_base;
VACUUM (ANALYZE) shop_private.ch09_write_indexed;

ALTER TABLE shop_private.ch09_write_base
    SET (autovacuum_enabled = true);
ALTER TABLE shop_private.ch09_write_indexed
    SET (autovacuum_enabled = true);

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'write_tables_restored=true';
