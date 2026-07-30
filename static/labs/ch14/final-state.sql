\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

WITH document_lines AS (
    SELECT
        'doc'::text AS line_kind,
        pg_catalog.lpad(
            document.doc_id::text,
            20,
            '0'
        ) AS line_key,
        pg_catalog.concat_ws(
            '|',
            document.doc_id,
            document.title,
            document.embedding::text
        ) AS line_value
    FROM shop_ch14.candidate_doc AS document
),
review_lines AS (
    SELECT
        'review'::text AS line_kind,
        review.candidate AS line_key,
        pg_catalog.concat_ws(
            '|',
            review.candidate,
            review.extension_name,
            review.package_alias,
            review.decision,
            review.problem,
            review.success_criterion,
            review.exit_path,
            review.review_trigger,
            review.reviewed_on::text
        ) AS line_value
    FROM shop_ch14.extension_review AS review
),
extension_lines AS (
    SELECT
        'extension'::text AS line_kind,
        extension_catalog.extname AS line_key,
        pg_catalog.concat_ws(
            '|',
            extension_catalog.extname,
            extension_catalog.extversion,
            namespace.nspname,
            extension_catalog.extrelocatable::text
        ) AS line_value
    FROM pg_catalog.pg_extension AS extension_catalog
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = extension_catalog.extnamespace
    WHERE extension_catalog.extname IN ('pg_trgm', 'vector')
),
business_checksum AS (
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   line_value,
                   E'\n'
                   ORDER BY line_kind, line_key
               )
           ) AS checksum
    FROM (
        SELECT * FROM document_lines
        UNION ALL
        SELECT * FROM review_lines
        UNION ALL
        SELECT * FROM extension_lines
    ) AS all_lines
),
trigram_result AS (
    SELECT document.doc_id
    FROM shop_ch14.candidate_doc AS document
    ORDER BY
        shop_ch14.similarity(
            document.title,
            'PostgreSQL extenson'
        ) DESC,
        document.doc_id
    LIMIT 3
),
vector_result AS (
    SELECT document.doc_id
    FROM shop_ch14.candidate_doc AS document
    ORDER BY
        document.embedding
            OPERATOR(shop_ch14.<->)
            '[1,0,0]'::shop_ch14.vector(3),
        document.doc_id
    LIMIT 3
),
fact AS (
    SELECT
        'release'::text AS key,
        '1.2-proposal'::text AS value
    UNION ALL
    SELECT
        'review_rows',
        pg_catalog.count(*)::text
    FROM shop_ch14.extension_review
    UNION ALL
    SELECT
        'document_rows',
        pg_catalog.count(*)::text
    FROM shop_ch14.candidate_doc
    UNION ALL
    SELECT
        'pg_trgm_version',
        extversion
    FROM pg_catalog.pg_extension
    WHERE extname = 'pg_trgm'
    UNION ALL
    SELECT
        'vector_version',
        extversion
    FROM pg_catalog.pg_extension
    WHERE extname = 'vector'
    UNION ALL
    SELECT
        'pg_trgm_members',
        pg_catalog.count(*)::text
    FROM pg_catalog.pg_extension AS extension_catalog
    JOIN pg_catalog.pg_depend AS dependency
      ON dependency.refclassid =
             'pg_catalog.pg_extension'::pg_catalog.regclass
     AND dependency.refobjid = extension_catalog.oid
     AND dependency.deptype = 'e'
    WHERE extension_catalog.extname = 'pg_trgm'
    UNION ALL
    SELECT
        'vector_members',
        pg_catalog.count(*)::text
    FROM pg_catalog.pg_extension AS extension_catalog
    JOIN pg_catalog.pg_depend AS dependency
      ON dependency.refclassid =
             'pg_catalog.pg_extension'::pg_catalog.regclass
     AND dependency.refobjid = extension_catalog.oid
     AND dependency.deptype = 'e'
    WHERE extension_catalog.extname = 'vector'
    UNION ALL
    SELECT
        'trigram_top_ids',
        (
            SELECT pg_catalog.string_agg(
                       doc_id::text,
                       ',' ORDER BY score DESC, doc_id
                   )
            FROM (
                SELECT
                    doc_id,
                    shop_ch14.similarity(
                        document.title,
                        'PostgreSQL extenson'
                    ) AS score
                FROM trigram_result
                JOIN shop_ch14.candidate_doc AS document
                  USING (doc_id)
            ) AS ranked
        )
    UNION ALL
    SELECT
        'vector_top_ids',
        (
            SELECT pg_catalog.string_agg(
                       doc_id::text,
                       ',' ORDER BY distance, doc_id
                   )
            FROM (
                SELECT
                    doc_id,
                    document.embedding
                        OPERATOR(shop_ch14.<->)
                        '[1,0,0]'::shop_ch14.vector(3)
                        AS distance
                FROM vector_result
                JOIN shop_ch14.candidate_doc AS document
                  USING (doc_id)
            ) AS ranked
        )
    UNION ALL
    SELECT
        'business_checksum',
        checksum
    FROM business_checksum
)
SELECT key, value
FROM fact
ORDER BY key;
