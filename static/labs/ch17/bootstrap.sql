\set ON_ERROR_STOP on
\pset pager off

SELECT current_database() = 'postgres' AS database_ok
\gset

\if :database_ok
\else
  DO $context_error$
  BEGIN
      RAISE EXCEPTION
          'ch17 bootstrap must use the postgres maintenance database';
  END
  $context_error$;
\endif

DO $database_collision_guard$
DECLARE
    shard record;
BEGIN
    FOR shard IN
        SELECT *
        FROM (
            VALUES
                (
                    'pg36_shard_a'::text,
                    'pg36 ch17 fdw shard database a; retained shell'
                        ::text
                ),
                (
                    'pg36_shard_b'::text,
                    'pg36 ch17 fdw shard database b; retained shell'
                        ::text
                )
        ) AS expected(database_name, marker)
    LOOP
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_database AS database_catalog
            WHERE database_catalog.datname = shard.database_name
              AND (
                  pg_catalog.pg_get_userbyid(
                      database_catalog.datdba
                  ) <> 'pg36_owner'
                  OR pg_catalog.shobj_description(
                         database_catalog.oid,
                         'pg_database'
                     ) IS DISTINCT FROM shard.marker
                  OR database_catalog.datistemplate
                  OR NOT database_catalog.datallowconn
              )
        ) THEN
            RAISE EXCEPTION
                'refusing collision: database % identity drifted',
                shard.database_name;
        END IF;
    END LOOP;
END
$database_collision_guard$;

SELECT pg_catalog.format(
           'CREATE DATABASE %I WITH OWNER %I TEMPLATE template0 ENCODING %L',
           expected.database_name,
           'pg36_owner',
           'UTF8'
       )
FROM (
    VALUES
        ('pg36_shard_a'::text),
        ('pg36_shard_b'::text)
) AS expected(database_name)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_database AS database_catalog
    WHERE database_catalog.datname = expected.database_name
)
\gexec

COMMENT ON DATABASE pg36_shard_a IS
    'pg36 ch17 fdw shard database a; retained shell';
COMMENT ON DATABASE pg36_shard_b IS
    'pg36 ch17 fdw shard database b; retained shell';

REVOKE CONNECT ON DATABASE pg36_shard_a FROM PUBLIC;
REVOKE CONNECT ON DATABASE pg36_shard_b FROM PUBLIC;
GRANT CONNECT ON DATABASE pg36_shard_a
    TO pg36_owner, pg36_app;
GRANT CONNECT ON DATABASE pg36_shard_b
    TO pg36_owner, pg36_app;

\pset format unaligned
\pset tuples_only on
SELECT 'status=bootstrap-ready';
SELECT 'shard_databases=' ||
       pg_catalog.string_agg(
           datname,
           ',' ORDER BY datname
       )
FROM pg_catalog.pg_database
WHERE datname IN ('pg36_shard_a', 'pg36_shard_b');
