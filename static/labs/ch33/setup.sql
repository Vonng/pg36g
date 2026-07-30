\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA pg36_ch33;

CREATE TABLE pg36_ch33.run_marker (
    run_id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    external_dispatch_enabled boolean NOT NULL DEFAULT false,
    CHECK (external_dispatch_enabled IS FALSE)
);

CREATE TABLE pg36_ch33.write_probe (
    run_id uuid NOT NULL REFERENCES pg36_ch33.run_marker(run_id),
    attempt_no bigint NOT NULL,
    token text NOT NULL,
    client_sent_at timestamptz NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, attempt_no),
    UNIQUE (token)
);

REVOKE ALL ON SCHEMA pg36_ch33 FROM PUBLIC;
GRANT USAGE ON SCHEMA pg36_ch33 TO test;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA pg36_ch33 TO test;

INSERT INTO pg36_ch33.run_marker (
    run_id,
    external_dispatch_enabled
)
VALUES (:'run_id'::uuid, false);

COMMIT;
