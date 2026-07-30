\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS pg36_ch20 AUTHORIZATION CURRENT_USER;

CREATE TABLE IF NOT EXISTS pg36_ch20.write_probe (
    run_id text NOT NULL,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    token text NOT NULL,
    client_sent_at timestamptz NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, attempt_no),
    UNIQUE (token)
);

DO $fixture_contract$
DECLARE
    observed_columns text[];
    observed_constraints text[];
BEGIN
    IF pg_catalog.pg_get_userbyid(
        (
            SELECT nspowner
            FROM pg_catalog.pg_namespace
            WHERE nspname = 'pg36_ch20'
        )
    ) <> current_user THEN
        RAISE EXCEPTION
            'pg36_ch20 schema is not owned by the sandbox probe user';
    END IF;

    SELECT pg_catalog.array_agg(
               attname::text || ':' ||
               pg_catalog.format_type(atttypid, atttypmod) || ':' ||
               attnotnull::text
               ORDER BY attnum
           )
    INTO observed_columns
    FROM pg_catalog.pg_attribute
    WHERE attrelid = 'pg36_ch20.write_probe'::regclass
      AND attnum > 0
      AND NOT attisdropped;

    IF observed_columns <> ARRAY[
        'run_id:text:true',
        'attempt_no:integer:true',
        'token:text:true',
        'client_sent_at:timestamp with time zone:true',
        'committed_at:timestamp with time zone:true'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch20.write_probe column contract drifted: %',
            observed_columns;
    END IF;

    SELECT pg_catalog.array_agg(
               pg_catalog.pg_get_constraintdef(oid, true)
               ORDER BY contype, conname
           )
    INTO observed_constraints
    FROM pg_catalog.pg_constraint
    WHERE conrelid = 'pg36_ch20.write_probe'::regclass
      AND contype IN ('p', 'u');

    IF observed_constraints <> ARRAY[
        'PRIMARY KEY (run_id, attempt_no)',
        'UNIQUE (token)'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch20.write_probe key contract drifted: %',
            observed_constraints;
    END IF;
END
$fixture_contract$;

COMMENT ON SCHEMA pg36_ch20 IS
    'pg36 chapter 20 planned-switchover lab; synthetic data only';

COMMENT ON TABLE pg36_ch20.write_probe IS
    'idempotency and commit-outcome evidence for the chapter 20 sandbox drill';
