\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $precheck$
BEGIN
    IF (
        SELECT phase
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM 'migrated' THEN
        RAISE EXCEPTION 'validation requires migrated phase';
    END IF;

    IF EXISTS (
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
        RAISE EXCEPTION
            'validation precheck found null or mismatched codes';
    END IF;
END
$precheck$;

ALTER TABLE shop_private.ch11_order
    VALIDATE CONSTRAINT ch11_order_shipping_pair_consistent;

ALTER TABLE shop_private.ch11_order
    ADD CONSTRAINT ch11_order_shipping_code_nn
    CHECK (shipping_code IS NOT NULL)
    NOT VALID;

ALTER TABLE shop_private.ch11_order
    VALIDATE CONSTRAINT ch11_order_shipping_code_nn;

SELECT
    pg_catalog.pg_relation_filenode(
        'shop_private.ch11_order'::regclass
    ) AS filenode_before_not_null
\gset

ALTER TABLE shop_private.ch11_order
    ALTER COLUMN shipping_code SET NOT NULL;

SELECT
    pg_catalog.pg_relation_filenode(
        'shop_private.ch11_order'::regclass
    ) AS filenode_after_not_null
\gset

SELECT
    :'filenode_before_not_null' =
    :'filenode_after_not_null' AS filenode_same
\gset

\if :filenode_same
\else
  DO $filenode_error$
  BEGIN
      RAISE EXCEPTION
          'SET NOT NULL unexpectedly changed the relation filenode';
  END
  $filenode_error$;
\endif

DO $postcheck$
BEGIN
    IF NOT (
        SELECT attnotnull
        FROM pg_catalog.pg_attribute
        WHERE attrelid =
              'shop_private.ch11_order'::regclass
          AND attname = 'shipping_code'
          AND attnum > 0
          AND NOT attisdropped
    ) THEN
        RAISE EXCEPTION 'shipping_code is not marked NOT NULL';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid =
              'shop_private.ch11_order'::regclass
          AND conname IN (
              'ch11_order_shipping_pair_consistent',
              'ch11_order_shipping_code_nn'
          )
          AND NOT convalidated
    ) THEN
        RAISE EXCEPTION 'a staged shipping constraint is not valid';
    END IF;
END
$postcheck$;

UPDATE shop_private.ch11_migration_state
   SET phase = 'validated',
       validated_at = pg_catalog.clock_timestamp(),
       updated_at = pg_catalog.clock_timestamp()
 WHERE migration_id = 'shipping-code-v1';

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'phase=validated';
SELECT 'constraints=pair:true/nn-check:true/attnotnull:true';
SELECT 'set-not-null-filenode=' ||
       :'filenode_before_not_null' || '->' ||
       :'filenode_after_not_null';
SELECT 'not-null-catalog=' ||
       CASE
           WHEN current_setting('server_version_num')::integer >= 180000
           THEN 'pg18-pg_constraint+pg_attribute'
           ELSE 'pg14-17-pg_attribute'
       END;
