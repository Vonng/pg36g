CREATE VIEW shop_ch15.lexical_ranking AS
WITH scored AS (
    SELECT
        query.query_id,
        product.product_id,
        pg_catalog.ts_rank_cd(
            product.search_document,
            pg_catalog.websearch_to_tsquery(
                'pg_catalog.english'::pg_catalog.regconfig,
                query.raw_query
            ),
            32
        )::double precision AS score
    FROM shop_ch15.eval_query AS query
    JOIN shop_ch15.product_search AS product
      ON product.active
     AND (
         query.category_filter IS NULL
         OR product.category = query.category_filter
     )
    WHERE product.search_document
          @@
          pg_catalog.websearch_to_tsquery(
              'pg_catalog.english'::pg_catalog.regconfig,
              query.raw_query
          )
)
SELECT
    query_id,
    product_id,
    pg_catalog.row_number() OVER (
        PARTITION BY query_id
        ORDER BY score DESC, product_id
    ) AS result_rank,
    score
FROM scored;

CREATE VIEW shop_ch15.fuzzy_ranking AS
WITH scored AS (
    SELECT
        query.query_id,
        product.product_id,
        greatest(
            shop_ch14.similarity(
                pg_catalog.lower(product.title),
                pg_catalog.lower(query.raw_query)
            ),
            shop_ch14.word_similarity(
                pg_catalog.lower(query.raw_query),
                pg_catalog.lower(product.title)
            )
        )::double precision AS score
    FROM shop_ch15.eval_query AS query
    JOIN shop_ch15.product_search AS product
      ON product.active
     AND (
         query.category_filter IS NULL
         OR product.category = query.category_filter
     )
)
SELECT
    query_id,
    product_id,
    pg_catalog.row_number() OVER (
        PARTITION BY query_id
        ORDER BY score DESC, product_id
    ) AS result_rank,
    score
FROM scored;

CREATE VIEW shop_ch15.vector_exact_ranking AS
WITH scored AS (
    SELECT
        query.query_id,
        product.product_id,
        (
            product.embedding
            OPERATOR(shop_ch14.<->)
            query.embedding
        )::double precision AS distance
    FROM shop_ch15.eval_query AS query
    JOIN shop_ch15.product_search AS product
      ON product.active
     AND (
         query.category_filter IS NULL
         OR product.category = query.category_filter
     )
)
SELECT
    query_id,
    product_id,
    pg_catalog.row_number() OVER (
        PARTITION BY query_id
        ORDER BY distance, product_id
    ) AS result_rank,
    -distance AS score,
    distance
FROM scored;

CREATE VIEW shop_ch15.hybrid_rrf_ranking AS
WITH source_rank AS (
    SELECT
        query_id,
        product_id,
        'lexical'::text AS source_name,
        result_rank,
        1.0::double precision AS source_weight
    FROM shop_ch15.lexical_ranking
    WHERE result_rank <= 4

    UNION ALL

    SELECT
        query_id,
        product_id,
        'fuzzy',
        result_rank,
        1.0::double precision
    FROM shop_ch15.fuzzy_ranking
    WHERE result_rank <= 4

    UNION ALL

    SELECT
        query_id,
        product_id,
        'vector_exact',
        result_rank,
        1.0::double precision
    FROM shop_ch15.vector_exact_ranking
    WHERE result_rank <= 4
),
scored AS (
    SELECT
        query_id,
        product_id,
        pg_catalog.sum(
            source_weight / (60.0 + result_rank)
        )::double precision AS score,
        pg_catalog.array_agg(
            source_name
            ORDER BY source_name
        ) AS sources
    FROM source_rank
    GROUP BY query_id, product_id
)
SELECT
    query_id,
    product_id,
    pg_catalog.row_number() OVER (
        PARTITION BY query_id
        ORDER BY score DESC, product_id
    ) AS result_rank,
    score,
    sources
FROM scored;

CREATE VIEW shop_ch15.all_ranking AS
SELECT
    'lexical'::text AS strategy,
    query_id,
    product_id,
    result_rank,
    score,
    ARRAY['lexical']::text[] AS sources
FROM shop_ch15.lexical_ranking

UNION ALL

SELECT
    'fuzzy',
    query_id,
    product_id,
    result_rank,
    score,
    ARRAY['fuzzy']::text[]
FROM shop_ch15.fuzzy_ranking

UNION ALL

SELECT
    'vector_exact',
    query_id,
    product_id,
    result_rank,
    score,
    ARRAY['vector_exact']::text[]
FROM shop_ch15.vector_exact_ranking

UNION ALL

SELECT
    'hybrid_rrf',
    query_id,
    product_id,
    result_rank,
    score,
    sources
FROM shop_ch15.hybrid_rrf_ranking;

CREATE VIEW shop_ch15.quality_per_query AS
WITH strategy (strategy) AS (
    VALUES
        ('lexical'::text),
        ('fuzzy'::text),
        ('vector_exact'::text),
        ('hybrid_rrf'::text)
),
evaluation_grid AS (
    SELECT
        strategy.strategy,
        query.query_id
    FROM strategy
    CROSS JOIN shop_ch15.eval_query AS query
),
retrieved AS (
    SELECT
        ranking.strategy,
        ranking.query_id,
        ranking.product_id,
        ranking.result_rank
    FROM shop_ch15.all_ranking AS ranking
    WHERE ranking.result_rank <= 3
),
relevant_total AS (
    SELECT
        judgment.query_id,
        pg_catalog.count(*) AS relevant_count
    FROM shop_ch15.relevance_judgment AS judgment
    WHERE judgment.grade > 0
    GROUP BY judgment.query_id
),
ideal_ranked AS (
    SELECT
        judgment.query_id,
        judgment.grade,
        pg_catalog.row_number() OVER (
            PARTITION BY judgment.query_id
            ORDER BY
                judgment.grade DESC,
                judgment.product_id
        ) AS ideal_rank
    FROM shop_ch15.relevance_judgment AS judgment
    WHERE judgment.grade > 0
),
ideal AS (
    SELECT
        query_id,
        pg_catalog.sum(
            (
                pg_catalog.power(
                    2::numeric,
                    grade::numeric
                ) - 1
            )
            /
            pg_catalog.log(
                2::numeric,
                (ideal_rank + 1)::numeric
            )
        ) AS ideal_dcg
    FROM ideal_ranked
    WHERE ideal_rank <= 3
    GROUP BY query_id
),
observed AS (
    SELECT
        grid.strategy,
        grid.query_id,
        pg_catalog.count(
            retrieved.product_id
        ) AS result_count,
        pg_catalog.count(
            judgment.product_id
        ) FILTER (
            WHERE judgment.grade > 0
        ) AS relevant_retrieved,
        pg_catalog.min(
            retrieved.result_rank
        ) FILTER (
            WHERE judgment.grade > 0
        ) AS first_relevant_rank,
        coalesce(
            pg_catalog.sum(
                (
                    pg_catalog.power(
                        2::numeric,
                        coalesce(
                            judgment.grade,
                            0
                        )::numeric
                    ) - 1
                )
                /
                pg_catalog.log(
                    2::numeric,
                    (retrieved.result_rank + 1)::numeric
                )
            ),
            0
        ) AS dcg
    FROM evaluation_grid AS grid
    LEFT JOIN retrieved
      ON retrieved.strategy = grid.strategy
     AND retrieved.query_id = grid.query_id
    LEFT JOIN shop_ch15.relevance_judgment AS judgment
      ON judgment.query_id = retrieved.query_id
     AND judgment.product_id = retrieved.product_id
    GROUP BY grid.strategy, grid.query_id
)
SELECT
    observed.strategy,
    observed.query_id,
    observed.result_count,
    observed.relevant_retrieved,
    relevant_total.relevant_count,
    pg_catalog.round(
        observed.relevant_retrieved::numeric / 3,
        6
    ) AS precision_at_3,
    pg_catalog.round(
        observed.relevant_retrieved::numeric
        /
        relevant_total.relevant_count,
        6
    ) AS recall_at_3,
    pg_catalog.round(
        CASE
            WHEN observed.first_relevant_rank IS NULL
                THEN 0
            ELSE 1::numeric /
                 observed.first_relevant_rank
        END,
        6
    ) AS reciprocal_rank_at_3,
    pg_catalog.round(
        observed.dcg / ideal.ideal_dcg,
        6
    ) AS ndcg_at_3
FROM observed
JOIN relevant_total
  ON relevant_total.query_id = observed.query_id
JOIN ideal
  ON ideal.query_id = observed.query_id;

CREATE VIEW shop_ch15.quality_summary AS
SELECT
    strategy,
    pg_catalog.count(*) AS query_count,
    pg_catalog.round(
        pg_catalog.avg(precision_at_3),
        6
    ) AS mean_precision_at_3,
    pg_catalog.round(
        pg_catalog.avg(recall_at_3),
        6
    ) AS mean_recall_at_3,
    pg_catalog.round(
        pg_catalog.avg(reciprocal_rank_at_3),
        6
    ) AS mrr_at_3,
    pg_catalog.round(
        pg_catalog.avg(ndcg_at_3),
        6
    ) AS mean_ndcg_at_3,
    pg_catalog.round(
        pg_catalog.min(ndcg_at_3),
        6
    ) AS min_ndcg_at_3
FROM shop_ch15.quality_per_query
GROUP BY strategy;
