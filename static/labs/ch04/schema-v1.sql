\set ON_ERROR_STOP on
\ir context.sql

SELECT pg_catalog.to_regclass('shop_private.schema_version') IS NOT NULL
       AS version_table_exists
\gset

\if :version_table_exists
  SELECT EXISTS (
             SELECT 1
             FROM shop_private.schema_version
             WHERE version = 1
         ) AS already_v1
  \gset
\else
  \set already_v1 false
\endif

\if :already_v1
  \echo '[schema] ch04 physical model v1 is already installed'
\else
  SELECT (
             SELECT count(*)
             FROM unnest(
                 ARRAY[
                     'shop.customer',
                     'shop.product',
                     'shop.sales_order',
                     'shop.sales_order_item',
                     'shop.payment'
                 ]
             ) AS required(relation_name)
             WHERE pg_catalog.to_regclass(relation_name)
                   IS NOT NULL
         ) = 5 AS complete_v0_relation_set
  \gset

  \if :complete_v0_relation_set
    \echo '[schema] complete ch03 relation set found; migrating it'
  \else
    \echo '[schema] installing the empty ch03 v0 prerequisite'
    \ir ../ch03/setup.sql
  \endif

  \ir migrate-v0-to-v1.sql
\endif
