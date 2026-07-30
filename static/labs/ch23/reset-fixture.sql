\set ON_ERROR_STOP on

DO $reset_guard$
DECLARE
    schema_owner text;
    schema_comment text;
    role_name text;
    role_comment text;
    active_sessions integer;
BEGIN
    SELECT pg_catalog.pg_get_userbyid(nspowner),
           pg_catalog.obj_description(oid, 'pg_namespace')
      INTO schema_owner, schema_comment
      FROM pg_catalog.pg_namespace
     WHERE nspname = 'pg36_ch23';

    IF NOT FOUND
       OR schema_owner <> 'pg36_ch23_owner'
       OR schema_comment IS DISTINCT FROM
          'pg36 chapter 23 security lab; synthetic two-tenant data only'
    THEN
        RAISE EXCEPTION
            'reset guard rejected schema owner %, comment %',
            schema_owner,
            schema_comment;
    END IF;

    FOREACH role_name IN ARRAY ARRAY[
        'pg36_ch23_owner',
        'pg36_ch23_runtime',
        'pg36_ch23_readonly',
        'pg36_ch23_migrate',
        'pg36_ch23_rotate'
    ]
    LOOP
        SELECT pg_catalog.shobj_description(oid, 'pg_authid')
          INTO role_comment
          FROM pg_catalog.pg_roles
         WHERE rolname = role_name;

        IF NOT FOUND
           OR role_comment NOT LIKE
              'pg36 chapter 23 security lab:%synthetic fixture only'
        THEN
            RAISE EXCEPTION
                'reset guard rejected role %, comment %',
                role_name,
                role_comment;
        END IF;
    END LOOP;

    SELECT count(*)
      INTO active_sessions
      FROM pg_catalog.pg_stat_activity
     WHERE usename = ANY (ARRAY[
         'pg36_ch23_owner',
         'pg36_ch23_runtime',
         'pg36_ch23_readonly',
         'pg36_ch23_migrate',
         'pg36_ch23_rotate'
     ])
       AND pid <> pg_catalog.pg_backend_pid();

    IF active_sessions <> 0 THEN
        RAISE EXCEPTION
            'reset guard found % active synthetic-role sessions',
            active_sessions;
    END IF;
END
$reset_guard$;

ALTER ROLE pg36_ch23_rotate NOLOGIN PASSWORD NULL;

ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    REVOKE SELECT, INSERT, UPDATE ON TABLES
    FROM pg36_ch23_runtime;
ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    REVOKE SELECT ON TABLES
    FROM pg36_ch23_readonly;
ALTER DEFAULT PRIVILEGES
    FOR ROLE pg36_ch23_owner
    IN SCHEMA pg36_ch23
    REVOKE EXECUTE ON FUNCTIONS
    FROM pg36_ch23_runtime,
         pg36_ch23_readonly;

REVOKE pg36_ch23_runtime, pg36_ch23_readonly FROM test;
REVOKE pg36_ch23_owner FROM pg36_ch23_migrate;
REVOKE dbrole_readonly FROM pg36_ch23_rotate;

DROP SCHEMA pg36_ch23 CASCADE;

DROP ROLE pg36_ch23_rotate;
DROP ROLE pg36_ch23_migrate;
DROP ROLE pg36_ch23_readonly;
DROP ROLE pg36_ch23_runtime;
DROP ROLE pg36_ch23_owner;
