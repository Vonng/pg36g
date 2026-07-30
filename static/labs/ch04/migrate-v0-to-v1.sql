\set ON_ERROR_STOP on
\ir context.sql

SELECT pg_catalog.to_regclass('shop_private.schema_version') IS NOT NULL
       AS version_table_exists
\gset

\if :version_table_exists
  SELECT EXISTS (
             SELECT 1
             FROM shop_private.schema_version
             WHERE version = 1
         ) AS already_v1
  \gset
\else
  \set already_v1 false
\endif

\if :already_v1
  \echo '[migrate] ch04 physical model v1 is already installed'
\else

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $precheck$
DECLARE
    required_relation text;
BEGIN
    FOREACH required_relation IN ARRAY ARRAY[
        'shop.customer',
        'shop.product',
        'shop.sales_order',
        'shop.sales_order_item',
        'shop.payment',
        'shop_api.order_summary'
    ]
    LOOP
        IF pg_catalog.to_regclass(required_relation) IS NULL THEN
            RAISE EXCEPTION
                'ch03 v0 prerequisite is missing: %',
                required_relation;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute
        WHERE attrelid = 'shop.product'::regclass
          AND attname = 'current_unit_price'
          AND attnum > 0
          AND NOT attisdropped
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute
        WHERE attrelid = 'shop.sales_order_item'::regclass
          AND attname = 'unit_price'
          AND attnum > 0
          AND NOT attisdropped
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute
        WHERE attrelid = 'shop.payment'::regclass
          AND attname = 'amount'
          AND attnum > 0
          AND NOT attisdropped
    ) THEN
        RAISE EXCEPTION
            'migration expects the ch03 v0 money columns';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.product
        WHERE current_unit_price::text IN ('NaN', 'Infinity', '-Infinity')
           OR current_unit_price * 100
              <> pg_catalog.trunc(current_unit_price * 100)
           OR current_unit_price * 100 > 1000000000000
    ) THEN
        RAISE EXCEPTION
            'product price cannot be represented as bounded integer minor units';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.sales_order_item
        WHERE unit_price::text IN ('NaN', 'Infinity', '-Infinity')
           OR unit_price * 100 <> pg_catalog.trunc(unit_price * 100)
           OR unit_price * 100 > 1000000000000
           OR quantity > 1000000
    ) THEN
        RAISE EXCEPTION
            'order item cannot be represented by the v1 money contract';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.payment
        WHERE amount::text IN ('NaN', 'Infinity', '-Infinity')
           OR amount * 100 <> pg_catalog.trunc(amount * 100)
           OR amount * 100 > 1000000000000000
    ) THEN
        RAISE EXCEPTION
            'payment cannot be represented by the v1 money contract';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.customer
        WHERE email <> pg_catalog.lower(email COLLATE "C")
    ) OR EXISTS (
        SELECT 1
        FROM shop.sales_order
        WHERE buyer_email <> pg_catalog.lower(buyer_email COLLATE "C")
    ) THEN
        RAISE EXCEPTION
            'v1 requires canonical lower-case ASCII email input';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.sales_order
        WHERE order_status NOT IN ('draft', 'placed', 'paid', 'cancelled')
    ) OR EXISTS (
        SELECT 1
        FROM shop.payment
        WHERE payment_status NOT IN ('pending', 'captured', 'declined')
    ) THEN
        RAISE EXCEPTION
            'v0 contains a status outside the v1 state catalogs';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop.sales_order
        WHERE order_status IN ('draft', 'cancelled')
    ) THEN
        RAISE EXCEPTION
            'draft/cancelled v0 orders require explicit time reconciliation before v1 migration';
    END IF;
END
$precheck$;

DROP VIEW shop_api.order_summary;

CREATE TABLE shop_private.schema_version (
    version      integer NOT NULL,
    applied_at   timestamptz(3) NOT NULL
                 DEFAULT pg_catalog.transaction_timestamp(),
    description  text NOT NULL,
    CONSTRAINT schema_version_pkey PRIMARY KEY (version),
    CONSTRAINT schema_version_description_nonempty
        CHECK (pg_catalog.btrim(description) <> '')
);

CREATE TABLE shop_private.order_status_catalog (
    status_code  text NOT NULL,
    terminal     boolean NOT NULL,
    description  text NOT NULL,
    CONSTRAINT order_status_catalog_pkey PRIMARY KEY (status_code),
    CONSTRAINT order_status_catalog_code_format
        CHECK (
            status_code COLLATE "C" ~ '^[a-z][a-z0-9_]*$'
        ),
    CONSTRAINT order_status_catalog_description_nonempty
        CHECK (pg_catalog.btrim(description) <> '')
);

CREATE TABLE shop_private.order_status_transition (
    from_status  text NOT NULL,
    to_status    text NOT NULL,
    CONSTRAINT order_status_transition_pkey
        PRIMARY KEY (from_status, to_status),
    CONSTRAINT order_status_transition_from_fkey
        FOREIGN KEY (from_status)
        REFERENCES shop_private.order_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT order_status_transition_to_fkey
        FOREIGN KEY (to_status)
        REFERENCES shop_private.order_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT order_status_transition_changes_state
        CHECK (from_status <> to_status)
);

CREATE TABLE shop_private.payment_status_catalog (
    status_code  text NOT NULL,
    terminal     boolean NOT NULL,
    description  text NOT NULL,
    CONSTRAINT payment_status_catalog_pkey PRIMARY KEY (status_code),
    CONSTRAINT payment_status_catalog_code_format
        CHECK (
            status_code COLLATE "C" ~ '^[a-z][a-z0-9_]*$'
        ),
    CONSTRAINT payment_status_catalog_description_nonempty
        CHECK (pg_catalog.btrim(description) <> '')
);

CREATE TABLE shop_private.payment_status_transition (
    from_status  text NOT NULL,
    to_status    text NOT NULL,
    CONSTRAINT payment_status_transition_pkey
        PRIMARY KEY (from_status, to_status),
    CONSTRAINT payment_status_transition_from_fkey
        FOREIGN KEY (from_status)
        REFERENCES shop_private.payment_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT payment_status_transition_to_fkey
        FOREIGN KEY (to_status)
        REFERENCES shop_private.payment_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT payment_status_transition_changes_state
        CHECK (from_status <> to_status)
);

INSERT INTO shop_private.order_status_catalog (
    status_code,
    terminal,
    description
)
VALUES
    ('draft', false, 'Created but not placed'),
    ('placed', false, 'Placed and awaiting settlement'),
    ('paid', true, 'Payment captured'),
    ('cancelled', true, 'Cancelled before completion');

INSERT INTO shop_private.order_status_transition (
    from_status,
    to_status
)
VALUES
    ('draft', 'placed'),
    ('draft', 'cancelled'),
    ('placed', 'paid'),
    ('placed', 'cancelled');

INSERT INTO shop_private.payment_status_catalog (
    status_code,
    terminal,
    description
)
VALUES
    ('pending', false, 'Provider result is pending'),
    ('captured', true, 'Funds captured'),
    ('declined', true, 'Provider declined the payment');

INSERT INTO shop_private.payment_status_transition (
    from_status,
    to_status
)
VALUES
    ('pending', 'captured'),
    ('pending', 'declined');

ALTER TABLE shop.customer
    ALTER COLUMN customer_id ADD GENERATED BY DEFAULT AS IDENTITY,
    ALTER COLUMN created_at TYPE timestamptz(3),
    ALTER COLUMN created_at
        SET DEFAULT pg_catalog.transaction_timestamp(),
    ADD CONSTRAINT customer_ref_format
        CHECK (
            customer_ref COLLATE "C" ~ '^CUST-[A-Z0-9-]+$'
        ),
    ADD CONSTRAINT customer_email_canonical
        CHECK (
            email = pg_catalog.lower(email COLLATE "C")
            AND email COLLATE "C"
                ~ '^[a-z0-9][a-z0-9._+%-]*@[a-z0-9][a-z0-9.-]*$'
        ),
    ADD CONSTRAINT customer_display_name_nonempty
        CHECK (pg_catalog.btrim(display_name) <> '');

ALTER TABLE shop.product
    DROP CONSTRAINT product_price_nonnegative,
    ALTER COLUMN product_id ADD GENERATED BY DEFAULT AS IDENTITY,
    ALTER COLUMN created_at TYPE timestamptz(3),
    ALTER COLUMN created_at
        SET DEFAULT pg_catalog.transaction_timestamp(),
    ADD COLUMN currency_code text,
    ADD COLUMN current_unit_price_minor bigint,
    ADD CONSTRAINT product_sku_format
        CHECK (
            sku COLLATE "C" ~ '^SKU-[A-Z0-9-]+$'
        ),
    ADD CONSTRAINT product_name_nonempty
        CHECK (pg_catalog.btrim(product_name) <> '');

UPDATE shop.product
SET
    currency_code = 'CNY',
    current_unit_price_minor =
        (current_unit_price * 100)::bigint;

ALTER TABLE shop.product
    ALTER COLUMN currency_code SET NOT NULL,
    ALTER COLUMN current_unit_price_minor SET NOT NULL,
    DROP COLUMN current_unit_price,
    ADD CONSTRAINT product_currency_supported
        CHECK (currency_code = 'CNY'),
    ADD CONSTRAINT product_price_minor_bounds
        CHECK (
            current_unit_price_minor
            BETWEEN 0 AND 1000000000000
        );

ALTER TABLE shop.sales_order
    ALTER COLUMN order_id ADD GENERATED BY DEFAULT AS IDENTITY,
    ALTER COLUMN placed_at TYPE timestamptz(3),
    ALTER COLUMN placed_at DROP NOT NULL,
    ADD COLUMN currency_code text,
    ADD COLUMN paid_at timestamptz(3),
    ADD COLUMN cancelled_at timestamptz(3),
    ADD CONSTRAINT sales_order_order_no_format
        CHECK (
            order_no COLLATE "C" ~ '^ORD-[A-Z0-9-]+$'
        ),
    ADD CONSTRAINT sales_order_request_key_nonempty
        CHECK (pg_catalog.btrim(request_key) <> ''),
    ADD CONSTRAINT sales_order_request_fingerprint_format
        CHECK (
            request_fingerprint COLLATE "C" ~ '^[0-9a-f]{32}$'
        ),
    ADD CONSTRAINT sales_order_buyer_email_canonical
        CHECK (
            buyer_email = pg_catalog.lower(buyer_email COLLATE "C")
            AND buyer_email COLLATE "C"
                ~ '^[a-z0-9][a-z0-9._+%-]*@[a-z0-9][a-z0-9.-]*$'
        ),
    ADD CONSTRAINT sales_order_trace_nonempty
        CHECK (pg_catalog.btrim(created_by_trace_id) <> '');

UPDATE shop.sales_order AS o
SET
    currency_code = 'CNY',
    paid_at = CASE
        WHEN o.order_status = 'paid' THEN (
            SELECT min(p.occurred_at)::timestamptz(3)
            FROM shop.payment AS p
            WHERE p.order_id = o.order_id
              AND p.payment_status = 'captured'
        )
        ELSE NULL
    END;

DO $paid_precheck$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM shop.sales_order
        WHERE order_status = 'paid'
          AND paid_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'paid v0 order has no captured payment timestamp';
    END IF;
END
$paid_precheck$;

ALTER TABLE shop.sales_order
    ALTER COLUMN currency_code SET NOT NULL,
    ADD CONSTRAINT sales_order_currency_supported
        CHECK (currency_code = 'CNY'),
    ADD CONSTRAINT sales_order_order_currency_key
        UNIQUE (order_id, currency_code),
    ADD CONSTRAINT sales_order_status_fkey
        FOREIGN KEY (order_status)
        REFERENCES shop_private.order_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    ADD CONSTRAINT sales_order_state_time_consistent
        CHECK (
            (
                order_status = 'draft'
                AND placed_at IS NULL
                AND paid_at IS NULL
                AND cancelled_at IS NULL
            )
            OR
            (
                order_status = 'placed'
                AND placed_at IS NOT NULL
                AND paid_at IS NULL
                AND cancelled_at IS NULL
            )
            OR
            (
                order_status = 'paid'
                AND placed_at IS NOT NULL
                AND paid_at IS NOT NULL
                AND paid_at >= placed_at
                AND cancelled_at IS NULL
            )
            OR
            (
                order_status = 'cancelled'
                AND paid_at IS NULL
                AND cancelled_at IS NOT NULL
                AND (
                    placed_at IS NULL
                    OR cancelled_at >= placed_at
                )
            )
        );

ALTER TABLE shop.sales_order_item
    DROP CONSTRAINT sales_order_item_order_fkey,
    DROP CONSTRAINT sales_order_item_price_nonnegative,
    DROP CONSTRAINT sales_order_item_quantity_positive,
    ADD COLUMN currency_code text,
    ADD COLUMN unit_price_minor bigint;

UPDATE shop.sales_order_item AS i
SET
    currency_code = o.currency_code,
    unit_price_minor = (i.unit_price * 100)::bigint
FROM shop.sales_order AS o
WHERE o.order_id = i.order_id;

ALTER TABLE shop.sales_order_item
    ALTER COLUMN currency_code SET NOT NULL,
    ALTER COLUMN unit_price_minor SET NOT NULL,
    DROP COLUMN unit_price,
    ADD COLUMN line_total_minor bigint
        GENERATED ALWAYS AS (
            unit_price_minor * quantity::bigint
        ) STORED,
    ADD CONSTRAINT sales_order_item_order_fkey
        FOREIGN KEY (order_id, currency_code)
        REFERENCES shop.sales_order (order_id, currency_code)
        ON UPDATE RESTRICT
        ON DELETE CASCADE,
    ADD CONSTRAINT sales_order_item_currency_supported
        CHECK (currency_code = 'CNY'),
    ADD CONSTRAINT sales_order_item_price_minor_bounds
        CHECK (
            unit_price_minor
            BETWEEN 0 AND 1000000000000
        ),
    ADD CONSTRAINT sales_order_item_quantity_bounds
        CHECK (quantity BETWEEN 1 AND 1000000),
    ADD CONSTRAINT sales_order_item_line_total_bounds
        CHECK (
            line_total_minor
            BETWEEN 0 AND 1000000000000000000
        ),
    ADD CONSTRAINT sales_order_item_sku_snapshot_nonempty
        CHECK (pg_catalog.btrim(sku_snapshot) <> ''),
    ADD CONSTRAINT sales_order_item_name_snapshot_nonempty
        CHECK (pg_catalog.btrim(product_name_snapshot) <> '');

ALTER TABLE shop.payment
    DROP CONSTRAINT payment_order_fkey,
    DROP CONSTRAINT payment_amount_positive,
    ALTER COLUMN payment_id ADD GENERATED BY DEFAULT AS IDENTITY,
    ALTER COLUMN occurred_at TYPE timestamptz(3),
    ADD COLUMN currency_code text,
    ADD COLUMN amount_minor bigint,
    ADD COLUMN failure_code text;

UPDATE shop.payment AS p
SET
    currency_code = o.currency_code,
    amount_minor = (p.amount * 100)::bigint,
    failure_code = CASE
        WHEN p.payment_status = 'declined'
            THEN 'LEGACY_REASON_UNAVAILABLE'
        ELSE NULL
    END
FROM shop.sales_order AS o
WHERE o.order_id = p.order_id;

ALTER TABLE shop.payment
    ALTER COLUMN currency_code SET NOT NULL,
    ALTER COLUMN amount_minor SET NOT NULL,
    DROP COLUMN amount,
    ADD CONSTRAINT payment_order_fkey
        FOREIGN KEY (order_id, currency_code)
        REFERENCES shop.sales_order (order_id, currency_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    ADD CONSTRAINT payment_status_fkey
        FOREIGN KEY (payment_status)
        REFERENCES shop_private.payment_status_catalog (status_code)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    ADD CONSTRAINT payment_currency_supported
        CHECK (currency_code = 'CNY'),
    ADD CONSTRAINT payment_amount_minor_bounds
        CHECK (
            amount_minor
            BETWEEN 1 AND 1000000000000000
        ),
    ADD CONSTRAINT payment_failure_semantics
        CHECK (
            (
                payment_status = 'declined'
                AND failure_code IS NOT NULL
                AND pg_catalog.btrim(failure_code) <> ''
            )
            OR
            (
                payment_status IN ('pending', 'captured')
                AND failure_code IS NULL
            )
        ),
    ADD CONSTRAINT payment_provider_nonempty
        CHECK (pg_catalog.btrim(provider) <> ''),
    ADD CONSTRAINT payment_provider_ref_nonempty
        CHECK (pg_catalog.btrim(provider_payment_ref) <> ''),
    ADD CONSTRAINT payment_idempotency_nonempty
        CHECK (pg_catalog.btrim(idempotency_key) <> ''),
    ADD CONSTRAINT payment_request_fingerprint_format
        CHECK (
            request_fingerprint COLLATE "C" ~ '^[0-9a-f]{32}$'
        ),
    ADD CONSTRAINT payment_trace_nonempty
        CHECK (pg_catalog.btrim(trace_id) <> '');

DO $identity_sequences$
DECLARE
    identity_spec record;
    sequence_name regclass;
    maximum_id bigint;
BEGIN
    FOR identity_spec IN
        SELECT *
        FROM (
            VALUES
                ('customer', 'customer_id'),
                ('product', 'product_id'),
                ('sales_order', 'order_id'),
                ('payment', 'payment_id')
        ) AS spec(table_name, column_name)
    LOOP
        sequence_name :=
            pg_catalog.pg_get_serial_sequence(
                pg_catalog.format(
                    '%I.%I',
                    'shop',
                    identity_spec.table_name
                ),
                identity_spec.column_name
            )::regclass;

        EXECUTE pg_catalog.format(
            'SELECT max(%I) FROM %I.%I',
            identity_spec.column_name,
            'shop',
            identity_spec.table_name
        )
        INTO maximum_id;

        IF maximum_id IS NULL THEN
            PERFORM pg_catalog.setval(sequence_name, 1, false);
        ELSE
            PERFORM pg_catalog.setval(
                sequence_name,
                maximum_id,
                true
            );
        END IF;
    END LOOP;
END
$identity_sequences$;

CREATE FUNCTION shop_private.enforce_order_status_transition()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, shop_private
AS $function$
BEGIN
    IF NEW.order_status IS DISTINCT FROM OLD.order_status
       AND NOT EXISTS (
           SELECT 1
           FROM shop_private.order_status_transition
           WHERE from_status = OLD.order_status
             AND to_status = NEW.order_status
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            CONSTRAINT = 'sales_order_status_transition',
            MESSAGE = pg_catalog.format(
                'order status transition %s -> %s is not allowed',
                OLD.order_status,
                NEW.order_status
            );
    END IF;

    RETURN NEW;
END
$function$;

CREATE FUNCTION shop_private.enforce_payment_status_transition()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, shop_private
AS $function$
BEGIN
    IF NEW.payment_status IS DISTINCT FROM OLD.payment_status
       AND NOT EXISTS (
           SELECT 1
           FROM shop_private.payment_status_transition
           WHERE from_status = OLD.payment_status
             AND to_status = NEW.payment_status
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            CONSTRAINT = 'payment_status_transition',
            MESSAGE = pg_catalog.format(
                'payment status transition %s -> %s is not allowed',
                OLD.payment_status,
                NEW.payment_status
            );
    END IF;

    RETURN NEW;
END
$function$;

REVOKE ALL
ON FUNCTION shop_private.enforce_order_status_transition()
FROM PUBLIC;

REVOKE ALL
ON FUNCTION shop_private.enforce_payment_status_transition()
FROM PUBLIC;

CREATE TRIGGER sales_order_status_transition_guard
BEFORE UPDATE OF order_status
ON shop.sales_order
FOR EACH ROW
EXECUTE FUNCTION shop_private.enforce_order_status_transition();

CREATE TRIGGER payment_status_transition_guard
BEFORE UPDATE OF payment_status
ON shop.payment
FOR EACH ROW
EXECUTE FUNCTION shop_private.enforce_payment_status_transition();

CREATE VIEW shop_api.order_summary
AS
SELECT
    o.order_id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.currency_code,
    o.placed_at,
    o.paid_at,
    o.cancelled_at,
    count(i.line_no) AS item_count,
    COALESCE(
        sum(i.line_total_minor),
        0::numeric
    ) AS item_subtotal_minor,
    COALESCE(
        (
            SELECT sum(p.amount_minor)
            FROM shop.payment AS p
            WHERE p.order_id = o.order_id
              AND p.payment_status = 'captured'
        ),
        0::numeric
    ) AS captured_amount_minor
FROM shop.sales_order AS o
LEFT JOIN shop.sales_order_item AS i
  ON i.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.currency_code,
    o.placed_at,
    o.paid_at,
    o.cancelled_at;

COMMENT ON TABLE shop.sales_order_item IS
    'Purchase-time snapshots and exact CNY minor units; ch04 physical model v1';
COMMENT ON COLUMN shop.product.current_unit_price_minor IS
    'Current catalog price in CNY fen; 100 minor units = 1 yuan';
COMMENT ON COLUMN shop.sales_order_item.unit_price_minor IS
    'Purchase-time unit price snapshot in CNY fen';
COMMENT ON COLUMN shop.sales_order_item.line_total_minor IS
    'Stored generated fact: unit_price_minor * quantity';
COMMENT ON COLUMN shop.payment.amount_minor IS
    'Provider payment amount in CNY fen; refunds are separate future facts';
COMMENT ON VIEW shop_api.order_summary IS
    'Derived query model exposing exact CNY minor-unit totals';

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE
    shop.customer,
    shop.product,
    shop.sales_order,
    shop.sales_order_item,
    shop.payment
TO pg36_app;

GRANT SELECT
ON TABLE
    shop.customer,
    shop.product,
    shop.sales_order,
    shop.sales_order_item,
    shop.payment
TO pg36_ro;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA shop
TO pg36_app;

GRANT SELECT
ON ALL SEQUENCES IN SCHEMA shop
TO pg36_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT USAGE, SELECT ON SEQUENCES TO pg36_app;

ALTER DEFAULT PRIVILEGES FOR ROLE pg36_owner IN SCHEMA shop
GRANT SELECT ON SEQUENCES TO pg36_ro;

GRANT SELECT
ON shop_api.order_summary
TO pg36_app, pg36_ro;

INSERT INTO shop_private.schema_version (
    version,
    description
)
VALUES (
    1,
    'ch04 reliable physical model'
);

COMMIT;

\echo '[migrate] ch03 v0 -> ch04 physical model v1 complete'

\endif
