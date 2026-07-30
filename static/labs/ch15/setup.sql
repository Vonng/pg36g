\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch15');
    expected_marker constant text :=
        'pg36 ch15 search quality lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = schema_oid
              )
          ) <> 'pg36_owner' THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch15 identity drifted';
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
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch15 relation inventory drifted';
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
            'refusing collision: shop_ch15 contains unknown catalog objects';
    END IF;
END
$collision_guard$;

DROP VIEW IF EXISTS shop_ch15.quality_summary;
DROP VIEW IF EXISTS shop_ch15.quality_per_query;
DROP VIEW IF EXISTS shop_ch15.all_ranking;
DROP VIEW IF EXISTS shop_ch15.hybrid_rrf_ranking;
DROP VIEW IF EXISTS shop_ch15.vector_exact_ranking;
DROP VIEW IF EXISTS shop_ch15.fuzzy_ranking;
DROP VIEW IF EXISTS shop_ch15.lexical_ranking;
DROP TABLE IF EXISTS shop_ch15.relevance_judgment;
DROP TABLE IF EXISTS shop_ch15.eval_query;
DROP TABLE IF EXISTS shop_ch15.product_search;
DROP TABLE IF EXISTS shop_ch15.fixture_meta;
DROP SCHEMA IF EXISTS shop_ch15;

SET ROLE pg36_owner;

CREATE SCHEMA shop_ch15 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch15 IS
    'pg36 ch15 search quality lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch15 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch15 TO pg36_app;

CREATE TABLE shop_ch15.fixture_meta (
    fixture_version text PRIMARY KEY,
    corpus_identity text NOT NULL,
    query_identity text NOT NULL,
    judgment_identity text NOT NULL,
    embedding_model text NOT NULL,
    embedding_method text NOT NULL,
    text_license text NOT NULL,
    vector_license text NOT NULL,
    frozen_at timestamptz NOT NULL
);

CREATE TABLE shop_ch15.product_search (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL,
    active boolean NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    embedding shop_ch14.vector(4) NOT NULL,
    embedding_model text NOT NULL,
    search_document tsvector
        GENERATED ALWAYS AS (
            pg_catalog.setweight(
                pg_catalog.to_tsvector(
                    'pg_catalog.english'::pg_catalog.regconfig,
                    coalesce(title, '')
                ),
                'A'
            )
            ||
            pg_catalog.setweight(
                pg_catalog.to_tsvector(
                    'pg_catalog.english'::pg_catalog.regconfig,
                    coalesce(description, '')
                ),
                'B'
            )
        ) STORED,
    CONSTRAINT product_search_category_domain
        CHECK (
            category IN (
                'audio',
                'kitchen',
                'outdoor',
                'books'
            )
        ),
    CONSTRAINT product_search_embedding_model
        CHECK (
            embedding_model =
            'pg36-handcrafted-topic-4d-v1'
        )
);

CREATE TABLE shop_ch15.eval_query (
    query_id text PRIMARY KEY,
    raw_query text NOT NULL,
    category_filter text,
    embedding shop_ch14.vector(4) NOT NULL,
    embedding_model text NOT NULL,
    intent text NOT NULL,
    CONSTRAINT eval_query_category_domain
        CHECK (
            category_filter IS NULL
            OR category_filter IN (
                'audio',
                'kitchen',
                'outdoor',
                'books'
            )
        ),
    CONSTRAINT eval_query_embedding_model
        CHECK (
            embedding_model =
            'pg36-handcrafted-topic-4d-v1'
        )
);

CREATE TABLE shop_ch15.relevance_judgment (
    query_id text NOT NULL
        REFERENCES shop_ch15.eval_query(query_id)
        ON DELETE RESTRICT,
    product_id bigint NOT NULL
        REFERENCES shop_ch15.product_search(product_id)
        ON DELETE RESTRICT,
    grade smallint NOT NULL,
    rationale text NOT NULL,
    PRIMARY KEY (query_id, product_id),
    CONSTRAINT relevance_grade_domain
        CHECK (grade BETWEEN 1 AND 3)
);

\ir fixture.sql

CREATE INDEX product_search_fts_idx
    ON shop_ch15.product_search
    USING gin (search_document);

CREATE INDEX product_search_title_trgm_idx
    ON shop_ch15.product_search
    USING gin (
        (pg_catalog.lower(title))
        shop_ch14.gin_trgm_ops
    );

CREATE INDEX product_search_embedding_hnsw_idx
    ON shop_ch15.product_search
    USING hnsw (
        embedding shop_ch14.vector_l2_ops
    )
    WITH (
        m = 8,
        ef_construction = 32
    );

CREATE INDEX product_search_filter_idx
    ON shop_ch15.product_search (
        category,
        product_id
    )
    WHERE active;

CREATE INDEX relevance_judgment_product_idx
    ON shop_ch15.relevance_judgment (
        product_id,
        query_id
    );

\ir ranking-views.sql

COMMENT ON TABLE shop_ch15.fixture_meta IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON TABLE shop_ch15.product_search IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON TABLE shop_ch15.eval_query IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON TABLE shop_ch15.relevance_judgment IS
    'pg36 ch15 search quality lab; safe to rebuild';

COMMENT ON INDEX shop_ch15.fixture_meta_pkey IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_pkey IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_sku_key IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_fts_idx IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_title_trgm_idx IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_embedding_hnsw_idx IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.product_search_filter_idx IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.eval_query_pkey IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.relevance_judgment_pkey IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON INDEX shop_ch15.relevance_judgment_product_idx IS
    'pg36 ch15 search quality lab; safe to rebuild';

COMMENT ON VIEW shop_ch15.lexical_ranking IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.fuzzy_ranking IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.vector_exact_ranking IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.hybrid_rrf_ranking IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.all_ranking IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.quality_per_query IS
    'pg36 ch15 search quality lab; safe to rebuild';
COMMENT ON VIEW shop_ch15.quality_summary IS
    'pg36 ch15 search quality lab; safe to rebuild';

GRANT SELECT ON
    shop_ch15.fixture_meta,
    shop_ch15.product_search,
    shop_ch15.eval_query,
    shop_ch15.relevance_judgment,
    shop_ch15.lexical_ranking,
    shop_ch15.fuzzy_ranking,
    shop_ch15.vector_exact_ranking,
    shop_ch15.hybrid_rrf_ranking,
    shop_ch15.all_ranking,
    shop_ch15.quality_per_query,
    shop_ch15.quality_summary
TO pg36_app;

RESET ROLE;

\pset format unaligned
\pset tuples_only on
SELECT 'status=fixture-ready';
SELECT 'products=' ||
       pg_catalog.count(*)::text
FROM shop_ch15.product_search;
SELECT 'queries=' ||
       pg_catalog.count(*)::text
FROM shop_ch15.eval_query;
SELECT 'judgments=' ||
       pg_catalog.count(*)::text
FROM shop_ch15.relevance_judgment;
