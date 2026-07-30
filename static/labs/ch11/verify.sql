\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $verify$
DECLARE
    expected_marker constant text :=
        'pg36 ch11 deterministic release lab; safe to rebuild';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch11-%'
    ) THEN
        RAISE EXCEPTION 'a ch11 lab worker is still connected';
    END IF;

    IF pg_catalog.obj_description(
           'shop_private.ch11_order'::regclass,
           'pg_class'
       ) IS DISTINCT FROM expected_marker
       OR pg_catalog.obj_description(
           'shop_private.ch11_migration_state'::regclass,
           'pg_class'
       ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION 'ch11 fixture marker drifted';
    END IF;

    IF (
        SELECT phase
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM 'switched' THEN
        RAISE EXCEPTION 'ch11 release did not stop at switched';
    END IF;

    IF (
        SELECT ROW(
            source_rows,
            target_rows,
            rows_migrated,
            batches,
            last_order_id
        )
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM ROW(
        50000::bigint,
        49999::bigint,
        49999::bigint,
        10,
        50000::bigint
    ) THEN
        RAISE EXCEPTION 'ch11 backfill checkpoint drifted';
    END IF;

    IF (SELECT count(*) FROM shop_private.ch11_order) <> 50004
       OR EXISTS (
           SELECT 1
           FROM shop_private.ch11_order
           WHERE shipping_code IS NULL
              OR shipping_code IS DISTINCT FROM
                 CASE shipping_method
                     WHEN 'standard' THEN 'STD'
                     WHEN 'express' THEN 'EXP'
                     WHEN 'pickup' THEN 'PUP'
                 END
       ) THEN
        RAISE EXCEPTION 'ch11 order representation drifted';
    END IF;

    IF NOT (
        SELECT attnotnull
        FROM pg_catalog.pg_attribute
        WHERE attrelid =
              'shop_private.ch11_order'::regclass
          AND attname = 'shipping_code'
          AND attnum > 0
          AND NOT attisdropped
    )
       OR NOT EXISTS (
           SELECT 1
           FROM pg_catalog.pg_attribute
           WHERE attrelid =
                 'shop_private.ch11_order'::regclass
             AND attname = 'shipping_method'
             AND attnum > 0
             AND NOT attisdropped
       ) THEN
        RAISE EXCEPTION
            'NOT NULL or rollback-window column state drifted';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_catalog.pg_constraint
        WHERE conrelid =
              'shop_private.ch11_order'::regclass
          AND conname IN (
              'ch11_order_shipping_pair_consistent',
              'ch11_order_shipping_code_nn'
          )
          AND convalidated
    ) <> 2 THEN
        RAISE EXCEPTION 'validated constraint state drifted';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_trigger
        WHERE tgrelid =
              'shop_private.ch11_order'::regclass
          AND tgname = 'ch11_order_shipping_bridge'
          AND NOT tgisinternal
    )
       OR pg_catalog.obj_description(
              'shop_private.ch11_sync_shipping_code()'
                  ::regprocedure::oid,
              'pg_proc'
          ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION 'compatibility bridge drifted';
    END IF;

    IF pg_catalog.to_regclass(
           'shop_private.ch11_order_shipping_missing_idx'
       ) IS NOT NULL THEN
        RAISE EXCEPTION 'temporary backfill index was not removed';
    END IF;

    IF (
        SELECT ROW(
            before_filenode = fast_filenode,
            fast_filenode <> volatile_filenode,
            fast_has_missing,
            NOT volatile_has_missing,
            volatile_wal_bytes > fast_wal_bytes,
            row_count
        )
        FROM shop_private.ch11_default_probe_result
    ) IS DISTINCT FROM ROW(
        true,
        true,
        true,
        true,
        true,
        50000::bigint
    ) THEN
        RAISE EXCEPTION 'default/rewrite evidence drifted';
    END IF;

    IF NOT (
        SELECT relispartition
        FROM pg_catalog.pg_class
        WHERE oid =
              'shop_private.ch11_event_2025q1'::regclass
    )
       OR (
           SELECT count(*)
           FROM shop_private.ch11_event
       ) <> 20000 THEN
        RAISE EXCEPTION 'final partition state drifted';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'release=switched/contract:not-executed';
SELECT 'compatibility=legacy-column+bridge-retained';
SELECT 'backfill=rows:' || rows_migrated ||
       '/batches:' || batches ||
       '/remaining:0'
FROM shop_private.ch11_migration_state
WHERE migration_id = 'shipping-code-v1';
SELECT 'constraints=pair:true/nn:true/attnotnull:true';
SELECT 'partition=attached/rows:' || count(*)
FROM shop_private.ch11_event;
SELECT 'workers=' || count(*)
FROM pg_catalog.pg_stat_activity
WHERE pid <> pg_catalog.pg_backend_pid()
  AND datname = current_database()
  AND application_name LIKE 'pg36-ch11-%';
