\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch14');
    expected_marker constant text :=
        'pg36 ch14 extension lifecycle lab; safe to rebuild';
BEGIN
    IF schema_oid IS NOT NULL
       AND (
           pg_catalog.obj_description(
               schema_oid,
               'pg_namespace'
           ) IS DISTINCT FROM expected_marker
           OR pg_catalog.pg_get_userbyid(
                  (
                      SELECT namespace.nspowner
                      FROM pg_catalog.pg_namespace AS namespace
                      WHERE namespace.oid = schema_oid
                  )
              ) <> 'pg36_owner'
       ) THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch14 lacks the ch14 marker';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        WHERE extension_catalog.extname IN ('pg_trgm', 'vector')
          AND (
              schema_oid IS NULL
              OR extension_catalog.extnamespace <> schema_oid
              OR pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) IS DISTINCT FROM expected_marker
              OR (
                  extension_catalog.extname = 'pg_trgm'
                  AND (
                      extension_catalog.extversion
                          <> ALL (ARRAY['1.3', '1.6'])
                      OR pg_catalog.pg_get_userbyid(
                             extension_catalog.extowner
                         ) <> 'pg36_owner'
                  )
              )
              OR (
                  extension_catalog.extname = 'vector'
                  AND (
                      extension_catalog.extversion <> '0.8.4'
                      OR NOT EXISTS (
                          SELECT 1
                          FROM pg_catalog.pg_roles AS role
                          WHERE role.oid =
                                    extension_catalog.extowner
                            AND role.rolsuper
                      )
                  )
              )
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: pg_trgm or vector is not owned by this lab';
    END IF;

    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_extension AS extension_catalog
        WHERE extension_catalog.extnamespace = schema_oid
          AND extension_catalog.extname
              <> ALL (ARRAY['pg_trgm', 'vector'])
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains an unknown extension';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_class'::pg_catalog.regclass
                AND dependency.objid = relation.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
          AND (
              relation.relname <> ALL (ARRAY[
                  'extension_review',
                  'extension_review_pkey',
                  'candidate_doc',
                  'candidate_doc_pkey',
                  'candidate_doc_title_trgm_idx',
                  'candidate_doc_embedding_hnsw_idx'
              ])
              OR pg_catalog.obj_description(
                     relation.oid,
                     'pg_class'
                 ) IS DISTINCT FROM expected_marker
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains unknown relations';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_proc'::pg_catalog.regclass
                AND dependency.objid = routine.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains a non-extension routine';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_type AS type_catalog
        WHERE type_catalog.typnamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_type'::pg_catalog.regclass
                AND dependency.objid = type_catalog.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
          AND NOT (
              type_catalog.typrelid IN (
                  pg_catalog.to_regclass(
                      'shop_ch14.extension_review'
                  ),
                  pg_catalog.to_regclass(
                      'shop_ch14.candidate_doc'
                  )
              )
              OR EXISTS (
                  SELECT 1
                  FROM pg_catalog.pg_type AS element_type
                  WHERE element_type.oid = type_catalog.typelem
                    AND element_type.typrelid IN (
                        pg_catalog.to_regclass(
                            'shop_ch14.extension_review'
                        ),
                        pg_catalog.to_regclass(
                            'shop_ch14.candidate_doc'
                        )
                    )
              )
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains an unknown type';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_operator AS operator_catalog
        WHERE operator_catalog.oprnamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_operator'::pg_catalog.regclass
                AND dependency.objid = operator_catalog.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains a non-extension operator';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_opclass AS operator_class
        WHERE operator_class.opcnamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_opclass'::pg_catalog.regclass
                AND dependency.objid = operator_class.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains a non-extension opclass';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_opfamily AS operator_family
        WHERE operator_family.opfnamespace = schema_oid
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_depend AS dependency
              WHERE dependency.classid =
                        'pg_catalog.pg_opfamily'::pg_catalog.regclass
                AND dependency.objid = operator_family.oid
                AND dependency.refclassid =
                        'pg_catalog.pg_extension'::pg_catalog.regclass
                AND dependency.deptype = 'e'
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch14 contains a non-extension opfamily';
    END IF;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_ch14.candidate_doc;
DROP TABLE IF EXISTS shop_ch14.extension_review;
DROP EXTENSION IF EXISTS vector;
DROP EXTENSION IF EXISTS pg_trgm;
DROP SCHEMA IF EXISTS shop_ch14;

SET ROLE pg36_owner;

CREATE SCHEMA shop_ch14 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch14 IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch14 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch14 TO pg36_app;

CREATE EXTENSION pg_trgm
    WITH SCHEMA shop_ch14
    VERSION '1.3';
COMMENT ON EXTENSION pg_trgm IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';

CREATE TABLE shop_ch14.extension_review (
    candidate text PRIMARY KEY,
    extension_name text NOT NULL,
    package_alias text NOT NULL,
    decision text NOT NULL,
    problem text NOT NULL,
    success_criterion text NOT NULL,
    exit_path text NOT NULL,
    review_trigger text NOT NULL,
    reviewed_on date NOT NULL,
    CONSTRAINT extension_review_decision_domain
        CHECK (decision IN ('accept', 'pilot', 'reject'))
);

COMMENT ON TABLE shop_ch14.extension_review IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';
COMMENT ON INDEX shop_ch14.extension_review_pkey IS
    'pg36 ch14 extension lifecycle lab; safe to rebuild';

INSERT INTO shop_ch14.extension_review (
    candidate,
    extension_name,
    package_alias,
    decision,
    problem,
    success_criterion,
    exit_path,
    review_trigger,
    reviewed_on
)
VALUES
    (
        'bounded-fuzzy-search',
        'pg_trgm',
        'pgsql-main',
        'accept',
        'Typo-tolerant lookup over one bounded text field',
        'Top-three fixture IDs stay 1,5,2 and GIN is usable',
        'Drop the GIN index and replace similarity with exact or FTS lookup',
        'Query shape, language mix, or PostgreSQL major changes',
        DATE '2026-07-29'
    ),
    (
        'semantic-retrieval',
        'vector',
        'pgvector',
        'pilot',
        'Nearest-neighbor retrieval over controlled embeddings',
        'Quality corpus, latency budget, model identity, and recall pass',
        'Export embedding as text or array before dropping vector objects',
        'Embedding model, vector dimension, corpus, or extension version changes',
        DATE '2026-07-29'
    ),
    (
        'distributed-sharding',
        'citus',
        'citus',
        'reject',
        'No measured single-node bottleneck or shard key contract exists',
        'Reconsider only after a proven distributed capacity requirement',
        'Remain on upstream PostgreSQL with partitioning and scale-up options',
        'Capacity evidence exceeds the tested single-cluster envelope',
        DATE '2026-07-29'
    );

GRANT SELECT ON shop_ch14.extension_review TO pg36_app;

RESET ROLE;

\pset format unaligned
\pset tuples_only on
SELECT 'status=base-ready';
SELECT 'pg_trgm_owner=' ||
       pg_catalog.pg_get_userbyid(extension_catalog.extowner)
FROM pg_catalog.pg_extension AS extension_catalog
WHERE extension_catalog.extname = 'pg_trgm';
SELECT 'pg_trgm_version=' || extension_catalog.extversion
FROM pg_catalog.pg_extension AS extension_catalog
WHERE extension_catalog.extname = 'pg_trgm';
SELECT 'vector_installed=' ||
       CASE
           WHEN EXISTS (
               SELECT 1
               FROM pg_catalog.pg_extension
               WHERE extname = 'vector'
           )
               THEN 'true'
           ELSE 'false'
       END;
