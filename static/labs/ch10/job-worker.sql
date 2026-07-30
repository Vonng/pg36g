\set ON_ERROR_STOP on
\ir context.sql

\if :{?worker}
\else
  \set worker unknown
\endif
\if :{?gate}
\else
  \set gate 0
\endif

BEGIN ISOLATION LEVEL READ COMMITTED;

WITH picked AS (
    SELECT job_id
    FROM shop_private.ch10_job
    WHERE job_state = 'queued'
    ORDER BY job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 3
),
claimed AS (
    UPDATE shop_private.ch10_job AS job
    SET job_state = 'running',
        claimed_by = :'worker',
        claimed_at = timestamptz '2025-01-01 00:06:00+00'
    FROM picked
    WHERE job.job_id = picked.job_id
    RETURNING job.job_id
)
SELECT pg_catalog.format(
           'worker=%s/claimed=%s',
           :'worker',
           pg_catalog.string_agg(
               job_id::text,
               ',' ORDER BY job_id
           )
       )
FROM claimed;

SELECT pg_catalog.pg_advisory_xact_lock(3610, :gate);
COMMIT;
