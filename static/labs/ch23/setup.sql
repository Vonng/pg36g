\set ON_ERROR_STOP on

DO $role_setup$
DECLARE
    role_name text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'test'
    ) THEN
        RAISE EXCEPTION 'predeclared sandbox login test is absent';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'test'
          AND (
              NOT rolcanlogin
              OR rolsuper
              OR rolcreaterole
              OR rolcreatedb
              OR rolreplication
              OR rolbypassrls
          )
    ) THEN
        RAISE EXCEPTION
            'predeclared sandbox login test has unsafe attributes';
    END IF;

    FOREACH role_name IN ARRAY ARRAY[
        'pg36_ch23_owner',
        'pg36_ch23_runtime',
        'pg36_ch23_readonly',
        'pg36_ch23_migrate',
        'pg36_ch23_rotate'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles
            WHERE rolname = role_name
        ) THEN
            EXECUTE pg_catalog.format(
                'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB ' ||
                'NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
                role_name
            );
        END IF;
    END LOOP;
END
$role_setup$;

COMMENT ON ROLE pg36_ch23_owner IS
    'pg36 chapter 23 security lab: object owner; synthetic fixture only';
COMMENT ON ROLE pg36_ch23_runtime IS
    'pg36 chapter 23 security lab: application runtime; synthetic fixture only';
COMMENT ON ROLE pg36_ch23_readonly IS
    'pg36 chapter 23 security lab: read-only workload; synthetic fixture only';
COMMENT ON ROLE pg36_ch23_migrate IS
    'pg36 chapter 23 security lab: migration authority; synthetic fixture only';
COMMENT ON ROLE pg36_ch23_rotate IS
    'pg36 chapter 23 security lab: direct-only rotation probe; synthetic fixture only';

DO $role_contract$
DECLARE
    bad_roles text[];
BEGIN
    SELECT pg_catalog.array_agg(rolname ORDER BY rolname)
      INTO bad_roles
      FROM pg_catalog.pg_roles
     WHERE rolname = ANY (ARRAY[
               'pg36_ch23_owner',
               'pg36_ch23_runtime',
               'pg36_ch23_readonly',
               'pg36_ch23_migrate',
               'pg36_ch23_rotate'
           ])
       AND (
           rolcanlogin
           OR rolsuper
           OR rolcreatedb
           OR rolcreaterole
           OR rolreplication
           OR rolbypassrls
       );

    IF bad_roles IS NOT NULL THEN
        RAISE EXCEPTION
            'synthetic roles have unsafe attributes: %',
            bad_roles;
    END IF;

    IF (
        SELECT count(*)
        FROM pg_catalog.pg_roles
        WHERE rolname = ANY (ARRAY[
            'pg36_ch23_owner',
            'pg36_ch23_runtime',
            'pg36_ch23_readonly',
            'pg36_ch23_migrate',
            'pg36_ch23_rotate'
        ])
    ) <> 5 THEN
        RAISE EXCEPTION 'synthetic role set is incomplete';
    END IF;
END
$role_contract$;

ALTER ROLE pg36_ch23_rotate NOLOGIN PASSWORD NULL;

GRANT pg36_ch23_runtime, pg36_ch23_readonly
   TO test
 WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

GRANT pg36_ch23_owner
   TO pg36_ch23_migrate
 WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

GRANT dbrole_readonly
   TO pg36_ch23_rotate
 WITH ADMIN FALSE, INHERIT FALSE, SET FALSE;

DO $schema_guard$
DECLARE
    existing_owner text;
    existing_comment text;
BEGIN
    SELECT pg_catalog.pg_get_userbyid(nspowner),
           pg_catalog.obj_description(oid, 'pg_namespace')
      INTO existing_owner, existing_comment
      FROM pg_catalog.pg_namespace
     WHERE nspname = 'pg36_ch23';

    IF FOUND AND (
        existing_owner <> 'pg36_ch23_owner'
        OR existing_comment IS DISTINCT FROM
           'pg36 chapter 23 security lab; synthetic two-tenant data only'
    ) THEN
        RAISE EXCEPTION
            'refusing existing pg36_ch23 schema owned by %, comment %',
            existing_owner,
            existing_comment;
    END IF;
END
$schema_guard$;

CREATE SCHEMA IF NOT EXISTS pg36_ch23
    AUTHORIZATION pg36_ch23_owner;

COMMENT ON SCHEMA pg36_ch23 IS
    'pg36 chapter 23 security lab; synthetic two-tenant data only';

SET ROLE pg36_ch23_owner;

CREATE TABLE IF NOT EXISTS pg36_ch23.account (
    tenant_id       uuid        NOT NULL,
    account_id      uuid        NOT NULL,
    display_name    text        NOT NULL,
    balance_cents   bigint      NOT NULL
        CHECK (balance_cents >= 0),
    secret_note     text        NOT NULL,
    created_at      timestamptz NOT NULL
        DEFAULT pg_catalog.clock_timestamp(),
    PRIMARY KEY (tenant_id, account_id)
);

COMMENT ON TABLE pg36_ch23.account IS
    'synthetic two-tenant account rows for the chapter 23 RLS lab';

CREATE OR REPLACE FUNCTION pg36_ch23.current_tenant()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = pg_catalog
RETURN NULLIF(
    pg_catalog.current_setting('app.tenant_id', true),
    ''
)::uuid;

COMMENT ON FUNCTION pg36_ch23.current_tenant() IS
    'fail-closed transaction tenant context for the chapter 23 lab';

RESET ROLE;

INSERT INTO pg36_ch23.account (
    tenant_id,
    account_id,
    display_name,
    balance_cents,
    secret_note
)
VALUES
    (
        '11111111-1111-4111-8111-111111111111',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
        'tenant-a-checking',
        120000,
        'synthetic tenant A note 1'
    ),
    (
        '11111111-1111-4111-8111-111111111111',
        'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2',
        'tenant-a-savings',
        880000,
        'synthetic tenant A note 2'
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
        'tenant-b-checking',
        240000,
        'synthetic tenant B note 1'
    ),
    (
        '22222222-2222-4222-8222-222222222222',
        'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
        'tenant-b-savings',
        760000,
        'synthetic tenant B note 2'
    )
ON CONFLICT (tenant_id, account_id) DO NOTHING;

DO $table_contract$
DECLARE
    observed_columns text[];
    observed_constraints text[];
    unexpected_rows bigint;
BEGIN
    SELECT pg_catalog.array_agg(
               attname::text || ':' ||
               pg_catalog.format_type(atttypid, atttypmod) || ':' ||
               attnotnull::text
               ORDER BY attnum
           )
      INTO observed_columns
      FROM pg_catalog.pg_attribute
     WHERE attrelid = 'pg36_ch23.account'::pg_catalog.regclass
       AND attnum > 0
       AND NOT attisdropped;

    IF observed_columns <> ARRAY[
        'tenant_id:uuid:true',
        'account_id:uuid:true',
        'display_name:text:true',
        'balance_cents:bigint:true',
        'secret_note:text:true',
        'created_at:timestamp with time zone:true'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch23.account column contract drifted: %',
            observed_columns;
    END IF;

    SELECT pg_catalog.array_agg(
               pg_catalog.pg_get_constraintdef(oid, true)
               ORDER BY contype, conname
           )
      INTO observed_constraints
      FROM pg_catalog.pg_constraint
     WHERE conrelid = 'pg36_ch23.account'::pg_catalog.regclass
       AND contype IN ('c', 'p');

    IF observed_constraints <> ARRAY[
        'CHECK (balance_cents >= 0)',
        'PRIMARY KEY (tenant_id, account_id)'
    ]::text[] THEN
        RAISE EXCEPTION
            'pg36_ch23.account constraint contract drifted: %',
            observed_constraints;
    END IF;

    SELECT count(*)
      INTO unexpected_rows
      FROM pg36_ch23.account
     WHERE (tenant_id, account_id) NOT IN (
         (
             '11111111-1111-4111-8111-111111111111'::uuid,
             'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'::uuid
         ),
         (
             '11111111-1111-4111-8111-111111111111'::uuid,
             'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'::uuid
         ),
         (
             '22222222-2222-4222-8222-222222222222'::uuid,
             'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1'::uuid
         ),
         (
             '22222222-2222-4222-8222-222222222222'::uuid,
             'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2'::uuid
         )
     );

    IF unexpected_rows <> 0 OR (
        SELECT count(*) FROM pg36_ch23.account
    ) <> 4 THEN
        RAISE EXCEPTION
            'synthetic fixture contains unexpected rows';
    END IF;
END
$table_contract$;

DROP POLICY IF EXISTS account_runtime_select
    ON pg36_ch23.account;
DROP POLICY IF EXISTS account_readonly_select
    ON pg36_ch23.account;
DROP POLICY IF EXISTS account_runtime_insert
    ON pg36_ch23.account;
DROP POLICY IF EXISTS account_runtime_update
    ON pg36_ch23.account;
DROP POLICY IF EXISTS account_owner_all
    ON pg36_ch23.account;

CREATE POLICY account_runtime_select
    ON pg36_ch23.account
    FOR SELECT
    TO pg36_ch23_runtime
    USING (
        tenant_id = pg36_ch23.current_tenant()
    );

CREATE POLICY account_readonly_select
    ON pg36_ch23.account
    FOR SELECT
    TO pg36_ch23_readonly
    USING (
        tenant_id = pg36_ch23.current_tenant()
    );

CREATE POLICY account_runtime_insert
    ON pg36_ch23.account
    FOR INSERT
    TO pg36_ch23_runtime
    WITH CHECK (
        tenant_id = pg36_ch23.current_tenant()
    );

CREATE POLICY account_runtime_update
    ON pg36_ch23.account
    FOR UPDATE
    TO pg36_ch23_runtime
    USING (
        tenant_id = pg36_ch23.current_tenant()
    )
    WITH CHECK (
        tenant_id = pg36_ch23.current_tenant()
    );

CREATE POLICY account_owner_all
    ON pg36_ch23.account
    FOR ALL
    TO pg36_ch23_owner
    USING (
        tenant_id = pg36_ch23.current_tenant()
    )
    WITH CHECK (
        tenant_id = pg36_ch23.current_tenant()
    );

ALTER TABLE pg36_ch23.account
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pg36_ch23.account
    FORCE ROW LEVEL SECURITY;

RESET ROLE;

REVOKE ALL ON SCHEMA pg36_ch23
   FROM PUBLIC,
        test,
        dbrole_readonly,
        dbrole_readwrite,
        dbrole_admin,
        dbrole_offline,
        pg36_ch23_runtime,
        pg36_ch23_readonly,
        pg36_ch23_migrate;

REVOKE ALL ON TABLE pg36_ch23.account
   FROM PUBLIC,
        test,
        dbrole_readonly,
        dbrole_readwrite,
        dbrole_admin,
        dbrole_offline,
        pg36_ch23_runtime,
        pg36_ch23_readonly,
        pg36_ch23_migrate;

REVOKE ALL ON FUNCTION pg36_ch23.current_tenant()
   FROM PUBLIC,
        test,
        dbrole_readonly,
        dbrole_readwrite,
        dbrole_admin,
        dbrole_offline,
        pg36_ch23_runtime,
        pg36_ch23_readonly,
        pg36_ch23_migrate;

GRANT USAGE ON SCHEMA pg36_ch23
   TO pg36_ch23_runtime,
      pg36_ch23_readonly;

GRANT SELECT, INSERT, UPDATE ON TABLE pg36_ch23.account
   TO pg36_ch23_runtime;

GRANT SELECT ON TABLE pg36_ch23.account
   TO pg36_ch23_readonly;

GRANT EXECUTE ON FUNCTION pg36_ch23.current_tenant()
   TO pg36_ch23_runtime,
      pg36_ch23_readonly;

ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    GRANT SELECT, INSERT, UPDATE ON TABLES
    TO pg36_ch23_runtime;
ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    GRANT SELECT ON TABLES
    TO pg36_ch23_readonly;

ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    GRANT EXECUTE ON FUNCTIONS
    TO pg36_ch23_runtime,
       pg36_ch23_readonly;
