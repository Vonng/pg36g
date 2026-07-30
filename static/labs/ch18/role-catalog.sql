\set ON_ERROR_STOP on
\pset pager off
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
\ir context.sql

SELECT
    role.rolname AS role_name,
    role.rolcanlogin AS can_login,
    role.rolsuper AS is_superuser,
    role.rolcreaterole AS can_create_role,
    role.rolcreatedb AS can_create_database,
    role.rolreplication AS can_replicate,
    role.rolbypassrls AS bypass_rls,
    role.rolconnlimit AS connection_limit
FROM pg_catalog.pg_roles AS role
WHERE role.rolname IN (
    'pg36_app',
    'pg36_owner',
    'postgres'
)
ORDER BY role.rolname;

COMMIT;
