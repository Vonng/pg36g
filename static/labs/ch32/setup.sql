\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA pg36_ch32;

CREATE TABLE pg36_ch32.run_marker (
    run_id      text PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE pg36_ch32.accounts (
    account_id    integer PRIMARY KEY,
    balance_cents bigint NOT NULL CHECK (balance_cents >= 0),
    status         text NOT NULL CHECK (status IN ('active', 'mispriced')),
    updated_at     timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE pg36_ch32.ledger (
    entry_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        text NOT NULL,
    account_id    integer NOT NULL
                  REFERENCES pg36_ch32.accounts(account_id),
    amount_cents  integer NOT NULL,
    stage         text NOT NULL
                  CHECK (stage IN ('safe-before', 'post-target')),
    committed_at  timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE pg36_ch32.outbox (
    event_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        text NOT NULL,
    account_id    integer NOT NULL
                  REFERENCES pg36_ch32.accounts(account_id),
    event_kind    text NOT NULL,
    state         text NOT NULL CHECK (state IN ('pending', 'canceled')),
    created_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (run_id, event_kind, account_id)
);

CREATE TABLE pg36_ch32.incident_audit (
    run_id       text NOT NULL,
    stage        text NOT NULL,
    xact_id      text NOT NULL,
    observed_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    wal_lsn      pg_lsn NOT NULL,
    details      jsonb NOT NULL,
    PRIMARY KEY (run_id, stage)
);

INSERT INTO pg36_ch32.run_marker (run_id)
VALUES (:'run_id');

INSERT INTO pg36_ch32.accounts (
    account_id,
    balance_cents,
    status
)
SELECT
    id,
    100000 + id,
    'active'
FROM generate_series(1, :account_count) AS id;

INSERT INTO pg36_ch32.incident_audit (
    run_id,
    stage,
    xact_id,
    wal_lsn,
    details
)
VALUES (
    :'run_id',
    'base',
    pg_current_xact_id()::text,
    pg_current_wal_lsn(),
    jsonb_build_object(
        'account_count', :account_count,
        'external_dispatch_enabled', false
    )
);

COMMIT;

SELECT json_build_object(
    'run_id', :'run_id',
    'accounts', count(*),
    'balance_cents', sum(balance_cents),
    'active', count(*) FILTER (WHERE status = 'active'),
    'schema', 'pg36_ch32'
)
FROM pg36_ch32.accounts;
