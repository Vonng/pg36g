\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

CREATE EXTENSION vector
    WITH SCHEMA shop_ch14
    VERSION '0.8.4';
COMMENT ON EXTENSION vector IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';

SET ROLE pg36_owner;

CREATE TABLE shop_ch14.candidate_doc (
    doc_id bigint PRIMARY KEY,
    title text NOT NULL,
    embedding shop_ch14.vector(3) NOT NULL
);

COMMENT ON TABLE shop_ch14.candidate_doc IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';
COMMENT ON INDEX shop_ch14.candidate_doc_pkey IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';

INSERT INTO shop_ch14.candidate_doc (
    doc_id,
    title,
    embedding
)
VALUES
    (1, 'PostgreSQL extension guide', '[1,0,0]'),
    (2, 'Pigsty extension operations', '[0.9,0.1,0]'),
    (3, 'PostGIS spatial analysis', '[0,1,0]'),
    (4, 'Citus distributed planning', '[0,0,1]'),
    (5, 'Native PostgreSQL indexing', '[0.8,0.2,0]');

CREATE INDEX candidate_doc_title_trgm_idx
    ON shop_ch14.candidate_doc
    USING gin (title shop_ch14.gin_trgm_ops);

CREATE INDEX candidate_doc_embedding_hnsw_idx
    ON shop_ch14.candidate_doc
    USING hnsw (
        embedding shop_ch14.vector_l2_ops
    )
    WITH (
        m = 8,
        ef_construction = 32
    );

COMMENT ON INDEX shop_ch14.candidate_doc_title_trgm_idx IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';
COMMENT ON INDEX shop_ch14.candidate_doc_embedding_hnsw_idx IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';

GRANT SELECT ON shop_ch14.candidate_doc TO pg36_app;

RESET ROLE;

\pset format unaligned
\pset tuples_only on
SELECT 'status=fixture-ready';
SELECT 'vector_owner=' ||
       pg_catalog.pg_get_userbyid(extension_catalog.extowner)
FROM pg_catalog.pg_extension AS extension_catalog
WHERE extension_catalog.extname = 'vector';
SELECT 'documents=' ||
       pg_catalog.count(*)::text
FROM shop_ch14.candidate_doc;
