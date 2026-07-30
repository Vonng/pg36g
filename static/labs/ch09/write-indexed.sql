\ir plan-context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
UPDATE shop_private.ch09_write_indexed
SET volatile_counter = volatile_counter + 1;
