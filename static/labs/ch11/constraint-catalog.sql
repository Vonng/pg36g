\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

SELECT
    constraint_catalog.conname AS constraint_name,
    constraint_catalog.contype AS constraint_type,
    constraint_catalog.convalidated,
    pg_catalog.pg_get_constraintdef(
        constraint_catalog.oid,
        true
    ) AS definition
FROM pg_catalog.pg_constraint AS constraint_catalog
WHERE constraint_catalog.conrelid =
      'shop_private.ch11_order'::regclass
  AND (
      constraint_catalog.conname IN (
          'ch11_order_shipping_pair_consistent',
          'ch11_order_shipping_code_nn'
      )
      OR (
          constraint_catalog.contype = 'n'
          AND constraint_catalog.conkey = ARRAY[
              (
                  SELECT attnum
                  FROM pg_catalog.pg_attribute
                  WHERE attrelid =
                        'shop_private.ch11_order'::regclass
                    AND attname = 'shipping_code'
                    AND attnum > 0
                    AND NOT attisdropped
              )
          ]::smallint[]
      )
  )
UNION ALL
SELECT
    'pg_attribute.shipping_code',
    'a',
    attribute_catalog.attnotnull,
    pg_catalog.format(
        'attnotnull=%s atthasmissing=%s',
        attribute_catalog.attnotnull,
        attribute_catalog.atthasmissing
    )
FROM pg_catalog.pg_attribute AS attribute_catalog
WHERE attribute_catalog.attrelid =
      'shop_private.ch11_order'::regclass
  AND attribute_catalog.attname = 'shipping_code'
  AND attribute_catalog.attnum > 0
  AND NOT attribute_catalog.attisdropped
ORDER BY constraint_name;
