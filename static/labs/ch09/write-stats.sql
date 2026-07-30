\set ON_ERROR_STOP on
\ir plan-context.sql

SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE WHEN n_tup_upd = 0 THEN NULL
         ELSE n_tup_hot_upd::numeric / n_tup_upd
    END AS hot_ratio
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'shop_private'
  AND relname IN (
      'ch09_write_base',
      'ch09_write_indexed'
  )
ORDER BY relname;
