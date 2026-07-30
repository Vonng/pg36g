\set ON_ERROR_STOP on
\pset pager off

SELECT
    current_database() = 'pg36_shop' AS database_ok,
    current_setting('server_version_num')::integer
        BETWEEN 180000 AND 189999 AS version_ok,
    session_user = 'postgres' AS admin_identity_ok,
    (
        SELECT role.rolsuper
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = session_user
    ) AS superuser_ok,
    pg_catalog.pg_has_role(
        session_user,
        'pg36_owner',
        'MEMBER'
    ) AS owner_membership_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'pg36_owner'
          AND NOT rolcanlogin
          AND NOT rolsuper
    ) AS owner_role_ok,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'pg36_app'
          AND rolcanlogin
          AND NOT rolsuper
    ) AS app_role_ok,
    EXISTS (
        SELECT 1
        FROM shop_private.schema_version
        WHERE version = 1
          AND description = 'ch04 reliable physical model'
    ) AS ch04_model_ok
\gset

\if :database_ok
\else
  \warn 'ch18 expected database pg36_shop'
  \quit 3
\endif

\if :version_ok
\else
  \warn 'ch18 formal fixture requires PostgreSQL 18.x'
  \quit 3
\endif

\if :admin_identity_ok
\else
  \warn 'ch18 formal fixture requires session_user postgres'
  \quit 3
\endif

\if :superuser_ok
\else
  \warn 'ch18 requires a superuser catalog-audit session'
  \quit 3
\endif

\if :owner_membership_ok
\else
  \warn 'ch18 session cannot inspect pg36_owner state'
  \quit 3
\endif

\if :owner_role_ok
\else
  \warn 'ch18 pg36_owner role contract drifted'
  \quit 3
\endif

\if :app_role_ok
\else
  \warn 'ch18 pg36_app role contract drifted'
  \quit 3
\endif

\if :ch04_model_ok
\else
  \warn 'ch18 requires the ch04-v1 physical model'
  \quit 3
\endif
