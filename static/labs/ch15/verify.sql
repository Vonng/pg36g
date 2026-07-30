\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch15');
    expected_marker constant text :=
        'pg36 ch15 search quality lab; safe to rebuild';
    actual_checksum text;
    actual_quality text;
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
        RAISE EXCEPTION
            'ch15 schema identity or marker drifted';
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
        RAISE EXCEPTION
            'ch15 relation inventory or marker drifted';
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
        RAISE EXCEPTION
            'ch15 contains unexpected catalog objects';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch15.fixture_meta
        WHERE fixture_version = 'ch15-search-v1'
          AND corpus_identity = 'frozen-corpus.csv'
          AND query_identity = 'frozen-queries.csv'
          AND judgment_identity = 'frozen-judgments.csv'
          AND embedding_model =
              'pg36-handcrafted-topic-4d-v1'
          AND embedding_method =
              'manually assigned deterministic topic coordinates'
          AND frozen_at =
              TIMESTAMPTZ '2026-07-29 00:00:00+00'
    ) <> 1 THEN
        RAISE EXCEPTION
            'ch15 fixture identity drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch15.product_search
    ) <> 17
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch15.product_search
           WHERE active
       ) <> 16
       OR (
           SELECT pg_catalog.array_agg(
                      product_id ORDER BY product_id
                  )
           FROM shop_ch15.product_search
           WHERE NOT active
       ) <> ARRAY[17]::bigint[]
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch15.eval_query
       ) <> 8
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch15.relevance_judgment
       ) <> 24
       OR EXISTS (
           SELECT 1
           FROM shop_ch15.eval_query AS query
           WHERE (
               SELECT pg_catalog.count(*)
               FROM shop_ch15.relevance_judgment AS judgment
               WHERE judgment.query_id = query.query_id
           ) <> 3
       ) THEN
        RAISE EXCEPTION
            'ch15 fixture cardinality drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop_ch15.product_search AS product
        WHERE product.search_document IS DISTINCT FROM
              (
                  pg_catalog.setweight(
                      pg_catalog.to_tsvector(
                          'pg_catalog.english'::pg_catalog.regconfig,
                          coalesce(product.title, '')
                      ),
                      'A'
                  )
                  ||
                  pg_catalog.setweight(
                      pg_catalog.to_tsvector(
                          'pg_catalog.english'::pg_catalog.regconfig,
                          coalesce(product.description, '')
                      ),
                      'B'
                  )
              )
    )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute AS attribute
           WHERE attribute.attrelid =
                     'shop_ch15.product_search'::pg_catalog.regclass
             AND attribute.attname = 'search_document'
             AND attribute.attgenerated = 's'
       ) THEN
        RAISE EXCEPTION
            'ch15 generated search document drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_catalog.indexrelid
        WHERE index_relation.relnamespace = schema_oid
          AND index_relation.relname IN (
              'product_search_fts_idx',
              'product_search_title_trgm_idx',
              'product_search_embedding_hnsw_idx',
              'product_search_filter_idx'
          )
          AND index_catalog.indisvalid
          AND index_catalog.indisready
          AND index_catalog.indislive
    ) <> 4
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           JOIN pg_catalog.pg_namespace AS operator_namespace
             ON operator_namespace.oid =
                    operator_class.opcnamespace
           WHERE index_relation.oid =
                     'shop_ch15.product_search_fts_idx'::pg_catalog.regclass
             AND access_method.amname = 'gin'
             AND operator_class.opcname = 'tsvector_ops'
             AND operator_namespace.nspname = 'pg_catalog'
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           JOIN pg_catalog.pg_namespace AS operator_namespace
             ON operator_namespace.oid =
                    operator_class.opcnamespace
           WHERE index_relation.oid =
                     'shop_ch15.product_search_title_trgm_idx'::pg_catalog.regclass
             AND access_method.amname = 'gin'
             AND operator_class.opcname = 'gin_trgm_ops'
             AND operator_namespace.nspname = 'shop_ch14'
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           JOIN pg_catalog.pg_namespace AS operator_namespace
             ON operator_namespace.oid =
                    operator_class.opcnamespace
           WHERE index_relation.oid =
                     'shop_ch15.product_search_embedding_hnsw_idx'::pg_catalog.regclass
             AND access_method.amname = 'hnsw'
             AND operator_class.opcname = 'vector_l2_ops'
             AND operator_namespace.nspname = 'shop_ch14'
       ) THEN
        RAISE EXCEPTION
            'ch15 index validity, access method, or opclass drifted';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
               'pg36_app',
               'shop_ch15',
               'USAGE'
           )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_class AS relation
           WHERE relation.relnamespace = schema_oid
             AND relation.relkind IN ('r', 'v')
             AND NOT pg_catalog.has_table_privilege(
                         'pg36_app',
                         relation.oid,
                         'SELECT'
                     )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_class AS relation
           WHERE relation.relnamespace = schema_oid
             AND relation.relkind = 'r'
             AND (
                 pg_catalog.has_table_privilege(
                     'pg36_app',
                     relation.oid,
                     'INSERT'
                 )
                 OR pg_catalog.has_table_privilege(
                        'pg36_app',
                        relation.oid,
                        'UPDATE'
                    )
                 OR pg_catalog.has_table_privilege(
                        'pg36_app',
                        relation.oid,
                        'DELETE'
                    )
             )
       ) THEN
        RAISE EXCEPTION
            'ch15 application privilege boundary drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop_ch15.all_ranking AS ranking
        WHERE ranking.product_id = 17
    )
       OR EXISTS (
           SELECT 1
           FROM shop_ch15.all_ranking AS ranking
           JOIN shop_ch15.eval_query AS query
             ON query.query_id = ranking.query_id
           JOIN shop_ch15.product_search AS product
             ON product.product_id = ranking.product_id
           WHERE query.category_filter IS NOT NULL
             AND product.category <> query.category_filter
       ) THEN
        RAISE EXCEPTION
            'ch15 active or category filter leaked';
    END IF;

    SELECT pg_catalog.string_agg(
               strategy || '|' ||
               query_count::text || '|' ||
               mean_precision_at_3::text || '|' ||
               mean_recall_at_3::text || '|' ||
               mrr_at_3::text || '|' ||
               mean_ndcg_at_3::text || '|' ||
               min_ndcg_at_3::text,
               E'\n' ORDER BY strategy
           )
    INTO actual_quality
    FROM shop_ch15.quality_summary;

    IF actual_quality IS DISTINCT FROM
       E'fuzzy|8|0.916667|0.916667|1.000000|0.942881|0.842828\n'
       'hybrid_rrf|8|1.000000|1.000000|1.000000|0.962929|0.759192\n'
       'lexical|8|0.291667|0.291667|0.750000|0.613043|0.000000\n'
       'vector_exact|8|1.000000|1.000000|1.000000|0.817314|0.631039'
    THEN
        RAISE EXCEPTION
            'ch15 quality baseline drifted: %',
            actual_quality;
    END IF;

    WITH business_rows AS (
        SELECT
            'product'::text AS kind,
            pg_catalog.lpad(
                product_id::text,
                4,
                '0'
            ) AS sort_key,
            pg_catalog.concat_ws(
                '|',
                product_id,
                sku,
                category,
                active,
                title,
                description,
                embedding::text,
                embedding_model
            ) AS payload
        FROM shop_ch15.product_search

        UNION ALL

        SELECT
            'query',
            query_id,
            pg_catalog.concat_ws(
                '|',
                query_id,
                raw_query,
                coalesce(category_filter, ''),
                embedding::text,
                embedding_model,
                intent
            )
        FROM shop_ch15.eval_query

        UNION ALL

        SELECT
            'judgment',
            query_id || '|' ||
                pg_catalog.lpad(product_id::text, 4, '0'),
            pg_catalog.concat_ws(
                '|',
                query_id,
                product_id,
                grade,
                rationale
            )
        FROM shop_ch15.relevance_judgment

        UNION ALL

        SELECT
            'ranking',
            strategy || '|' || query_id || '|' ||
                pg_catalog.lpad(result_rank::text, 4, '0'),
            pg_catalog.concat_ws(
                '|',
                strategy,
                query_id,
                product_id,
                result_rank,
                pg_catalog.round(score::numeric, 8),
                pg_catalog.array_to_string(sources, '+')
            )
        FROM shop_ch15.all_ranking
        WHERE result_rank <= 3

        UNION ALL

        SELECT
            'quality',
            strategy,
            pg_catalog.concat_ws(
                '|',
                strategy,
                query_count,
                mean_precision_at_3,
                mean_recall_at_3,
                mrr_at_3,
                mean_ndcg_at_3,
                min_ndcg_at_3
            )
        FROM shop_ch15.quality_summary
    )
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           )
    INTO actual_checksum
    FROM business_rows;

    IF actual_checksum <>
       'c637abf09edba88b7793f91201a57c34' THEN
        RAISE EXCEPTION
            'ch15 business checksum drifted: %',
            actual_checksum;
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=17-products/8-queries/24-judgments';
SELECT 'quality=exact-golden+precision+recall+mrr+ndcg';
SELECT 'ranking=fts+trigram+exact-vector+rrf';
SELECT 'ann=measured-separately-from-quality-golden';
SELECT 'security=pg36_app-read-only';
SELECT 'extensions=ch14-preserved';
SELECT 'release=1.3-proposal';
