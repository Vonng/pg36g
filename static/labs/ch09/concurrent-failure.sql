\set ON_ERROR_STOP on
\ir plan-context.sql

CREATE UNIQUE INDEX CONCURRENTLY
    ch09_unique_probe_external_ref_uidx
ON shop_private.ch09_unique_probe (external_ref);
