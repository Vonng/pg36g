\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch14');
    expected_marker constant text :=
        'pg36 ch14 extension lifecycle lab; safe to rebuild';
    trigram_ids bigint[];
    vector_ids bigint[];
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
            'ch14 schema identity or marker drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_extension AS extension_catalog
        WHERE extension_catalog.extnamespace = schema_oid
    ) <> 2
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           WHERE extension_catalog.extname = 'pg_trgm'
             AND extension_catalog.extversion = '1.6'
             AND extension_catalog.extnamespace = schema_oid
             AND extension_catalog.extrelocatable
             AND pg_catalog.pg_get_userbyid(
                     extension_catalog.extowner
                 ) = 'pg36_owner'
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           JOIN pg_catalog.pg_roles AS role
             ON role.oid = extension_catalog.extowner
           WHERE extension_catalog.extname = 'vector'
             AND extension_catalog.extversion = '0.8.4'
             AND extension_catalog.extnamespace = schema_oid
             AND extension_catalog.extrelocatable
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION
            'ch14 extension version, owner, namespace, or marker drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extension_versions
        WHERE name = 'pg_trgm'
          AND version = '1.6'
          AND installed
          AND superuser
          AND trusted
          AND relocatable
    )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_available_extension_versions
           WHERE name = 'vector'
             AND version = '0.8.4'
             AND installed
             AND superuser
             AND NOT trusted
             AND relocatable
       ) THEN
        RAISE EXCEPTION
            'ch14 control-file privilege attributes drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_available_extensions
        WHERE name = 'citus'
    ) THEN
        RAISE EXCEPTION
            'ch14 formal local baseline expects Citus to be unavailable';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch14.extension_review
    ) <> 3
       OR (
           SELECT pg_catalog.string_agg(
                      extension_name || ':' || decision,
                      ',' ORDER BY extension_name
                  )
           FROM shop_ch14.extension_review
       ) <> 'citus:reject,pg_trgm:accept,vector:pilot' THEN
        RAISE EXCEPTION
            'ch14 ADR decisions drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch14.candidate_doc
    ) <> 5 THEN
        RAISE EXCEPTION
            'ch14 candidate document fixture drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_catalog.indexrelid
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_catalog.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        WHERE namespace.nspname = 'shop_ch14'
          AND index_relation.relname IN (
              'candidate_doc_title_trgm_idx',
              'candidate_doc_embedding_hnsw_idx'
          )
          AND index_catalog.indisvalid
          AND index_catalog.indisready
          AND index_catalog.indislive
    ) <> 2
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           JOIN pg_catalog.pg_am AS access_method
             ON access_method.oid = index_relation.relam
           JOIN pg_catalog.pg_opclass AS operator_class
             ON operator_class.oid = index_catalog.indclass[0]
           WHERE index_relation.oid =
                     pg_catalog.to_regclass(
                         'shop_ch14.candidate_doc_title_trgm_idx'
                     )
             AND access_method.amname = 'gin'
             AND operator_class.opcname = 'gin_trgm_ops'
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
           WHERE index_relation.oid =
                     pg_catalog.to_regclass(
                         'shop_ch14.candidate_doc_embedding_hnsw_idx'
                     )
             AND access_method.amname = 'hnsw'
             AND operator_class.opcname = 'vector_l2_ops'
       ) THEN
        RAISE EXCEPTION
            'ch14 index validity, access method, or opclass drifted';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
               'pg36_app',
               'shop_ch14',
               'USAGE'
           )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch14.extension_review',
                  'SELECT'
              )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch14.candidate_doc',
                  'SELECT'
              )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch14.candidate_doc',
              'INSERT'
          )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch14.candidate_doc',
              'UPDATE'
          )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch14.candidate_doc',
              'DELETE'
          ) THEN
        RAISE EXCEPTION
            'ch14 application privilege boundary drifted';
    END IF;

    SELECT pg_catalog.array_agg(
               doc_id
               ORDER BY score DESC, doc_id
           )
    INTO trigram_ids
    FROM (
        SELECT
            document.doc_id,
            shop_ch14.similarity(
                document.title,
                'PostgreSQL extenson'
            ) AS score
        FROM shop_ch14.candidate_doc AS document
        ORDER BY
            shop_ch14.similarity(
                document.title,
                'PostgreSQL extenson'
            ) DESC,
            document.doc_id
        LIMIT 3
    ) AS ranked;

    SELECT pg_catalog.array_agg(
               doc_id
               ORDER BY distance, doc_id
           )
    INTO vector_ids
    FROM (
        SELECT
            document.doc_id,
            document.embedding
                OPERATOR(shop_ch14.<->)
                '[1,0,0]'::shop_ch14.vector(3)
                AS distance
        FROM shop_ch14.candidate_doc AS document
        ORDER BY
            document.embedding
                OPERATOR(shop_ch14.<->)
                '[1,0,0]'::shop_ch14.vector(3),
            document.doc_id
        LIMIT 3
    ) AS ranked;

    IF trigram_ids <> ARRAY[1, 5, 2]::bigint[]
       OR vector_ids <> ARRAY[1, 2, 5]::bigint[] THEN
        RAISE EXCEPTION
            'ch14 query behavior drifted: trigram=% vector=%',
            trigram_ids,
            vector_ids;
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_extension AS extension_catalog
        JOIN pg_catalog.pg_depend AS dependency
          ON dependency.refclassid =
                 'pg_catalog.pg_extension'::pg_catalog.regclass
         AND dependency.refobjid = extension_catalog.oid
         AND dependency.deptype = 'e'
        WHERE extension_catalog.extname = 'pg_trgm'
    ) < 40
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_extension AS extension_catalog
           JOIN pg_catalog.pg_depend AS dependency
             ON dependency.refclassid =
                    'pg_catalog.pg_extension'::pg_catalog.regclass
            AND dependency.refobjid = extension_catalog.oid
            AND dependency.deptype = 'e'
           WHERE extension_catalog.extname = 'vector'
       ) < 200 THEN
        RAISE EXCEPTION
            'ch14 extension membership is unexpectedly incomplete';
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
            'ch14 non-extension relation inventory drifted';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'boundary=package+control+database-object';
SELECT 'decision=pg_trgm:accept/vector:pilot/citus:reject';
SELECT 'upgrade=pg_trgm:1.3->1.6';
SELECT 'failure=42501-owner+42501-superuser';
SELECT 'exit=portable-text-export';
