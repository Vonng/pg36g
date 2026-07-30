\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

CREATE TEMPORARY TABLE ch13_exception_result (
    event text NOT NULL,
    sqlstate text,
    message text,
    status_after text NOT NULL,
    version_after bigint NOT NULL
) ON COMMIT DROP;

DO $probe$
DECLARE
    caught_state text;
    caught_message text;
    state_after text;
    version_after bigint;
BEGIN
    BEGIN
        PERFORM pg_catalog.set_config(
            'pg36.actor',
            'exception-probe',
            true
        );

        UPDATE shop_ch13.sales_order
        SET
            status = 'shipped',
            version = version + 1
        WHERE order_id = 103;

        RAISE EXCEPTION
            'the invalid transition unexpectedly succeeded';
    EXCEPTION
        WHEN SQLSTATE 'P3613' THEN
            GET STACKED DIAGNOSTICS
                caught_state = RETURNED_SQLSTATE,
                caught_message = MESSAGE_TEXT;
    END;

    SELECT target.status, target.version
    INTO state_after, version_after
    FROM shop_ch13.sales_order AS target
    WHERE target.order_id = 103;

    INSERT INTO ch13_exception_result (
        event,
        sqlstate,
        message,
        status_after,
        version_after
    )
    VALUES (
        'caught-inner-subtransaction',
        caught_state,
        caught_message,
        state_after,
        version_after
    );
END
$probe$;

SELECT *
FROM ch13_exception_result;

ROLLBACK;
