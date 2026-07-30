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
    :'reset_token' = 'RESET_CH14_EXTENSION_LAB' AS token_ok,
    :'reset_target' =
        'pg36_shop/shop_ch14/pg_trgm+vector' AS target_ok
\gset

\if :token_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3650',
          MESSAGE = 'reset refused: invalid ch14 action token';
  END
  $action_guard$;
\endif

\if :target_ok
\else
  DO $action_guard$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3651',
          MESSAGE = 'reset refused: invalid ch14 target token';
  END
  $action_guard$;
\endif

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch14');
    expected_marker constant text :=
        'pg36 ch14 extension lifecycle lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL
       OR pg_catalog.obj_description(
              schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3652',
            MESSAGE =
                'reset refused: shop_ch14 schema marker mismatch';
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
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3652',
            MESSAGE =
                'reset refused: ch14 extension inventory drifted';
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
        RAISE EXCEPTION USING
            ERRCODE = 'P3652',
            MESSAGE =
                'reset refused: shop_ch14 relation inventory drifted';
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
    )
       OR EXISTS (
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
       )
       OR EXISTS (
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
       )
       OR EXISTS (
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
       )
       OR EXISTS (
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
        RAISE EXCEPTION USING
            ERRCODE = 'P3652',
            MESSAGE =
                'reset refused: shop_ch14 catalog inventory drifted';
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
          AND application_name LIKE 'pg36-ch14-%'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3653',
            MESSAGE = 'reset refused: ch14 workers are active';
    END IF;
END
$active_guard$;

DROP TABLE shop_ch14.candidate_doc;
DROP TABLE shop_ch14.extension_review;
DROP EXTENSION vector;
DROP EXTENSION pg_trgm;
DROP SCHEMA shop_ch14;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'reset_target=pg36_shop/shop_ch14/pg_trgm+vector';
SELECT 'remaining_schema=' ||
       CASE
           WHEN pg_catalog.to_regnamespace('shop_ch14') IS NULL
               THEN '0'
           ELSE '1'
       END;
SELECT 'remaining_extensions=' ||
       (
           SELECT pg_catalog.count(*)::text
           FROM pg_catalog.pg_extension
           WHERE extname IN ('pg_trgm', 'vector')
       );
