\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned

WITH control AS (
    SELECT system_identifier::text
    FROM pg_catalog.pg_control_system()
),
checkpoint AS (
    SELECT timeline_id
    FROM pg_catalog.pg_control_checkpoint()
),
senders AS (
    SELECT COALESCE(
        pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'application_name', application_name,
                'client_addr', host(client_addr),
                'state', state,
                'sync_state', sync_state,
                'sent_lsn', sent_lsn::text,
                'write_lsn', write_lsn::text,
                'flush_lsn', flush_lsn::text,
                'replay_lsn', replay_lsn::text,
                'replay_gap_bytes',
                    CASE
                        WHEN replay_lsn IS NULL THEN NULL
                        ELSE pg_catalog.pg_wal_lsn_diff(
                            pg_catalog.pg_current_wal_lsn(),
                            replay_lsn
                        )
                    END
            )
            ORDER BY application_name
        ),
        '[]'::pg_catalog.jsonb
    ) AS rows
    FROM pg_catalog.pg_stat_replication
),
slots AS (
    SELECT COALESCE(
        pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'slot_name', slot_name,
                'slot_type', slot_type,
                'active', active,
                'restart_lsn', restart_lsn::text,
                'wal_status', wal_status,
                'safe_wal_size', safe_wal_size
            )
            ORDER BY slot_name
        ),
        '[]'::pg_catalog.jsonb
    ) AS rows
    FROM pg_catalog.pg_replication_slots
),
receiver AS (
    SELECT COALESCE(
        pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'status', status,
                'sender_host', sender_host,
                'sender_port', sender_port,
                'written_lsn', written_lsn::text,
                'flushed_lsn', flushed_lsn::text,
                'latest_end_lsn', latest_end_lsn::text
            )
        ),
        '[]'::pg_catalog.jsonb
    ) AS rows
    FROM pg_catalog.pg_stat_wal_receiver
),
archiver AS (
    SELECT pg_catalog.jsonb_build_object(
        'archived_count', archived_count,
        'last_archived_wal', last_archived_wal,
        'last_archived_time', last_archived_time,
        'failed_count', failed_count,
        'last_failed_wal', last_failed_wal,
        'last_failed_time', last_failed_time
    ) AS row
    FROM pg_catalog.pg_stat_archiver
)
SELECT pg_catalog.jsonb_pretty(
    pg_catalog.jsonb_build_object(
        'schema', 'pg36-ch20-postgresql-ha-facts-v1',
        'cluster_name', current_setting('cluster_name'),
        'server_version_num',
            current_setting('server_version_num')::integer,
        'in_recovery', pg_catalog.pg_is_in_recovery(),
        'system_identifier', control.system_identifier,
        'checkpoint_timeline_id', checkpoint.timeline_id,
        'current_wal_timeline_id',
            CASE
                WHEN pg_catalog.pg_is_in_recovery() THEN NULL
                ELSE (
                    SELECT split.timeline_id
                    FROM pg_catalog.pg_split_walfile_name(
                        pg_catalog.pg_walfile_name(
                            pg_catalog.pg_current_wal_lsn()
                        )
                    ) AS split
                )
            END,
        'current_wal_lsn',
            CASE
                WHEN pg_catalog.pg_is_in_recovery() THEN NULL
                ELSE pg_catalog.pg_current_wal_lsn()::text
            END,
        'last_wal_receive_lsn',
            pg_catalog.pg_last_wal_receive_lsn()::text,
        'last_wal_replay_lsn',
            pg_catalog.pg_last_wal_replay_lsn()::text,
        'settings', pg_catalog.jsonb_build_object(
            'synchronous_commit',
                current_setting('synchronous_commit'),
            'synchronous_standby_names',
                current_setting('synchronous_standby_names'),
            'wal_log_hints',
                current_setting('wal_log_hints'),
            'full_page_writes',
                current_setting('full_page_writes'),
            'archive_mode',
                current_setting('archive_mode')
        ),
        'senders', senders.rows,
        'slots', slots.rows,
        'receivers', receiver.rows,
        'archiver', archiver.row
    )
)
FROM control
CROSS JOIN checkpoint
CROSS JOIN senders
CROSS JOIN slots
CROSS JOIN receiver
CROSS JOIN archiver;
