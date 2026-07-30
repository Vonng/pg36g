\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\if :{?reset_token}
\else
  \set reset_token ''
\endif

\if :{?reset_target}
\else
  \set reset_target ''
\endif

SELECT
    :'reset_token' = 'RESET_CH15_SEARCH_LAB' AS token_ok,
    :'reset_target' = 'pg36_shop/shop_ch15' AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3660',
          MESSAGE = 'reset refused: invalid ch15 action token';
  END
  $action_guard$;
\endif

\if :target_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3661',
          MESSAGE = 'reset refused: invalid ch15 target token';
  END
  $action_guard$;
\endif

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch15');
    expected_marker constant text :=
        'pg36 ch15 search quality lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = schema_oid
              )
          ) <> 'pg36_owner'
       OR pg_catalog.obj_description(
              schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3662',
            MESSAGE =
                'reset refused: shop_ch15 schema identity mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND (
              relation.relname <> ALL (ARRAY[
                  'fixture_meta',
                  'fixture_meta_pkey',
                  'product_search',
                  'product_search_pkey',
                  'product_search_sku_key',
                  'product_search_fts_idx',
                  'product_search_title_trgm_idx',
                  'product_search_embedding_hnsw_idx',
                  'product_search_filter_idx',
                  'eval_query',
                  'eval_query_pkey',
                  'relevance_judgment',
                  'relevance_judgment_pkey',
                  'relevance_judgment_product_idx',
                  'lexical_ranking',
                  'fuzzy_ranking',
                  'vector_exact_ranking',
                  'hybrid_rrf_ranking',
                  'all_ranking',
                  'quality_per_query',
                  'quality_summary'
              ])
              OR pg_catalog.obj_description(
                     relation.oid,
                     'pg_class'
                 ) IS DISTINCT FROM expected_marker
          )
    )
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_class AS relation
           WHERE relation.relnamespace = schema_oid
       ) <> 21 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3662',
            MESSAGE =
                'reset refused: shop_ch15 relation inventory drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
    )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opclass AS operator_class
           WHERE operator_class.opcnamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_opfamily AS operator_family
           WHERE operator_family.opfnamespace = schema_oid
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3662',
            MESSAGE =
                'reset refused: shop_ch15 catalog inventory drifted';
    END IF;
END
$collision_guard$;

DO $active_guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch15-%'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3663',
            MESSAGE = 'reset refused: ch15 workers are active';
    END IF;
END
$active_guard$;

DROP VIEW shop_ch15.quality_summary;
DROP VIEW shop_ch15.quality_per_query;
DROP VIEW shop_ch15.all_ranking;
DROP VIEW shop_ch15.hybrid_rrf_ranking;
DROP VIEW shop_ch15.vector_exact_ranking;
DROP VIEW shop_ch15.fuzzy_ranking;
DROP VIEW shop_ch15.lexical_ranking;
DROP TABLE shop_ch15.relevance_judgment;
DROP TABLE shop_ch15.eval_query;
DROP TABLE shop_ch15.product_search;
DROP TABLE shop_ch15.fixture_meta;
DROP SCHEMA shop_ch15;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_ch15';
SELECT 'remaining_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace('shop_ch15') IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'preserved_extensions=' ||
       (
           SELECT pg_catalog.string_agg(
                      extname || ':' || extversion,
                      ',' ORDER BY extname
                  )
           FROM pg_catalog.pg_extension
           WHERE extname IN ('pg_trgm', 'vector')
       );
