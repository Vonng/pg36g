\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

CREATE TABLE shop_private.ch11_default_probe (
    probe_id bigint PRIMARY KEY,
    payload text NOT NULL
);
ALTER TABLE shop_private.ch11_default_probe OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch11_default_probe IS
    'pg36 ch11 deterministic release lab; safe to rebuild';

INSERT INTO shop_private.ch11_default_probe (probe_id, payload)
SELECT
    probe_id,
    pg_catalog.repeat(pg_catalog.md5(probe_id::text), 4)
FROM pg_catalog.generate_series(1, 50000) AS seed(probe_id);

SELECT
    pg_catalog.pg_relation_filenode(
        'shop_private.ch11_default_probe'::regclass
    ) AS before_filenode,
    pg_catalog.pg_current_wal_insert_lsn() AS fast_lsn
\gset

ALTER TABLE shop_private.ch11_default_probe
    ADD COLUMN fast_flag integer NOT NULL DEFAULT 7;

SELECT
    pg_catalog.pg_relation_filenode(
        'shop_private.ch11_default_probe'::regclass
    ) AS fast_filenode,
    pg_catalog.pg_wal_lsn_diff(
        pg_catalog.pg_current_wal_insert_lsn(),
        :'fast_lsn'::pg_lsn
    )::bigint AS fast_wal_bytes,
    pg_catalog.pg_current_wal_insert_lsn() AS volatile_lsn,
    atthasmissing AS fast_has_missing,
    attmissingval::text AS fast_missing_value
FROM pg_catalog.pg_attribute
WHERE attrelid =
      'shop_private.ch11_default_probe'::regclass
  AND attname = 'fast_flag'
\gset

ALTER TABLE shop_private.ch11_default_probe
    ADD COLUMN volatile_stamp timestamptz
    NOT NULL DEFAULT pg_catalog.clock_timestamp();

SELECT
    pg_catalog.pg_relation_filenode(
        'shop_private.ch11_default_probe'::regclass
    ) AS volatile_filenode,
    pg_catalog.pg_wal_lsn_diff(
        pg_catalog.pg_current_wal_insert_lsn(),
        :'volatile_lsn'::pg_lsn
    )::bigint AS volatile_wal_bytes,
    atthasmissing AS volatile_has_missing
FROM pg_catalog.pg_attribute
WHERE attrelid =
      'shop_private.ch11_default_probe'::regclass
  AND attname = 'volatile_stamp'
\gset

CREATE TABLE shop_private.ch11_default_probe_result AS
SELECT
    :'before_filenode'::oid AS before_filenode,
    :'fast_filenode'::oid AS fast_filenode,
    :'volatile_filenode'::oid AS volatile_filenode,
    :'fast_has_missing'::boolean AS fast_has_missing,
    :'fast_missing_value'::text AS fast_missing_value,
    :'volatile_has_missing'::boolean AS volatile_has_missing,
    :'fast_wal_bytes'::bigint AS fast_wal_bytes,
    :'volatile_wal_bytes'::bigint AS volatile_wal_bytes,
    (SELECT count(*)
     FROM shop_private.ch11_default_probe) AS row_count;

ALTER TABLE shop_private.ch11_default_probe_result OWNER TO pg36_owner;
COMMENT ON TABLE shop_private.ch11_default_probe_result IS
    'pg36 ch11 deterministic release lab; safe to rebuild';

DO $assertions$
DECLARE
    result shop_private.ch11_default_probe_result%ROWTYPE;
BEGIN
    SELECT *
      INTO result
      FROM shop_private.ch11_default_probe_result;

    IF result.before_filenode IS DISTINCT FROM result.fast_filenode
       OR NOT result.fast_has_missing
       OR result.fast_missing_value <> '{7}' THEN
        RAISE EXCEPTION
            'constant default did not use the metadata fast path';
    END IF;

    IF result.fast_filenode = result.volatile_filenode
       OR result.volatile_has_missing
       OR result.volatile_wal_bytes <= result.fast_wal_bytes THEN
        RAISE EXCEPTION
            'volatile default did not show the expected rewrite relationship';
    END IF;
END
$assertions$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fast_path=same-filenode/atthasmissing:true';
SELECT 'volatile_path=new-filenode/atthasmissing:false';
SELECT 'rows=' || row_count
FROM shop_private.ch11_default_probe_result;
SELECT 'wal_bytes=fast:' || fast_wal_bytes ||
       '/volatile:' || volatile_wal_bytes
FROM shop_private.ch11_default_probe_result;
