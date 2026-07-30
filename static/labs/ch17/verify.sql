\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    data_schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17');
    extension_schema_oid oid :=
        pg_catalog.to_regnamespace('shop_ch17_ext');
    expected_marker constant text :=
        'pg36 ch17 analytics fdw lab; safe to rebuild';
    business_checksum text;
    local_monthly_checksum text;
    summary_monthly_checksum text;
    distributed_monthly_checksum text;
    two_stage_monthly_checksum text;
BEGIN
    IF data_schema_oid IS NULL
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid = data_schema_oid
              )
          ) <> 'pg36_owner'
       OR pg_catalog.obj_description(
              data_schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'ch17 data schema identity or marker drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = data_schema_oid
          AND (
              relation.relname <> ALL (ARRAY[
                  'fixture_meta',
                  'fixture_meta_pkey',
                  'account_dim',
                  'account_dim_pkey',
                  'sales_fact',
                  'sales_fact_pkey',
                  'sales_fact_tenant_day_idx',
                  'sales_fact_day_brin_idx',
                  'daily_tenant_summary',
                  'daily_tenant_summary_pkey',
                  'account_dim_distributed',
                  'account_dim_dist_0',
                  'account_dim_dist_1',
                  'sales_fact_distributed',
                  'sales_fact_dist_0',
                  'sales_fact_dist_1',
                  'local_tenant_month',
                  'distributed_tenant_month'
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
           WHERE relation.relnamespace = data_schema_oid
       ) <> 18
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace = data_schema_oid
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator AS operator_catalog
           WHERE operator_catalog.oprnamespace =
                     data_schema_oid
       ) THEN
        RAISE EXCEPTION
            'ch17 relation inventory or marker drifted';
    END IF;

    IF extension_schema_oid IS NULL
       OR pg_catalog.pg_get_userbyid(
              (
                  SELECT namespace.nspowner
                  FROM pg_catalog.pg_namespace AS namespace
                  WHERE namespace.oid =
                        extension_schema_oid
              )
          ) <> 'pg36_owner'
       OR pg_catalog.obj_description(
              extension_schema_oid,
              'pg_namespace'
          ) IS DISTINCT FROM expected_marker
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_extension
           WHERE extnamespace = extension_schema_oid
       ) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_extension AS extension_catalog
           JOIN pg_catalog.pg_roles AS role
             ON role.oid = extension_catalog.extowner
           WHERE extension_catalog.extname = 'postgres_fdw'
             AND extension_catalog.extversion = '1.2'
             AND extension_catalog.extnamespace =
                     extension_schema_oid
             AND extension_catalog.extrelocatable
             AND role.rolsuper
             AND pg_catalog.obj_description(
                     extension_catalog.oid,
                     'pg_extension'
                 ) = expected_marker
       )
       OR (
           SELECT pg_catalog.count(*)
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace =
                     extension_schema_oid
             AND EXISTS (
                 SELECT 1
                 FROM pg_catalog.pg_depend AS dependency
                 WHERE dependency.classid =
                           'pg_catalog.pg_proc'::pg_catalog.regclass
                   AND dependency.objid = routine.oid
                   AND dependency.refclassid =
                           'pg_catalog.pg_extension'::pg_catalog.regclass
                   AND dependency.deptype = 'e'
             )
       ) <> 5
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_proc AS routine
           WHERE routine.pronamespace =
                     extension_schema_oid
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
           WHERE relation.relnamespace =
                     extension_schema_oid
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_foreign_data_wrapper AS wrapper
           WHERE wrapper.fdwname = 'postgres_fdw'
             AND pg_catalog.obj_description(
                     wrapper.oid,
                     'pg_foreign_data_wrapper'
                 ) = expected_marker
       ) THEN
        RAISE EXCEPTION
            'ch17 postgres_fdw extension identity drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_foreign_server
        WHERE srvname IN (
            'pg36_ch17_shard_a',
            'pg36_ch17_shard_b'
        )
    ) <> 2
       OR EXISTS (
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
                 OR NOT server_catalog.srvoptions @> ARRAY[
                        'host=' ||
                            current_setting(
                                'unix_socket_directories'
                            ),
                        'port=' || current_setting('port'),
                        'fetch_size=10000',
                        'dbname=' ||
                            CASE server_catalog.srvname
                                WHEN 'pg36_ch17_shard_a'
                                    THEN 'pg36_shard_a'
                                WHEN 'pg36_ch17_shard_b'
                                    THEN 'pg36_shard_b'
                            END
                    ]
             )
       ) THEN
        RAISE EXCEPTION
            'ch17 foreign server identity or options drifted';
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
    ) <> 6
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.pg_user_mapping AS mapping
           JOIN pg_catalog.pg_foreign_server AS server_catalog
             ON server_catalog.oid = mapping.umserver
           WHERE server_catalog.srvname IN (
               'pg36_ch17_shard_a',
               'pg36_ch17_shard_b'
           )
             AND (
                 mapping.umuser = 0
                 OR NOT mapping.umoptions @>
                        ARRAY['password_required=false']
                 OR NOT mapping.umoptions @>
                        ARRAY[
                            'user=' ||
                            CASE
                                WHEN pg_catalog.pg_get_userbyid(
                                         mapping.umuser
                                     ) = 'pg36_app'
                                    THEN 'pg36_app'
                                ELSE 'postgres'
                            END
                        ]
             )
       ) THEN
        RAISE EXCEPTION
            'ch17 user mapping inventory or options drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch17.fixture_meta
        WHERE fixture_version = 'ch17-analytics-v1'
          AND generator_identity = 'fixture-generator-v1'
          AND tenant_count = 8
          AND accounts_per_tenant = 50
          AND day_count = 120
          AND sales_per_account_day = 5
          AND first_day = DATE '2026-01-01'
          AND distribution_key = 'tenant_id'
          AND shard_modulus = 2
          AND frozen_at =
              TIMESTAMPTZ '2026-07-29 00:00:00+00'
    ) <> 1
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch17.account_dim
       ) <> 400
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch17.sales_fact
       ) <> 240000
       OR (
           SELECT pg_catalog.sum(units)
           FROM shop_ch17.sales_fact
       ) <> 1200000
       OR (
           SELECT pg_catalog.sum(amount)
           FROM shop_ch17.sales_fact
       ) <> 2256000.00
       OR (
           SELECT pg_catalog.count(*)
           FROM shop_ch17.daily_tenant_summary
       ) <> 2880
       OR (
           SELECT pg_catalog.sum(sale_count)
           FROM shop_ch17.daily_tenant_summary
       ) <> 240000 THEN
        RAISE EXCEPTION
            'ch17 local fixture or summary drifted';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM shop_ch17.sales_fact_distributed
    ) <> 240000
       OR (
           SELECT pg_catalog.sum(units)
           FROM shop_ch17.sales_fact_distributed
       ) <> 1200000
       OR (
           SELECT pg_catalog.sum(amount)
           FROM shop_ch17.sales_fact_distributed
       ) <> 2256000.00
       OR (
           SELECT pg_catalog.string_agg(
                      tableoid::pg_catalog.regclass::text ||
                      ':' || sale_count::text,
                      ',' ORDER BY
                          tableoid::pg_catalog.regclass::text
                  )
           FROM (
               SELECT
                   tableoid,
                   pg_catalog.count(*) AS sale_count
               FROM shop_ch17.sales_fact_distributed
               GROUP BY tableoid
           ) AS per_shard
       ) <>
       'shop_ch17.sales_fact_dist_0:120000,' ||
       'shop_ch17.sales_fact_dist_1:120000'
       OR EXISTS (
           SELECT 1
           FROM shop_ch17.sales_fact_dist_0
           WHERE pg_catalog.mod(tenant_id, 2) <> 0
       )
       OR EXISTS (
           SELECT 1
           FROM shop_ch17.sales_fact_dist_1
           WHERE pg_catalog.mod(tenant_id, 2) <> 1
       ) THEN
        RAISE EXCEPTION
            'ch17 distributed data or placement drifted';
    END IF;

    IF pg_catalog.pg_get_partkeydef(
           'shop_ch17.sales_fact_distributed'
               ::pg_catalog.regclass
       ) <> 'LIST (tenant_id)'
       OR pg_catalog.pg_get_partkeydef(
              'shop_ch17.account_dim_distributed'
                  ::pg_catalog.regclass
          ) <> 'LIST (tenant_id)'
       OR pg_catalog.pg_get_expr(
              (
                  SELECT relpartbound
                  FROM pg_catalog.pg_class
                  WHERE oid =
                        'shop_ch17.sales_fact_dist_0'
                            ::pg_catalog.regclass
              ),
              'shop_ch17.sales_fact_dist_0'
                  ::pg_catalog.regclass
          ) <> 'FOR VALUES IN (2, 4, 6, 8)'
       OR pg_catalog.pg_get_expr(
              (
                  SELECT relpartbound
                  FROM pg_catalog.pg_class
                  WHERE oid =
                        'shop_ch17.sales_fact_dist_1'
                            ::pg_catalog.regclass
              ),
              'shop_ch17.sales_fact_dist_1'
                  ::pg_catalog.regclass
          ) <> 'FOR VALUES IN (1, 3, 5, 7)' THEN
        RAISE EXCEPTION
            'ch17 distribution-key or placement contract drifted';
    END IF;

    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   pg_catalog.concat_ws(
                       '|',
                       tenant_id,
                       month_start,
                       sale_count,
                       unit_count,
                       amount_total
                   ),
                   E'\n'
                   ORDER BY tenant_id, month_start
               )
           )
    INTO local_monthly_checksum
    FROM shop_ch17.local_tenant_month;

    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   pg_catalog.concat_ws(
                       '|',
                       tenant_id,
                       month_start,
                       sale_count,
                       unit_count,
                       amount_total
                   ),
                   E'\n'
                   ORDER BY tenant_id, month_start
               )
           )
    INTO distributed_monthly_checksum
    FROM shop_ch17.distributed_tenant_month;

    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   pg_catalog.concat_ws(
                       '|',
                       tenant_id,
                       month_start,
                       sale_count,
                       unit_count,
                       amount_total
                   ),
                   E'\n'
                   ORDER BY tenant_id, month_start
               )
           )
    INTO summary_monthly_checksum
    FROM (
        SELECT
            tenant_id,
            pg_catalog.date_trunc(
                'month',
                occurred_on::timestamp
            )::date AS month_start,
            pg_catalog.sum(sale_count)::bigint
                AS sale_count,
            pg_catalog.sum(unit_count)::bigint
                AS unit_count,
            pg_catalog.sum(amount_total)::numeric(18,2)
                AS amount_total
        FROM shop_ch17.daily_tenant_summary
        GROUP BY tenant_id, month_start
    ) AS summary_month;

    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   pg_catalog.concat_ws(
                       '|',
                       tenant_id,
                       month_start,
                       sale_count,
                       unit_count,
                       amount_total
                   ),
                   E'\n'
                   ORDER BY tenant_id, month_start
               )
           )
    INTO two_stage_monthly_checksum
    FROM (
        SELECT
            tenant_id,
            pg_catalog.date_trunc(
                'month',
                occurred_on::timestamp
            )::date AS month_start,
            pg_catalog.sum(sale_count)::bigint
                AS sale_count,
            pg_catalog.sum(unit_count)::bigint
                AS unit_count,
            pg_catalog.sum(amount_total)::numeric(18,2)
                AS amount_total
        FROM (
            SELECT
                tenant_id,
                occurred_on,
                pg_catalog.count(*) AS sale_count,
                pg_catalog.sum(units)::bigint AS unit_count,
                pg_catalog.sum(amount)::numeric(18,2)
                    AS amount_total
            FROM shop_ch17.sales_fact_dist_0
            GROUP BY tenant_id, occurred_on

            UNION ALL

            SELECT
                tenant_id,
                occurred_on,
                pg_catalog.count(*) AS sale_count,
                pg_catalog.sum(units)::bigint AS unit_count,
                pg_catalog.sum(amount)::numeric(18,2)
                    AS amount_total
            FROM shop_ch17.sales_fact_dist_1
            GROUP BY tenant_id, occurred_on
        ) AS shard_daily
        GROUP BY tenant_id, month_start
    ) AS two_stage_month;

    IF local_monthly_checksum <>
           '644d45544ebbc2a80c42270c38ac6885'
       OR summary_monthly_checksum <>
           local_monthly_checksum
       OR distributed_monthly_checksum <>
           local_monthly_checksum
       OR two_stage_monthly_checksum <>
           local_monthly_checksum THEN
        RAISE EXCEPTION
            'ch17 monthly result checksums drifted: local %, summary %, distributed %, two-stage %',
            local_monthly_checksum,
            summary_monthly_checksum,
            distributed_monthly_checksum,
            two_stage_monthly_checksum;
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_catalog.indexrelid
        WHERE index_relation.relnamespace = data_schema_oid
          AND index_catalog.indisvalid
          AND index_catalog.indisready
          AND index_catalog.indislive
    ) <> 6
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
                     'shop_ch17.sales_fact_day_brin_idx'
                         ::pg_catalog.regclass
             AND access_method.amname = 'brin'
             AND operator_class.opcname =
                     'date_minmax_ops'
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_index AS index_catalog
           JOIN pg_catalog.pg_class AS index_relation
             ON index_relation.oid = index_catalog.indexrelid
           WHERE index_relation.oid =
                     'shop_ch17.sales_fact_tenant_day_idx'
                         ::pg_catalog.regclass
             AND index_catalog.indnkeyatts = 3
             AND index_catalog.indnatts = 6
       )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_class AS relation
           WHERE relation.oid =
                     'shop_ch17.sales_fact'
                         ::pg_catalog.regclass
             AND relation.reloptions @>
                     ARRAY['parallel_workers=2']
       ) THEN
        RAISE EXCEPTION
            'ch17 index or parallel-table contract drifted';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
               'pg36_app',
               'shop_ch17',
               'USAGE'
           )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch17.sales_fact',
                  'SELECT'
              )
       OR NOT pg_catalog.has_table_privilege(
                  'pg36_app',
                  'shop_ch17.sales_fact_distributed',
                  'SELECT'
              )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch17.sales_fact',
              'INSERT,UPDATE,DELETE'
          )
       OR pg_catalog.has_table_privilege(
              'pg36_app',
              'shop_ch17.sales_fact_distributed',
              'INSERT,UPDATE,DELETE'
          )
       OR NOT pg_catalog.has_server_privilege(
                  'pg36_app',
                  'pg36_ch17_shard_a',
                  'USAGE'
              )
       OR NOT pg_catalog.has_server_privilege(
                  'pg36_app',
                  'pg36_ch17_shard_b',
                  'USAGE'
              ) THEN
        RAISE EXCEPTION
            'ch17 application privilege boundary drifted';
    END IF;

    WITH business_rows AS (
        SELECT
            'account'::text AS kind,
            pg_catalog.lpad(tenant_id::text, 2, '0') ||
                '|' ||
                pg_catalog.lpad(account_id::text, 3, '0')
                AS sort_key,
            pg_catalog.concat_ws(
                '|',
                tenant_id,
                account_id,
                segment,
                region
            ) AS payload
        FROM shop_ch17.account_dim

        UNION ALL

        SELECT
            'sale',
            pg_catalog.lpad(sale_id::text, 9, '0'),
            pg_catalog.concat_ws(
                '|',
                sale_id,
                tenant_id,
                account_id,
                occurred_on,
                channel,
                units,
                amount
            )
        FROM shop_ch17.sales_fact
    )
    SELECT pg_catalog.md5(
               pg_catalog.string_agg(
                   kind || '|' || payload,
                   E'\n'
                   ORDER BY kind, sort_key
               )
           )
    INTO business_checksum
    FROM business_rows;

    IF business_checksum <>
           '42fb8ab5444469eba1f104a8e1e529dd' THEN
        RAISE EXCEPTION
            'ch17 business checksum drifted: %',
            business_checksum;
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=generator-v1';
SELECT 'single_node=parallel+index+summary+spill';
SELECT 'distributed=tenant-pruning+fdw+two-stage';
SELECT 'rows=240000';
SELECT 'monthly_checksum=644d45544ebbc2a80c42270c38ac6885';
SELECT 'business_checksum=42fb8ab5444469eba1f104a8e1e529dd';
