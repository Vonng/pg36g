\set ON_ERROR_STOP on
\pset pager off
\ir ../ch05/verify.sql
\ir context.sql

DO $verify$
DECLARE
    relation_name text;
    relation_oid regclass;
    expected_marker constant text :=
        'pg36 ch09 deterministic index lab; safe to rebuild';
BEGIN
    FOREACH relation_name IN ARRAY ARRAY[
        'shop_private.ch09_order_probe',
        'shop_private.ch09_inventory_probe',
        'shop_private.ch09_search_probe',
        'shop_private.ch09_event_probe',
        'shop_private.ch09_write_base',
        'shop_private.ch09_write_indexed',
        'shop_private.ch09_unique_probe'
    ]
    LOOP
        relation_oid := pg_catalog.to_regclass(relation_name);
        IF relation_oid IS NULL
           OR pg_catalog.obj_description(
                  relation_oid::oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker THEN
            RAISE EXCEPTION
                'ch09 relation or marker verification failed: %',
                relation_name;
        END IF;
    END LOOP;

    IF (SELECT count(*) FROM shop_private.ch09_order_probe)
           <> 200000
       OR (
           SELECT count(*)
           FROM shop_private.ch09_order_probe
           WHERE order_status = 'placed'
       ) <> 10000
       OR (
           SELECT count(*)
           FROM shop_private.ch09_order_probe
           WHERE customer_id = 42
             AND order_status = 'placed'
       ) <> 10
       OR (SELECT count(*) FROM shop_private.ch09_inventory_probe)
           <> 300000
       OR (
           SELECT count(*)
           FROM shop_private.ch09_inventory_probe
           WHERE sku_id = 4242
       ) <> 30
       OR (SELECT count(*) FROM shop_private.ch09_search_probe)
           <> 100000
       OR (
           SELECT count(*)
           FROM shop_private.ch09_search_probe
           WHERE search_document @@
                 pg_catalog.plainto_tsquery(
                     'simple'::regconfig,
                     'postgresql observability'
                 )
       ) <> 100
       OR (SELECT count(*) FROM shop_private.ch09_event_probe)
           <> 400000
       OR (SELECT count(*) FROM shop_private.ch09_write_base)
           <> 50000
       OR (SELECT count(*) FROM shop_private.ch09_write_indexed)
           <> 50000
       OR (SELECT count(*) FROM shop_private.ch09_unique_probe)
           <> 10000 THEN
        RAISE EXCEPTION 'ch09 deterministic row counts drifted';
    END IF;

    IF (
        SELECT count(*)
        FROM pg_catalog.pg_index
        WHERE indexrelid IN (
            'shop_private.ch09_order_placed_cover_idx'::regclass,
            'shop_private.ch09_inventory_sku_cover_idx'::regclass,
            'shop_private.ch09_search_document_gin_idx'::regclass,
            'shop_private.ch09_event_occurred_brin_idx'::regclass,
            'shop_private.ch09_write_indexed_counter_idx'::regclass
        )
          AND indisvalid
          AND indisready
    ) <> 5 THEN
        RAISE EXCEPTION 'one or more retained ch09 indexes are not valid';
    END IF;

    IF pg_catalog.to_regclass(
           'shop_private.ch09_event_occurred_btree_idx'
       ) IS NOT NULL
       OR pg_catalog.to_regclass(
           'shop_private.ch09_unique_probe_external_ref_uidx'
       ) IS NOT NULL THEN
        RAISE EXCEPTION 'a rejected or failed ch09 index remains';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_stat_activity
        WHERE pid <> pg_catalog.pg_backend_pid()
          AND datname = current_database()
          AND application_name LIKE 'pg36-ch09-%'
    ) THEN
        RAISE EXCEPTION 'a ch09 worker is still connected';
    END IF;
END
$verify$;

\pset format unaligned
\pset tuples_only on

SELECT 'status=ok';
SELECT 'fixture=ch09-index-v1';
SELECT 'order_rows=200000';
SELECT 'inventory_rows=300000';
SELECT 'search_rows=100000';
SELECT 'event_rows=400000';
SELECT 'retained_candidate_indexes=4';
SELECT 'rejected_or_failed_indexes=0';
SELECT 'active_lab_workers=0';
