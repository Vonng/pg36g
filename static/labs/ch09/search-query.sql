\ir plan-context.sql

EXPLAIN (
    ANALYZE,
    BUFFERS,
    WAL,
    SETTINGS,
    SUMMARY,
    FORMAT JSON
)
SELECT product_id, product_name
FROM shop_private.ch09_search_probe
WHERE search_document @@
      pg_catalog.plainto_tsquery(
          'simple'::regconfig,
          'postgresql observability'
      )
ORDER BY product_id;
