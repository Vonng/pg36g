\set ON_ERROR_STOP on

DO $fixture_guard$
DECLARE
    existing_owner text;
    existing_comment text;
BEGIN
    SELECT pg_catalog.pg_get_userbyid(nspowner),
           pg_catalog.obj_description(oid, 'pg_namespace')
      INTO existing_owner, existing_comment
      FROM pg_catalog.pg_namespace
     WHERE nspname = 'pg36_ch22';

    IF FOUND AND (
        existing_owner <> 'postgres'
        OR existing_comment IS DISTINCT FROM
           'pg36 chapter 22 service-routing lab; synthetic data only'
    ) THEN
        RAISE EXCEPTION
            'refusing to commandeer existing pg36_ch22 schema owned by %, comment %',
            existing_owner, existing_comment;
    END IF;
END
$fixture_guard$;

CREATE SCHEMA IF NOT EXISTS pg36_ch22 AUTHORIZATION postgres;

COMMENT ON SCHEMA pg36_ch22 IS
    'pg36 chapter 22 service-routing lab; synthetic data only';

CREATE TABLE IF NOT EXISTS pg36_ch22.route_probe (
    run_id       uuid        NOT NULL,
    worker_no    integer     NOT NULL CHECK (worker_no >= 0),
    attempt_no   integer     NOT NULL CHECK (attempt_no > 0),
    token        text        NOT NULL UNIQUE,
    client_sent_at timestamptz NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, worker_no, attempt_no)
);

DO $table_contract$
DECLARE
    observed_columns text[];
    observed_keys text[];
BEGIN
    SELECT pg_catalog.array_agg(
               attname::text || ':' ||
               pg_catalog.format_type(atttypid, atttypmod) || ':' ||
               attnotnull::text
               ORDER BY attnum
           )
      INTO observed_columns
      FROM pg_catalog.pg_attribute
     WHERE attrelid = 'pg36_ch22.route_probe'::regclass
       AND attnum > 0
       AND NOT attisdropped;

    IF observed_columns <> ARRAY[
        'run_id:uuid:true',
        'worker_no:integer:true',
        'attempt_no:integer:true',
        'token:text:true',
        'client_sent_at:timestamp with time zone:true',
        'committed_at:timestamp with time zone:true'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch22.route_probe column contract drifted: %',
            observed_columns;
    END IF;

    SELECT pg_catalog.array_agg(
               pg_catalog.pg_get_constraintdef(oid, true)
               ORDER BY contype, conname
           )
      INTO observed_keys
      FROM pg_catalog.pg_constraint
     WHERE conrelid = 'pg36_ch22.route_probe'::regclass
       AND contype IN ('p', 'u');

    IF observed_keys <> ARRAY[
        'PRIMARY KEY (run_id, worker_no, attempt_no)',
        'UNIQUE (token)'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch22.route_probe key contract drifted: %',
            observed_keys;
    END IF;
END
$table_contract$;

COMMENT ON TABLE pg36_ch22.route_probe IS
    'idempotency, routing, visibility, and switchover evidence for chapter 22';

REVOKE ALL ON SCHEMA pg36_ch22 FROM PUBLIC;
REVOKE ALL ON TABLE pg36_ch22.route_probe FROM PUBLIC;

GRANT USAGE ON SCHEMA pg36_ch22 TO test;
GRANT SELECT, INSERT ON pg36_ch22.route_probe TO test;
