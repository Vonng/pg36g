\set ON_ERROR_STOP on
\pset pager off
\ir remote-context.sql

SELECT pg_catalog.set_config(
    'pg36.shard_marker',
    :'shard_marker',
    false
);

BEGIN;

DO $collision_guard$
DECLARE
    schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17_shard');
    expected_marker constant text :=
        current_setting('pg36.shard_marker');
BEGIN
    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.pg_get_userbyid(
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
            'refusing collision: remote schema identity drifted';
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
            'refusing collision: remote object inventory drifted';
    END IF;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_ch17_shard.sales_fact;
DROP TABLE IF EXISTS shop_ch17_shard.account_dim;
DROP TABLE IF EXISTS shop_ch17_shard.fixture_meta;
DROP SCHEMA IF EXISTS shop_ch17_shard;

SET ROLE pg36_owner;

CREATE SCHEMA shop_ch17_shard AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch17_shard IS :'shard_marker';
REVOKE ALL ON SCHEMA shop_ch17_shard FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch17_shard TO pg36_app;

CREATE TABLE shop_ch17_shard.fixture_meta (
    fixture_version text PRIMARY KEY,
    generator_identity text NOT NULL,
    shard_modulus integer NOT NULL,
    shard_remainder integer NOT NULL,
    tenant_count integer NOT NULL,
    accounts_per_tenant integer NOT NULL,
    day_count integer NOT NULL,
    sales_per_account_day integer NOT NULL,
    first_day date NOT NULL,
    frozen_at timestamptz NOT NULL,
    CHECK (shard_modulus = 2),
    CHECK (shard_remainder = :shard_remainder)
);

CREATE TABLE shop_ch17_shard.account_dim (
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    segment text NOT NULL,
    region text NOT NULL,
    PRIMARY KEY (tenant_id, account_id),
    CHECK (
        pg_catalog.mod(tenant_id, 2) =
        :shard_remainder
    )
);

CREATE TABLE shop_ch17_shard.sales_fact (
    sale_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    occurred_on date NOT NULL,
    channel text NOT NULL,
    units smallint NOT NULL,
    amount numeric(12,2) NOT NULL,
    FOREIGN KEY (tenant_id, account_id)
        REFERENCES shop_ch17_shard.account_dim (
            tenant_id,
            account_id
        ),
    CHECK (
        pg_catalog.mod(tenant_id, 2) =
        :shard_remainder
    ),
    CHECK (occurred_on >= DATE '2026-01-01'),
    CHECK (occurred_on < DATE '2026-05-01'),
    CHECK (units BETWEEN 1 AND 9),
    CHECK (amount > 0)
);

CREATE INDEX sales_fact_tenant_day_idx
    ON shop_ch17_shard.sales_fact (
        tenant_id,
        occurred_on,
        account_id
    )
    INCLUDE (amount, units, channel);

\ir fixture-remote.sql

DO $mark_relations$
DECLARE
    relation record;
    expected_marker constant text :=
        current_setting('pg36.shard_marker');
BEGIN
    FOR relation IN
        SELECT
            namespace.nspname AS schema_name,
            catalog.relname AS relation_name,
            catalog.relkind
        FROM pg_catalog.pg_class AS catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = catalog.relnamespace
        WHERE namespace.nspname = 'shop_ch17_shard'
    LOOP
        IF relation.relkind = 'r' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON TABLE %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                expected_marker
            );
        ELSIF relation.relkind = 'i' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON INDEX %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                expected_marker
            );
        ELSE
            RAISE EXCEPTION
                'unexpected remote relation kind: %.% %',
                relation.schema_name,
                relation.relation_name,
                relation.relkind;
        END IF;
    END LOOP;
END
$mark_relations$;

GRANT SELECT ON
    shop_ch17_shard.account_dim,
    shop_ch17_shard.sales_fact
TO pg36_app;

ANALYZE shop_ch17_shard.account_dim;
ANALYZE shop_ch17_shard.sales_fact;

RESET ROLE;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=remote-ready';
SELECT 'database=' || current_database();
SELECT 'remainder=' || :'shard_remainder';
SELECT 'accounts=' ||
       pg_catalog.count(*)::text
FROM shop_ch17_shard.account_dim;
SELECT 'sales=' ||
       pg_catalog.count(*)::text
FROM shop_ch17_shard.sales_fact;
