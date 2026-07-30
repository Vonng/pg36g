\set ON_ERROR_STOP on
\ir context.sql

BEGIN;
SET LOCAL TimeZone = 'UTC';

CREATE TEMPORARY TABLE booking_window (
    booking_id  bigint GENERATED ALWAYS AS IDENTITY,
    slot        tstzrange NOT NULL,
    CONSTRAINT booking_window_pkey PRIMARY KEY (booking_id),
    CONSTRAINT booking_window_nonempty
        CHECK (NOT isempty(slot)),
    CONSTRAINT booking_window_no_overlap
        EXCLUDE USING gist (slot WITH &&)
) ON COMMIT DROP;

INSERT INTO booking_window (slot)
VALUES (
    tstzrange(
        '2026-07-29 09:00:00+00',
        '2026-07-29 10:00:00+00',
        '[)'
    )
);

DO $exclusion_case$
DECLARE
    actual_constraint text;
BEGIN
    BEGIN
        INSERT INTO booking_window (slot)
        VALUES (
            tstzrange(
                '2026-07-29 09:30:00+00',
                '2026-07-29 10:30:00+00',
                '[)'
            )
        );
        RAISE EXCEPTION
            'overlapping range unexpectedly passed';
    EXCEPTION
        WHEN exclusion_violation THEN
            GET STACKED DIAGNOSTICS
                actual_constraint = CONSTRAINT_NAME;
            IF actual_constraint <> 'booking_window_no_overlap' THEN
                RAISE;
            END IF;
    END;
END
$exclusion_case$;

CREATE TEMPORARY TABLE display_slot (
    item_code  text NOT NULL,
    slot_no    integer NOT NULL,
    CONSTRAINT display_slot_pkey PRIMARY KEY (item_code),
    CONSTRAINT display_slot_slot_key
        UNIQUE (slot_no)
        DEFERRABLE INITIALLY IMMEDIATE
) ON COMMIT DROP;

INSERT INTO display_slot (item_code, slot_no)
VALUES ('A', 1), ('B', 2);

SET CONSTRAINTS display_slot_slot_key DEFERRED;

UPDATE display_slot
SET slot_no = CASE slot_no
    WHEN 1 THEN 2
    WHEN 2 THEN 1
END;

SET CONSTRAINTS display_slot_slot_key IMMEDIATE;

DO $deferrable_catalog_check$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'display_slot'::regclass
          AND conname = 'display_slot_slot_key'
          AND contype = 'u'
          AND condeferrable
          AND NOT condeferred
    ) THEN
        RAISE EXCEPTION
            'DEFERRABLE unique constraint catalog state drifted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'display_slot'::regclass
          AND contype = 'c'
          AND condeferrable
    ) THEN
        RAISE EXCEPTION
            'CHECK constraints must not be reported as deferrable';
    END IF;
END
$deferrable_catalog_check$;

\echo 'exclusion_overlap_rejected=ok'
\echo 'deferrable_unique_swap=ok'

SELECT 'btree_gist_available=' ||
       EXISTS (
           SELECT 1
           FROM pg_catalog.pg_available_extensions
           WHERE name = 'btree_gist'
       )::text AS extension_probe;

ROLLBACK;
