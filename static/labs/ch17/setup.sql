\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

DO $data_collision_guard$
DECLARE
    schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17');
    expected_marker constant text :=
        'pg36 ch17 analytics fdw lab; safe to rebuild';
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
            'refusing collision: shop_ch17 identity drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND pg_catalog.obj_description(
                  relation.oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker
    )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace = schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace = schema_oid
       ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch17 object inventory drifted';
    END IF;
END
$data_collision_guard$;

DROP VIEW IF EXISTS shop_ch17.distributed_tenant_month;
DROP VIEW IF EXISTS shop_ch17.local_tenant_month;
DROP MATERIALIZED VIEW IF EXISTS
    shop_ch17.daily_tenant_summary;
DROP TABLE IF EXISTS shop_ch17.sales_fact_distributed;
DROP TABLE IF EXISTS shop_ch17.account_dim_distributed;
DROP TABLE IF EXISTS shop_ch17.sales_fact;
DROP TABLE IF EXISTS shop_ch17.account_dim;
DROP TABLE IF EXISTS shop_ch17.fixture_meta;
DROP SCHEMA IF EXISTS shop_ch17;

DO $server_collision_guard$
DECLARE
    expected_marker constant text :=
        'pg36 ch17 analytics fdw lab; safe to rebuild';
BEGIN
    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_foreign_server
        WHERE srvname IN (
            'pg36_ch17_shard_a',
            'pg36_ch17_shard_b'
        )
    ) NOT IN (0, 2) THEN
        RAISE EXCEPTION
            'refusing collision: partial ch17 server inventory';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_foreign_server AS server_catalog
        JOIN pg_catalog.pg_foreign_data_wrapper AS wrapper
          ON wrapper.oid = server_catalog.srvfdw
        WHERE server_catalog.srvname IN (
            'pg36_ch17_shard_a',
            'pg36_ch17_shard_b'
        )
          AND (
              wrapper.fdwname <> 'postgres_fdw'
              OR pg_catalog.pg_get_userbyid(
                     server_catalog.srvowner
                 ) <> 'pg36_owner'
              OR pg_catalog.obj_description(
                     server_catalog.oid,
                     'pg_foreign_server'
                 ) IS DISTINCT FROM expected_marker
          )
    ) THEN
        RAISE EXCEPTION
            'refusing collision: ch17 server identity drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_user_mapping AS mapping
        JOIN pg_catalog.pg_foreign_server AS server_catalog
          ON server_catalog.oid = mapping.umserver
        WHERE server_catalog.srvname IN (
            'pg36_ch17_shard_a',
            'pg36_ch17_shard_b'
        )
    ) NOT IN (0, 6) THEN
        RAISE EXCEPTION
            'refusing collision: ch17 user mapping inventory drifted';
    END IF;
END
$server_collision_guard$;

DROP USER MAPPING IF EXISTS
    FOR postgres SERVER pg36_ch17_shard_a;
DROP USER MAPPING IF EXISTS
    FOR pg36_owner SERVER pg36_ch17_shard_a;
DROP USER MAPPING IF EXISTS
    FOR pg36_app SERVER pg36_ch17_shard_a;
DROP USER MAPPING IF EXISTS
    FOR postgres SERVER pg36_ch17_shard_b;
DROP USER MAPPING IF EXISTS
    FOR pg36_owner SERVER pg36_ch17_shard_b;
DROP USER MAPPING IF EXISTS
    FOR pg36_app SERVER pg36_ch17_shard_b;
DROP SERVER IF EXISTS pg36_ch17_shard_a;
DROP SERVER IF EXISTS pg36_ch17_shard_b;

DO $extension_collision_guard$
DECLARE
    schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17_ext');
    expected_marker constant text :=
        'pg36 ch17 analytics fdw lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_extension
            WHERE extname = 'postgres_fdw'
        ) THEN
            RAISE EXCEPTION
                'refusing collision: postgres_fdw exists outside ch17 schema';
        END IF;
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
          ) IS DISTINCT FROM expected_marker
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_extension
           WHERE extnamespace = schema_oid
       ) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           JOIN pg_catalog.pg_roles AS role
             ON role.oid = extension_catalog.extowner
           WHERE extension_catalog.extname = 'postgres_fdw'
             AND extension_catalog.extversion = '1.2'
             AND extension_catalog.extnamespace = schema_oid
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION
            'refusing collision: postgres_fdw identity drifted';
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
       ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch17_ext has unmanaged objects';
    END IF;
END
$extension_collision_guard$;

DROP EXTENSION IF EXISTS postgres_fdw;
DROP SCHEMA IF EXISTS shop_ch17_ext;

CREATE SCHEMA shop_ch17_ext AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch17_ext IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch17_ext FROM PUBLIC;

CREATE EXTENSION postgres_fdw
    WITH SCHEMA shop_ch17_ext
    VERSION '1.2';
COMMENT ON EXTENSION postgres_fdw IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';
COMMENT ON FOREIGN DATA WRAPPER postgres_fdw IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';
GRANT USAGE ON SCHEMA shop_ch17_ext
    TO pg36_owner, pg36_app;

CREATE SERVER pg36_ch17_shard_a
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (
        host :'fdw_host',
        port :'fdw_port',
        dbname 'pg36_shard_a',
        fetch_size '10000'
    );
ALTER SERVER pg36_ch17_shard_a OWNER TO pg36_owner;
COMMENT ON SERVER pg36_ch17_shard_a IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';

CREATE SERVER pg36_ch17_shard_b
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (
        host :'fdw_host',
        port :'fdw_port',
        dbname 'pg36_shard_b',
        fetch_size '10000'
    );
ALTER SERVER pg36_ch17_shard_b OWNER TO pg36_owner;
COMMENT ON SERVER pg36_ch17_shard_b IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';

GRANT USAGE ON FOREIGN SERVER pg36_ch17_shard_a
    TO pg36_app;
GRANT USAGE ON FOREIGN SERVER pg36_ch17_shard_b
    TO pg36_app;

CREATE USER MAPPING FOR postgres
    SERVER pg36_ch17_shard_a
    OPTIONS (
        user 'postgres',
        password_required 'false'
    );
CREATE USER MAPPING FOR pg36_owner
    SERVER pg36_ch17_shard_a
    OPTIONS (
        user 'postgres',
        password_required 'false'
    );
CREATE USER MAPPING FOR pg36_app
    SERVER pg36_ch17_shard_a
    OPTIONS (
        user 'pg36_app',
        password_required 'false'
    );

CREATE USER MAPPING FOR postgres
    SERVER pg36_ch17_shard_b
    OPTIONS (
        user 'postgres',
        password_required 'false'
    );
CREATE USER MAPPING FOR pg36_owner
    SERVER pg36_ch17_shard_b
    OPTIONS (
        user 'postgres',
        password_required 'false'
    );
CREATE USER MAPPING FOR pg36_app
    SERVER pg36_ch17_shard_b
    OPTIONS (
        user 'pg36_app',
        password_required 'false'
    );

SET ROLE pg36_owner;

CREATE SCHEMA shop_ch17 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch17 IS
    'pg36 ch17 analytics fdw lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch17 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch17 TO pg36_app;

CREATE TABLE shop_ch17.fixture_meta (
    fixture_version text PRIMARY KEY,
    generator_identity text NOT NULL,
    tenant_count integer NOT NULL,
    accounts_per_tenant integer NOT NULL,
    day_count integer NOT NULL,
    sales_per_account_day integer NOT NULL,
    first_day date NOT NULL,
    distribution_key text NOT NULL,
    shard_modulus integer NOT NULL,
    frozen_at timestamptz NOT NULL
);

CREATE TABLE shop_ch17.account_dim (
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    segment text NOT NULL,
    region text NOT NULL,
    PRIMARY KEY (tenant_id, account_id)
);

CREATE TABLE shop_ch17.sales_fact (
    sale_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    occurred_on date NOT NULL,
    channel text NOT NULL,
    units smallint NOT NULL,
    amount numeric(12,2) NOT NULL,
    FOREIGN KEY (tenant_id, account_id)
        REFERENCES shop_ch17.account_dim (
            tenant_id,
            account_id
        ),
    CHECK (occurred_on >= DATE '2026-01-01'),
    CHECK (occurred_on < DATE '2026-05-01'),
    CHECK (units BETWEEN 1 AND 9),
    CHECK (amount > 0)
) WITH (parallel_workers = 2);

CREATE INDEX sales_fact_tenant_day_idx
    ON shop_ch17.sales_fact (
        tenant_id,
        occurred_on,
        account_id
    )
    INCLUDE (amount, units, channel);

CREATE INDEX sales_fact_day_brin_idx
    ON shop_ch17.sales_fact
    USING brin (occurred_on)
    WITH (pages_per_range = 16);

\ir fixture.sql

CREATE MATERIALIZED VIEW
    shop_ch17.daily_tenant_summary AS
SELECT
    tenant_id,
    occurred_on,
    channel,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(units)::bigint AS unit_count,
    pg_catalog.sum(amount)::numeric(18,2) AS amount_total
FROM shop_ch17.sales_fact
GROUP BY tenant_id, occurred_on, channel
WITH DATA;

CREATE UNIQUE INDEX daily_tenant_summary_pkey
    ON shop_ch17.daily_tenant_summary (
        tenant_id,
        occurred_on,
        channel
    );

CREATE TABLE shop_ch17.account_dim_distributed (
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    segment text NOT NULL,
    region text NOT NULL
) PARTITION BY LIST (tenant_id);

CREATE FOREIGN TABLE shop_ch17.account_dim_dist_0
    PARTITION OF shop_ch17.account_dim_distributed
    FOR VALUES IN (2, 4, 6, 8)
    SERVER pg36_ch17_shard_a
    OPTIONS (
        schema_name 'shop_ch17_shard',
        table_name 'account_dim'
    );

CREATE FOREIGN TABLE shop_ch17.account_dim_dist_1
    PARTITION OF shop_ch17.account_dim_distributed
    FOR VALUES IN (1, 3, 5, 7)
    SERVER pg36_ch17_shard_b
    OPTIONS (
        schema_name 'shop_ch17_shard',
        table_name 'account_dim'
    );

CREATE TABLE shop_ch17.sales_fact_distributed (
    sale_id bigint NOT NULL,
    tenant_id integer NOT NULL,
    account_id integer NOT NULL,
    occurred_on date NOT NULL,
    channel text NOT NULL,
    units smallint NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY LIST (tenant_id);

CREATE FOREIGN TABLE shop_ch17.sales_fact_dist_0
    PARTITION OF shop_ch17.sales_fact_distributed
    FOR VALUES IN (2, 4, 6, 8)
    SERVER pg36_ch17_shard_a
    OPTIONS (
        schema_name 'shop_ch17_shard',
        table_name 'sales_fact'
    );

CREATE FOREIGN TABLE shop_ch17.sales_fact_dist_1
    PARTITION OF shop_ch17.sales_fact_distributed
    FOR VALUES IN (1, 3, 5, 7)
    SERVER pg36_ch17_shard_b
    OPTIONS (
        schema_name 'shop_ch17_shard',
        table_name 'sales_fact'
    );

CREATE VIEW shop_ch17.local_tenant_month AS
SELECT
    tenant_id,
    pg_catalog.date_trunc(
        'month',
        occurred_on::timestamp
    )::date AS month_start,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(units)::bigint AS unit_count,
    pg_catalog.sum(amount)::numeric(18,2) AS amount_total
FROM shop_ch17.sales_fact
GROUP BY tenant_id, month_start;

CREATE VIEW shop_ch17.distributed_tenant_month AS
SELECT
    tenant_id,
    pg_catalog.date_trunc(
        'month',
        occurred_on::timestamp
    )::date AS month_start,
    pg_catalog.count(*) AS sale_count,
    pg_catalog.sum(units)::bigint AS unit_count,
    pg_catalog.sum(amount)::numeric(18,2) AS amount_total
FROM shop_ch17.sales_fact_distributed
GROUP BY tenant_id, month_start;

DO $mark_relations$
DECLARE
    relation record;
    marker constant text :=
        'pg36 ch17 analytics fdw lab; safe to rebuild';
BEGIN
    FOR relation IN
        SELECT
            namespace.nspname AS schema_name,
            catalog.relname AS relation_name,
            catalog.relkind
        FROM pg_catalog.pg_class AS catalog
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = catalog.relnamespace
        WHERE namespace.nspname = 'shop_ch17'
    LOOP
        IF relation.relkind IN ('r', 'p') THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON TABLE %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind = 'f' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON FOREIGN TABLE %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind IN ('i', 'I') THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON INDEX %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind = 'm' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON MATERIALIZED VIEW %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSIF relation.relkind = 'v' THEN
            EXECUTE pg_catalog.format(
                'COMMENT ON VIEW %I.%I IS %L',
                relation.schema_name,
                relation.relation_name,
                marker
            );
        ELSE
            RAISE EXCEPTION
                'unexpected ch17 relation kind: %.% %',
                relation.schema_name,
                relation.relation_name,
                relation.relkind;
        END IF;
    END LOOP;
END
$mark_relations$;

GRANT SELECT ON
    shop_ch17.account_dim,
    shop_ch17.sales_fact,
    shop_ch17.daily_tenant_summary,
    shop_ch17.account_dim_distributed,
    shop_ch17.sales_fact_distributed,
    shop_ch17.local_tenant_month,
    shop_ch17.distributed_tenant_month
TO pg36_app;

ANALYZE shop_ch17.account_dim;
ANALYZE shop_ch17.sales_fact;
ANALYZE shop_ch17.daily_tenant_summary;
ANALYZE shop_ch17.account_dim_distributed;
ANALYZE shop_ch17.sales_fact_distributed;

RESET ROLE;

COMMIT;

-- The covering-index probe asserts Heap Fetches: 0.  A freshly loaded table
-- has not yet set its visibility-map all-visible bits, so make that
-- precondition explicit instead of relying on a previous autovacuum cycle.
VACUUM (ANALYZE) shop_ch17.sales_fact;

\pset format unaligned
\pset tuples_only on
SELECT 'status=fixture-ready';
SELECT 'local_sales=' ||
       pg_catalog.count(*)::text
FROM shop_ch17.sales_fact;
SELECT 'distributed_sales=' ||
       pg_catalog.count(*)::text
FROM shop_ch17.sales_fact_distributed;
SELECT 'summary_rows=' ||
       pg_catalog.count(*)::text
FROM shop_ch17.daily_tenant_summary;
SELECT 'postgres_fdw=' ||
       extversion
FROM pg_catalog.pg_extension
WHERE extname = 'postgres_fdw';
