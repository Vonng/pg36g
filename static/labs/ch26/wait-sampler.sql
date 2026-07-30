\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off

SELECT jsonb_build_object(
    'captured_at', clock_timestamp(),
    'sessions', coalesce(
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'state', state,
                    'wait_event_type', coalesce(wait_event_type, 'CPU'),
                    'wait_event', coalesce(wait_event, 'CPU'),
                    'count', session_count
                )
                ORDER BY state, wait_event_type, wait_event
            )
            FROM (
                SELECT
                    state,
                    wait_event_type,
                    wait_event,
                    count(*) AS session_count
                FROM pg_stat_activity
                WHERE datname = 'pg36_capacity'
                  AND application_name = :'bench_application'
                GROUP BY state, wait_event_type, wait_event
            ) AS grouped
        ),
        '[]'::jsonb
    )
);
\watch 0.25
