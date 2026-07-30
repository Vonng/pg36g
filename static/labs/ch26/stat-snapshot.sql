\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

SET statement_timeout = '5s';
SET lock_timeout = '500ms';
SET default_transaction_read_only = on;

SELECT jsonb_build_object(
    'captured_at', clock_timestamp(),
    'identity', jsonb_build_object(
        'database', current_database(),
        'user', current_user,
        'cluster_name', current_setting('cluster_name'),
        'server_version', current_setting('server_version'),
        'in_recovery', pg_is_in_recovery(),
        'synchronous_commit', current_setting('synchronous_commit'),
        'track_io_timing', current_setting('track_io_timing'),
        'track_wal_io_timing', current_setting('track_wal_io_timing'),
        'stats_fetch_consistency', current_setting('stats_fetch_consistency')
    ),
    'database', (
        SELECT to_jsonb(d)
            - 'datid'
            - 'datname'
            - 'numbackends'
            - 'checksum_last_failure'
        FROM pg_stat_database AS d
        WHERE datname = current_database()
    ),
    'wal', (
        SELECT to_jsonb(w)
        FROM pg_stat_wal AS w
    ),
    'checkpointer', (
        SELECT to_jsonb(c)
        FROM pg_stat_checkpointer AS c
    ),
    'bgwriter', (
        SELECT to_jsonb(b)
        FROM pg_stat_bgwriter AS b
    ),
    'io', (
        SELECT jsonb_agg(
            to_jsonb(i)
            ORDER BY backend_type, object, context
        )
        FROM pg_stat_io AS i
    ),
    'tables', (
        SELECT jsonb_agg(
            jsonb_build_object(
                'relation', relname,
                'seq_scan', seq_scan,
                'idx_scan', idx_scan,
                'n_tup_ins', n_tup_ins,
                'n_tup_upd', n_tup_upd,
                'n_tup_del', n_tup_del,
                'n_live_tup', n_live_tup,
                'n_dead_tup', n_dead_tup,
                'total_bytes', pg_total_relation_size(relid)
            )
            ORDER BY relname
        )
        FROM pg_stat_user_tables
        WHERE schemaname = 'shopbench'
    ),
    'relations', (
        SELECT jsonb_build_object(
            'database_bytes', pg_database_size(current_database()),
            'schema_bytes', coalesce(sum(pg_total_relation_size(c.oid)), 0),
            'live_order_rows', (
                SELECT count(*) FROM shopbench.order_live
            )
        )
        FROM pg_class AS c
        JOIN pg_namespace AS n
          ON n.oid = c.relnamespace
        WHERE n.nspname = 'shopbench'
          AND c.relkind IN ('r', 'p', 'm')
    ),
    'statements', (
        SELECT jsonb_build_object(
            'query_text_exported', false,
            'rows', coalesce(
                jsonb_agg(
                    jsonb_build_object(
                        'queryid', queryid,
                        'calls', calls,
                        'total_exec_time', total_exec_time,
                        'rows', rows,
                        'shared_blks_hit', shared_blks_hit,
                        'shared_blks_read', shared_blks_read,
                        'shared_blks_dirtied', shared_blks_dirtied,
                        'shared_blks_written', shared_blks_written,
                        'temp_blks_read', temp_blks_read,
                        'temp_blks_written', temp_blks_written,
                        'wal_records', wal_records,
                        'wal_fpi', wal_fpi,
                        'wal_bytes', wal_bytes,
                        'stats_since', stats_since
                    )
                    ORDER BY queryid
                ),
                '[]'::jsonb
            )
        )
        FROM monitor.pg_stat_statements
        WHERE dbid = (
            SELECT oid
            FROM pg_database
            WHERE datname = current_database()
        )
          AND userid = (
            SELECT oid
            FROM pg_roles
            WHERE rolname = 'dbuser_pg36bench'
        )
    )
);
