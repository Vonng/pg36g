\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $collision_guard$
DECLARE
    schema_oid oid := pg_catalog.to_regnamespace('shop_ch13');
    expected_marker constant text :=
        'pg36 ch13 routine guard lab; safe to rebuild';
BEGIN
    IF schema_oid IS NULL THEN
        RETURN;
    END IF;

    IF pg_catalog.obj_description(
           schema_oid,
           'pg_namespace'
       ) IS DISTINCT FROM expected_marker THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch13 lacks the ch13 marker';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
          AND relation.relname <> ALL (ARRAY[
              'schema_version',
              'sales_order',
              'payment',
              'order_history',
              'statement_audit',
              'payment_payment_id_seq',
              'order_history_history_id_seq',
              'statement_audit_audit_id_seq'
          ])
    ) THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch13 contains unknown relations';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        WHERE relation.relnamespace = schema_oid
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
          AND pg_catalog.obj_description(
                  relation.oid,
                  'pg_class'
              ) IS DISTINCT FROM expected_marker
    ) THEN
        RAISE EXCEPTION
            'refusing collision: a shop_ch13 relation lacks the marker';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
          AND routine.oid::pg_catalog.regprocedure::text
              <> ALL (ARRAY[
              'shop_ch13.allowed_transition(text,text)',
              'shop_ch13.order_snapshot(bigint)',
              'shop_ch13.guard_order_transition()',
              'shop_ch13.audit_order_transition()',
              'shop_ch13.validate_paid_order()',
              'shop_ch13.transition_order(bigint,bigint,text,text)',
              'shop_ch13.capture_payment(bigint,bigint,text,bigint,text)',
              'shop_ch13.expire_stale_orders(timestamp with time zone,integer,integer)'
          ])
    ) THEN
        RAISE EXCEPTION
            'refusing collision: schema shop_ch13 contains unknown routines';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS routine
        WHERE routine.pronamespace = schema_oid
          AND pg_catalog.obj_description(
                  routine.oid,
                  'pg_proc'
              ) IS DISTINCT FROM expected_marker
    ) THEN
        RAISE EXCEPTION
            'refusing collision: a shop_ch13 routine lacks the marker';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_trigger AS trigger_catalog
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_catalog.tgrelid
        WHERE relation.relnamespace = schema_oid
          AND NOT trigger_catalog.tgisinternal
          AND trigger_catalog.tgname <> ALL (ARRAY[
              'a_guard_order_transition',
              'z_audit_order_transition',
              'z_validate_paid_order',
              'z_validate_payment'
          ])
    ) THEN
        RAISE EXCEPTION
            'refusing collision: shop_ch13 contains unknown triggers';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_trigger AS trigger_catalog
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_catalog.tgrelid
        WHERE relation.relnamespace = schema_oid
          AND NOT trigger_catalog.tgisinternal
          AND pg_catalog.obj_description(
                  trigger_catalog.oid,
                  'pg_trigger'
              ) IS DISTINCT FROM expected_marker
    ) THEN
        RAISE EXCEPTION
            'refusing collision: a shop_ch13 trigger lacks the marker';
    END IF;
END
$collision_guard$;

DROP TABLE IF EXISTS shop_ch13.payment;
DROP TABLE IF EXISTS shop_ch13.order_history;
DROP TABLE IF EXISTS shop_ch13.statement_audit;
DROP TABLE IF EXISTS shop_ch13.sales_order;
DROP TABLE IF EXISTS shop_ch13.schema_version;

DROP PROCEDURE IF EXISTS shop_ch13.expire_stale_orders(
    timestamptz,
    integer,
    integer
);
DROP FUNCTION IF EXISTS shop_ch13.capture_payment(
    bigint,
    bigint,
    text,
    bigint,
    text
);
DROP FUNCTION IF EXISTS shop_ch13.transition_order(
    bigint,
    bigint,
    text,
    text
);
DROP FUNCTION IF EXISTS shop_ch13.validate_paid_order();
DROP FUNCTION IF EXISTS shop_ch13.audit_order_transition();
DROP FUNCTION IF EXISTS shop_ch13.guard_order_transition();
DROP FUNCTION IF EXISTS shop_ch13.order_snapshot(bigint);
DROP FUNCTION IF EXISTS shop_ch13.allowed_transition(text, text);
DROP SCHEMA IF EXISTS shop_ch13;

CREATE SCHEMA shop_ch13 AUTHORIZATION pg36_owner;
COMMENT ON SCHEMA shop_ch13 IS
    'pg36 ch13 routine guard lab; safe to rebuild';
REVOKE ALL ON SCHEMA shop_ch13 FROM PUBLIC;
GRANT USAGE ON SCHEMA shop_ch13 TO pg36_app;

CREATE TABLE shop_ch13.schema_version (
    version integer PRIMARY KEY,
    description text NOT NULL,
    installed_at timestamptz NOT NULL
);

CREATE TABLE shop_ch13.sales_order (
    order_id bigint PRIMARY KEY,
    order_ref text NOT NULL UNIQUE,
    total_minor bigint NOT NULL,
    status text NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT sales_order_total_positive
        CHECK (total_minor > 0),
    CONSTRAINT sales_order_status_domain
        CHECK (
            status IN (
                'created',
                'paid',
                'packing',
                'shipped',
                'completed',
                'canceled',
                'expired'
            )
        ),
    CONSTRAINT sales_order_version_nonnegative
        CHECK (version >= 0),
    CONSTRAINT sales_order_time_order
        CHECK (updated_at >= created_at)
);

CREATE TABLE shop_ch13.payment (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES shop_ch13.sales_order(order_id)
        ON DELETE RESTRICT,
    payment_ref text NOT NULL UNIQUE,
    amount_minor bigint NOT NULL,
    status text NOT NULL,
    captured_at timestamptz NOT NULL,
    CONSTRAINT payment_amount_positive
        CHECK (amount_minor > 0),
    CONSTRAINT payment_status_domain
        CHECK (status IN ('captured', 'refunded'))
);

CREATE TABLE shop_ch13.order_history (
    history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES shop_ch13.sales_order(order_id)
        ON DELETE RESTRICT,
    old_status text NOT NULL,
    new_status text NOT NULL,
    old_version bigint NOT NULL,
    new_version bigint NOT NULL,
    actor text NOT NULL,
    session_actor name NOT NULL,
    changed_at timestamptz NOT NULL,
    transaction_id xid8 NOT NULL
);

CREATE TABLE shop_ch13.statement_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id xid8 NOT NULL,
    actor text NOT NULL,
    session_actor name NOT NULL,
    affected_count integer NOT NULL,
    order_ids bigint[] NOT NULL,
    changed_at timestamptz NOT NULL,
    CONSTRAINT statement_audit_affected_positive
        CHECK (affected_count > 0),
    CONSTRAINT statement_audit_count_matches
        CHECK (
            affected_count =
            pg_catalog.cardinality(order_ids)
        )
);

ALTER TABLE shop_ch13.schema_version OWNER TO pg36_owner;
ALTER TABLE shop_ch13.sales_order OWNER TO pg36_owner;
ALTER TABLE shop_ch13.payment OWNER TO pg36_owner;
ALTER TABLE shop_ch13.order_history OWNER TO pg36_owner;
ALTER TABLE shop_ch13.statement_audit OWNER TO pg36_owner;

COMMENT ON TABLE shop_ch13.schema_version IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TABLE shop_ch13.sales_order IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TABLE shop_ch13.payment IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TABLE shop_ch13.order_history IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TABLE shop_ch13.statement_audit IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON SEQUENCE shop_ch13.payment_payment_id_seq IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON SEQUENCE shop_ch13.order_history_history_id_seq IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON SEQUENCE shop_ch13.statement_audit_audit_id_seq IS
    'pg36 ch13 routine guard lab; safe to rebuild';

CREATE FUNCTION shop_ch13.allowed_transition(
    p_from text,
    p_to text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SECURITY INVOKER
AS $function$
    SELECT (p_from, p_to) IN (
        ('created', 'paid'),
        ('created', 'canceled'),
        ('created', 'expired'),
        ('paid', 'packing'),
        ('packing', 'shipped'),
        ('shipped', 'completed')
    )
$function$;

CREATE FUNCTION shop_ch13.order_snapshot(
    p_order_id bigint
)
RETURNS TABLE (
    result_order_id bigint,
    result_order_ref text,
    result_total_minor bigint,
    result_status text,
    result_version bigint,
    result_updated_at timestamptz
)
LANGUAGE sql
STABLE
STRICT
PARALLEL SAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
    SELECT
        target.order_id,
        target.order_ref,
        target.total_minor,
        target.status,
        target.version,
        target.updated_at
    FROM shop_ch13.sales_order AS target
    WHERE target.order_id = p_order_id
$function$;

CREATE FUNCTION shop_ch13.guard_order_transition()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT shop_ch13.allowed_transition(
                   OLD.status,
                   NEW.status
               ) THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P3613',
                MESSAGE = 'order status transition rejected',
                DETAIL = pg_catalog.format(
                    'order_id=%s transition=%s->%s',
                    OLD.order_id,
                    OLD.status,
                    NEW.status
                ),
                HINT = 'Use an allowed transition through the command API.';
        END IF;

        IF NEW.version IS DISTINCT FROM OLD.version + 1 THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P3615',
                MESSAGE = 'order version step rejected',
                DETAIL = pg_catalog.format(
                    'order_id=%s old_version=%s new_version=%s',
                    OLD.order_id,
                    OLD.version,
                    NEW.version
                ),
                HINT = 'Each state transition must advance version by one.';
        END IF;

        NEW.updated_at := pg_catalog.statement_timestamp();
    ELSIF NEW.version IS DISTINCT FROM OLD.version THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3615',
            MESSAGE = 'order version changed without a state transition',
            DETAIL = pg_catalog.format(
                'order_id=%s old_version=%s new_version=%s',
                OLD.order_id,
                OLD.version,
                NEW.version
            );
    END IF;

    RETURN NEW;
END
$function$;

CREATE FUNCTION shop_ch13.audit_order_transition()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    change_count integer;
    audit_actor text := coalesce(
        nullif(
            pg_catalog.current_setting('pg36.actor', true),
            ''
        ),
        session_user::text
    );
BEGIN
    INSERT INTO shop_ch13.order_history (
        order_id,
        old_status,
        new_status,
        old_version,
        new_version,
        actor,
        session_actor,
        changed_at,
        transaction_id
    )
    SELECT
        new_rows.order_id,
        old_rows.status,
        new_rows.status,
        old_rows.version,
        new_rows.version,
        audit_actor,
        session_user,
        pg_catalog.statement_timestamp(),
        pg_catalog.pg_current_xact_id()
    FROM old_rows
    JOIN new_rows USING (order_id)
    WHERE old_rows.status IS DISTINCT FROM new_rows.status;

    GET DIAGNOSTICS change_count = ROW_COUNT;

    IF change_count > 0 THEN
        INSERT INTO shop_ch13.statement_audit (
            transaction_id,
            actor,
            session_actor,
            affected_count,
            order_ids,
            changed_at
        )
        SELECT
            pg_catalog.pg_current_xact_id(),
            audit_actor,
            session_user,
            pg_catalog.count(*)::integer,
            pg_catalog.array_agg(
                new_rows.order_id
                ORDER BY new_rows.order_id
            ),
            pg_catalog.statement_timestamp()
        FROM old_rows
        JOIN new_rows USING (order_id)
        WHERE old_rows.status IS DISTINCT FROM new_rows.status;
    END IF;

    RETURN NULL;
END
$function$;

CREATE FUNCTION shop_ch13.validate_paid_order()
RETURNS trigger
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    target_order_id bigint;
    target_status text;
    target_total bigint;
    captured_total bigint;
BEGIN
    target_order_id := CASE
        WHEN TG_TABLE_NAME = 'sales_order'
            THEN coalesce(NEW.order_id, OLD.order_id)
        WHEN TG_TABLE_NAME = 'payment'
            THEN coalesce(NEW.order_id, OLD.order_id)
        ELSE NULL
    END;

    SELECT target.status, target.total_minor
    INTO target_status, target_total
    FROM shop_ch13.sales_order AS target
    WHERE target.order_id = target_order_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(
               pg_catalog.sum(payment.amount_minor)
                   FILTER (WHERE payment.status = 'captured'),
               0
           )
    INTO captured_total
    FROM shop_ch13.payment AS payment
    WHERE payment.order_id = target_order_id;

    IF (
        target_status = 'paid'
        AND captured_total IS DISTINCT FROM target_total
    ) OR (
        target_status <> 'paid'
        AND captured_total <> 0
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3614',
            MESSAGE = 'paid-order invariant rejected',
            DETAIL = pg_catalog.format(
                'order_id=%s status=%s total_minor=%s captured_minor=%s',
                target_order_id,
                target_status,
                target_total,
                captured_total
            ),
            HINT = 'Capture payment and move the order to paid in one transaction.';
    END IF;

    RETURN NULL;
END
$function$;

CREATE FUNCTION shop_ch13.transition_order(
    p_order_id bigint,
    p_expected_version bigint,
    p_target_status text,
    p_actor text
)
RETURNS TABLE (
    result_order_id bigint,
    result_status text,
    result_version bigint
)
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
BEGIN
    IF p_actor IS NULL
       OR p_actor !~ '^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,63}$' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3617',
            MESSAGE = 'actor identifier rejected',
            HINT = 'Use 1-64 safe identifier characters.';
    END IF;

    PERFORM pg_catalog.set_config('pg36.actor', p_actor, true);

    RETURN QUERY
    UPDATE shop_ch13.sales_order AS target
    SET
        status = p_target_status,
        version = target.version + 1
    WHERE target.order_id = p_order_id
      AND target.version = p_expected_version
    RETURNING
        target.order_id,
        target.status,
        target.version;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3616',
            MESSAGE = 'order version precondition failed',
            DETAIL = pg_catalog.format(
                'order_id=%s expected_version=%s',
                p_order_id,
                p_expected_version
            ),
            HINT = 'Reload the order and retry the whole command deliberately.';
    END IF;
END
$function$;

CREATE FUNCTION shop_ch13.capture_payment(
    p_order_id bigint,
    p_expected_version bigint,
    p_payment_ref text,
    p_amount_minor bigint,
    p_actor text
)
RETURNS TABLE (
    result_order_id bigint,
    result_status text,
    result_version bigint,
    result_payment_ref text
)
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    current_status text;
    current_total bigint;
    current_version bigint;
BEGIN
    IF p_actor IS NULL
       OR p_actor !~ '^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,63}$' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3617',
            MESSAGE = 'actor identifier rejected',
            HINT = 'Use 1-64 safe identifier characters.';
    END IF;

    IF p_payment_ref IS NULL
       OR p_payment_ref !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3618',
            MESSAGE = 'payment reference rejected';
    END IF;

    SELECT target.status, target.total_minor, target.version
    INTO current_status, current_total, current_version
    FROM shop_ch13.sales_order AS target
    WHERE target.order_id = p_order_id
    FOR UPDATE;

    IF NOT FOUND
       OR current_version IS DISTINCT FROM p_expected_version THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3616',
            MESSAGE = 'order version precondition failed',
            DETAIL = pg_catalog.format(
                'order_id=%s expected_version=%s',
                p_order_id,
                p_expected_version
            );
    END IF;

    IF current_status <> 'created'
       OR p_amount_minor IS DISTINCT FROM current_total THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3618',
            MESSAGE = 'payment command precondition failed',
            DETAIL = pg_catalog.format(
                'order_id=%s status=%s expected_minor=%s received_minor=%s',
                p_order_id,
                current_status,
                current_total,
                p_amount_minor
            );
    END IF;

    PERFORM pg_catalog.set_config('pg36.actor', p_actor, true);

    INSERT INTO shop_ch13.payment (
        order_id,
        payment_ref,
        amount_minor,
        status,
        captured_at
    )
    VALUES (
        p_order_id,
        p_payment_ref,
        p_amount_minor,
        'captured',
        pg_catalog.statement_timestamp()
    );

    RETURN QUERY
    UPDATE shop_ch13.sales_order AS target
    SET
        status = 'paid',
        version = target.version + 1
    WHERE target.order_id = p_order_id
    RETURNING
        target.order_id,
        target.status,
        target.version,
        p_payment_ref;
END
$function$;

CREATE PROCEDURE shop_ch13.expire_stale_orders(
    p_before timestamptz,
    p_batch_size integer,
    INOUT p_total integer
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $procedure$
DECLARE
    batch_count integer;
BEGIN
    IF p_batch_size NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'batch size must be between 1 and 1000';
    END IF;

    IF p_total IS NULL OR p_total < 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'initial total must be nonnegative';
    END IF;

    LOOP
        PERFORM pg_catalog.set_config(
            'pg36.actor',
            'ch13-maintenance',
            true
        );

        WITH candidate AS MATERIALIZED (
            SELECT target.order_id
            FROM shop_ch13.sales_order AS target
            WHERE target.status = 'created'
              AND target.created_at < p_before
            ORDER BY target.order_id
            FOR UPDATE SKIP LOCKED
            LIMIT p_batch_size
        )
        UPDATE shop_ch13.sales_order AS target
        SET
            status = 'expired',
            version = target.version + 1
        FROM candidate
        WHERE target.order_id = candidate.order_id;

        GET DIAGNOSTICS batch_count = ROW_COUNT;
        p_total := p_total + batch_count;

        EXIT WHEN batch_count = 0;
        COMMIT AND CHAIN;
    END LOOP;
END
$procedure$;

ALTER FUNCTION shop_ch13.allowed_transition(text, text)
    OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.order_snapshot(bigint)
    OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.guard_order_transition()
    OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.audit_order_transition()
    OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.validate_paid_order()
    OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.transition_order(
    bigint,
    bigint,
    text,
    text
) OWNER TO pg36_owner;
ALTER FUNCTION shop_ch13.capture_payment(
    bigint,
    bigint,
    text,
    bigint,
    text
) OWNER TO pg36_owner;
ALTER PROCEDURE shop_ch13.expire_stale_orders(
    timestamptz,
    integer,
    integer
) OWNER TO pg36_owner;

COMMENT ON FUNCTION shop_ch13.allowed_transition(text, text) IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.order_snapshot(bigint) IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.guard_order_transition() IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.audit_order_transition() IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.validate_paid_order() IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.transition_order(
    bigint,
    bigint,
    text,
    text
) IS 'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON FUNCTION shop_ch13.capture_payment(
    bigint,
    bigint,
    text,
    bigint,
    text
) IS 'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON PROCEDURE shop_ch13.expire_stale_orders(
    timestamptz,
    integer,
    integer
) IS 'pg36 ch13 routine guard lab; safe to rebuild';

CREATE TRIGGER a_guard_order_transition
BEFORE UPDATE OF status, version
ON shop_ch13.sales_order
FOR EACH ROW
EXECUTE FUNCTION shop_ch13.guard_order_transition();

CREATE TRIGGER z_audit_order_transition
AFTER UPDATE
ON shop_ch13.sales_order
REFERENCING
    OLD TABLE AS old_rows
    NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION shop_ch13.audit_order_transition();

CREATE CONSTRAINT TRIGGER z_validate_paid_order
AFTER INSERT OR UPDATE OF status, total_minor
ON shop_ch13.sales_order
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION shop_ch13.validate_paid_order();

CREATE CONSTRAINT TRIGGER z_validate_payment
AFTER INSERT OR UPDATE OR DELETE
ON shop_ch13.payment
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION shop_ch13.validate_paid_order();

COMMENT ON TRIGGER a_guard_order_transition
ON shop_ch13.sales_order IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TRIGGER z_audit_order_transition
ON shop_ch13.sales_order IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TRIGGER z_validate_paid_order
ON shop_ch13.sales_order IS
    'pg36 ch13 routine guard lab; safe to rebuild';
COMMENT ON TRIGGER z_validate_payment
ON shop_ch13.payment IS
    'pg36 ch13 routine guard lab; safe to rebuild';

REVOKE ALL ON ALL TABLES IN SCHEMA shop_ch13 FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA shop_ch13 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA shop_ch13 FROM PUBLIC;
REVOKE ALL ON PROCEDURE shop_ch13.expire_stale_orders(
    timestamptz,
    integer,
    integer
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION shop_ch13.order_snapshot(bigint)
TO pg36_app;
GRANT EXECUTE ON FUNCTION shop_ch13.transition_order(
    bigint,
    bigint,
    text,
    text
) TO pg36_app;
GRANT EXECUTE ON FUNCTION shop_ch13.capture_payment(
    bigint,
    bigint,
    text,
    bigint,
    text
) TO pg36_app;

INSERT INTO shop_ch13.schema_version (
    version,
    description,
    installed_at
)
VALUES (
    1,
    'ch13 routine guard lab',
    timestamptz '2025-01-01 00:00:00+00'
);

INSERT INTO shop_ch13.sales_order (
    order_id,
    order_ref,
    total_minor,
    status,
    version,
    created_at,
    updated_at
)
SELECT
    seed.order_id,
    'ch13-' || seed.order_id,
    seed.total_minor,
    'created',
    0,
    seed.created_at,
    seed.created_at
FROM (
    VALUES
        (101::bigint, 1000::bigint, timestamptz '2025-04-01 00:00:00+00'),
        (102::bigint, 2000::bigint, timestamptz '2025-04-02 00:00:00+00'),
        (103::bigint, 3000::bigint, timestamptz '2025-04-03 00:00:00+00'),
        (104::bigint, 4000::bigint, timestamptz '2025-04-04 00:00:00+00'),
        (105::bigint, 5000::bigint, timestamptz '2025-04-05 00:00:00+00'),
        (106::bigint, 6000::bigint, timestamptz '2025-04-06 00:00:00+00'),
        (107::bigint, 7000::bigint, timestamptz '2025-04-07 00:00:00+00'),
        (108::bigint, 8000::bigint, timestamptz '2025-04-08 00:00:00+00'),
        (201::bigint, 1100::bigint, timestamptz '2024-01-01 00:00:00+00'),
        (202::bigint, 1200::bigint, timestamptz '2024-01-02 00:00:00+00'),
        (203::bigint, 1300::bigint, timestamptz '2024-01-03 00:00:00+00'),
        (204::bigint, 1400::bigint, timestamptz '2024-01-04 00:00:00+00'),
        (205::bigint, 1500::bigint, timestamptz '2024-01-05 00:00:00+00')
) AS seed(order_id, total_minor, created_at);

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'fixture=ch13-routine-guard-v1';
SELECT 'orders=' || pg_catalog.count(*)
FROM shop_ch13.sales_order;
SELECT 'routines=' || pg_catalog.count(*)
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = routine.pronamespace
WHERE namespace.nspname = 'shop_ch13';
SELECT 'user_triggers=' || pg_catalog.count(*)
FROM pg_catalog.pg_trigger AS trigger_catalog
JOIN pg_catalog.pg_class AS relation
  ON relation.oid = trigger_catalog.tgrelid
JOIN pg_catalog.pg_namespace AS namespace
  ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'shop_ch13'
  AND NOT trigger_catalog.tgisinternal;
