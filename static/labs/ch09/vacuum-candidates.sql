\set ON_ERROR_STOP on
\ir context.sql

VACUUM (FREEZE, ANALYZE) shop_private.ch09_order_probe;
VACUUM (FREEZE, ANALYZE) shop_private.ch09_inventory_probe;
VACUUM (ANALYZE) shop_private.ch09_search_probe;
VACUUM (ANALYZE) shop_private.ch09_event_probe;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'candidate_tables_vacuumed=4';
