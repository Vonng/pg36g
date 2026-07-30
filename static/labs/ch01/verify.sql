\set ON_ERROR_STOP on
\pset pager off
\connect pg36_shop

DO $verify$
DECLARE
    actual_owner name;
    actual_schema_owner name;
BEGIN
    IF current_database() <> 'pg36_shop' THEN
        RAISE EXCEPTION 'expected database pg36_shop, got %', current_database();
    END IF;

    IF (
        SELECT count(*)
        FROM pg_catalog.pg_roles
        WHERE rolname IN ('pg36_owner', 'pg36_app', 'pg36_ro')
    ) <> 3 THEN
        RAISE EXCEPTION 'one or more pg36 roles are missing';
    END IF;

    SELECT pg_catalog.pg_get_userbyid(datdba)
    INTO actual_owner
    FROM pg_catalog.pg_database
    WHERE datname = 'pg36_shop';

    IF actual_owner <> 'pg36_owner' THEN
        RAISE EXCEPTION 'expected database owner pg36_owner, got %', actual_owner;
    END IF;

    SELECT pg_catalog.pg_get_userbyid(nspowner)
    INTO actual_schema_owner
    FROM pg_catalog.pg_namespace
    WHERE nspname = 'shop';

    IF actual_schema_owner <> 'pg36_owner' THEN
        RAISE EXCEPTION 'expected schema owner pg36_owner, got %', actual_schema_owner;
    END IF;

    IF NOT has_database_privilege('pg36_app', 'pg36_shop', 'CONNECT') THEN
        RAISE EXCEPTION 'pg36_app lacks CONNECT on pg36_shop';
    END IF;

    IF NOT has_schema_privilege('pg36_app', 'shop', 'USAGE') THEN
        RAISE EXCEPTION 'pg36_app lacks USAGE on schema shop';
    END IF;

    IF NOT has_schema_privilege('pg36_ro', 'shop', 'USAGE') THEN
        RAISE EXCEPTION 'pg36_ro lacks USAGE on schema shop';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_db_role_setting AS s
        JOIN pg_catalog.pg_roles AS r ON r.oid = s.setrole
        JOIN pg_catalog.pg_database AS d ON d.oid = s.setdatabase
        CROSS JOIN LATERAL unnest(s.setconfig) AS cfg(value)
        WHERE r.rolname IN ('pg36_app', 'pg36_ro')
          AND d.datname = 'pg36_shop'
          AND cfg.value = 'search_path=pg_catalog, shop'
        GROUP BY d.datname
        HAVING count(DISTINCT r.rolname) = 2
    ) THEN
        RAISE EXCEPTION 'database-specific search_path baseline is missing';
    END IF;
END
$verify$;

SELECT key || '=' || value AS state
FROM (
    SELECT 1 AS ord, 'status' AS key, 'ok' AS value
    UNION ALL
    SELECT 2, 'database', current_database()
    UNION ALL
    SELECT 3, 'database_oid', (
        SELECT oid::text
        FROM pg_catalog.pg_database
        WHERE datname = current_database()
    )
    UNION ALL
    SELECT 4, 'database_owner', (
        SELECT pg_catalog.pg_get_userbyid(datdba)
        FROM pg_catalog.pg_database
        WHERE datname = current_database()
    )
    UNION ALL
    SELECT 5, 'schema', 'shop'
    UNION ALL
    SELECT 6, 'schema_owner', (
        SELECT pg_catalog.pg_get_userbyid(nspowner)
        FROM pg_catalog.pg_namespace
        WHERE nspname = 'shop'
    )
    UNION ALL
    SELECT 7, 'server_version', current_setting('server_version')
    UNION ALL
    SELECT 8, 'in_recovery', pg_is_in_recovery()::text
) AS snapshot
ORDER BY ord;
