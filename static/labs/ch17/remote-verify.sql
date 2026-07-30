\set ON_ERROR_STOP on
\pset pager off
\ir remote-context.sql

SELECT pg_catalog.set_config(
    'pg36.shard_marker',
    :'shard_marker',
    false
);
SELECT pg_catalog.set_config(
    'pg36.shard_remainder',
    :'shard_remainder',
    false
);

DO $verify$
DECLARE
    schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17_shard');
    expected_marker constant text :=
        current_setting('pg36.shard_marker');
    expected_remainder constant integer :=
        current_setting('pg36.shard_remainder')::integer;
    actual_checksum text;
    expected_checksum text;
BEGIN
    expected_checksum :=
        CASE expected_remainder
            WHEN 0 THEN
                '274002669404fbcd449bdecd929624e3'
            WHEN 1 THEN
                '0bb770361058ec76ebc81a2a7d1e2629'
            ELSE NULL
        END;

    IF expected_checksum IS NULL THEN
        RAISE EXCEPTION
            'invalid remote shard remainder: %',
            expected_remainder;
    END IF;

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
            'ch17 remote schema identity or marker drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND (
              relation.relname <> ALL (ARRAY[
                  'fixture_meta',
                  'fixture_meta_pkey',
                  'account_dim',
                  'account_dim_pkey',
                  'sales_fact',
                  'sales_fact_pkey',
                  'sales_fact_tenant_day_idx'
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
       ) <> 7
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace = schema_oid
       ) THEN
        RAISE EXCEPTION
            'ch17 remote relation inventory drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch17_shard.fixture_meta
        WHERE fixture_version = 'ch17-analytics-v1'
          AND generator_identity = 'fixture-generator-v1'
          AND shard_modulus = 2
          AND shard_remainder = expected_remainder
          AND tenant_count = 8
          AND accounts_per_tenant = 50
          AND day_count = 120
          AND sales_per_account_day = 5
          AND first_day = DATE '2026-01-01'
          AND frozen_at =
              TIMESTAMPTZ '2026-07-29 00:00:00+00'
    ) <> 1
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch17_shard.account_dim
       ) <> 200
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch17_shard.sales_fact
       ) <> 120000
       OR EXISTS (
           SELECT 1
           FROM shop_ch17_shard.account_dim
           WHERE pg_catalog.mod(tenant_id, 2) <>
                 expected_remainder
       )
       OR EXISTS (
           SELECT 1
           FROM shop_ch17_shard.sales_fact
           WHERE pg_catalog.mod(tenant_id, 2) <>
                 expected_remainder
       ) THEN
        RAISE EXCEPTION
            'ch17 remote fixture cardinality or distribution drifted';
    END IF;

    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   sale_id::text || '|' ||
                   tenant_id::text || '|' ||
                   account_id::text || '|' ||
                   occurred_on::text || '|' ||
                   channel || '|' ||
                   units::text || '|' ||
                   amount::text,
                   E'\n' ORDER BY sale_id
               )
           )
    INTO actual_checksum
    FROM shop_ch17_shard.sales_fact;

    IF actual_checksum <> expected_checksum THEN
        RAISE EXCEPTION
            'ch17 remote checksum drifted: %',
            actual_checksum;
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
               'pg36_app',
               'shop_ch17_shard',
               'USAGE'
           )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch17_shard.sales_fact',
                  'SELECT'
              )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch17_shard.sales_fact',
              'INSERT,UPDATE,DELETE'
          ) THEN
        RAISE EXCEPTION
            'ch17 remote application privileges drifted';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=remote-ok';
SELECT 'database=' || current_database();
SELECT 'remainder=' || :'shard_remainder';
SELECT 'sales=120000';
