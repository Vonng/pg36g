\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $phase_guard$
BEGIN
    IF (
        SELECT phase
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM 'expanded' THEN
        RAISE EXCEPTION 'compatibility probe requires expanded phase';
    END IF;
END
$phase_guard$;

-- Old application: it knows only shipping_method.
INSERT INTO shop_private.ch11_order (
    order_id,
    order_ref,
    shipping_method,
    created_at,
    payload
)
VALUES (
    90001,
    'ch11-old-app-insert',
    'standard',
    timestamptz '2025-03-01 00:00:00+00',
    'old application omitted shipping_code'
);

-- An old writer updating a legacy row also receives the derived new value.
UPDATE shop_private.ch11_order
   SET shipping_method = 'express',
       payload = 'old application changed shipping_method'
 WHERE order_id = 1;

-- New application: dual-writes both representations during coexistence.
INSERT INTO shop_private.ch11_order (
    order_id,
    order_ref,
    shipping_method,
    shipping_code,
    created_at,
    payload
)
VALUES (
    90002,
    'ch11-new-app-insert',
    'pickup',
    'PUP',
    timestamptz '2025-03-01 00:00:01+00',
    'new application dual-wrote both fields'
);

DO $negative_case$
DECLARE
    caught_state text;
    caught_constraint text;
BEGIN
    BEGIN
        INSERT INTO shop_private.ch11_order (
            order_id,
            order_ref,
            shipping_method,
            shipping_code,
            created_at,
            payload
        )
        VALUES (
            90003,
            'ch11-mismatch-must-rollback',
            'express',
            'STD',
            timestamptz '2025-03-01 00:00:02+00',
            'must not survive'
        );
        RAISE EXCEPTION
            'mismatched dual write unexpectedly succeeded';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS
                caught_state = RETURNED_SQLSTATE,
                caught_constraint = CONSTRAINT_NAME;
            IF caught_state <> '23514'
               OR caught_constraint <>
                  'ch11_order_shipping_pair_consistent' THEN
                RAISE;
            END IF;
    END;

    IF EXISTS (
        SELECT 1
        FROM shop_private.ch11_order
        WHERE order_id = 90003
    ) THEN
        RAISE EXCEPTION
            'mismatched compatibility row survived';
    END IF;
END
$negative_case$;

DO $assertions$
BEGIN
    IF (
        SELECT shipping_method || '/' || shipping_code
        FROM shop_private.ch11_order
        WHERE order_id = 90001
    ) <> 'standard/STD'
       OR (
        SELECT shipping_method || '/' || shipping_code
        FROM shop_private.ch11_order
        WHERE order_id = 1
    ) <> 'express/EXP'
       OR (
        SELECT shipping_method || '/' || shipping_code
        FROM shop_private.ch11_order
        WHERE order_id = 90002
    ) <> 'pickup/PUP' THEN
        RAISE EXCEPTION 'old/new application coexistence drifted';
    END IF;
END
$assertions$;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'old_insert=standard/STD';
SELECT 'old_update=express/EXP';
SELECT 'new_insert=pickup/PUP';
SELECT 'mismatch=23514/ch11_order_shipping_pair_consistent';
SELECT 'legacy_nulls=' || count(*)
FROM shop_private.ch11_order
WHERE shipping_code IS NULL;
