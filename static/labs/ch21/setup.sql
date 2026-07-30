\set ON_ERROR_STOP on

\if :{?run_id}
\else
  \echo 'run_id is required'
  \quit 64
\endif
\if :{?stage}
\else
  \echo 'stage is required'
  \quit 64
\endif
\if :{?token}
\else
  \echo 'token is required'
  \quit 64
\endif

CREATE SCHEMA IF NOT EXISTS pg36_ch21;

CREATE TABLE IF NOT EXISTS pg36_ch21.recovery_probe (
    run_id       text        NOT NULL,
    stage        text        NOT NULL
                             CHECK (stage IN ('base', 'keep', 'discard')),
    token        text        NOT NULL UNIQUE,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, stage)
);

INSERT INTO pg36_ch21.recovery_probe (run_id, stage, token)
VALUES (:'run_id', :'stage', :'token')
ON CONFLICT (run_id, stage) DO NOTHING
RETURNING run_id, stage, token, committed_at;
