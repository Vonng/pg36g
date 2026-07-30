\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

DO $precheck$
DECLARE
    current_phase text;
BEGIN
    SELECT phase
      INTO current_phase
      FROM shop_private.ch11_migration_state
     WHERE migration_id = 'shipping-code-v1'
     FOR UPDATE;

    IF current_phase IS DISTINCT FROM 'legacy' THEN
        RAISE EXCEPTION
            'expand expected legacy phase, found %',
            current_phase;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute
        WHERE attrelid =
              'shop_private.ch11_order'::regclass
          AND attname = 'shipping_code'
          AND attnum > 0
          AND NOT attisdropped
    ) THEN
        RAISE EXCEPTION
            'expand refused: shipping_code already exists';
    END IF;
END
$precheck$;

ALTER TABLE shop_private.ch11_order
    ADD COLUMN shipping_code text;

CREATE FUNCTION shop_private.ch11_sync_shipping_code()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    expected_code text;
BEGIN
    expected_code := CASE NEW.shipping_method
        WHEN 'standard' THEN 'STD'
        WHEN 'express'  THEN 'EXP'
        WHEN 'pickup'   THEN 'PUP'
        ELSE NULL
    END;

    IF expected_code IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            CONSTRAINT =
                'ch11_order_shipping_method_check',
            MESSAGE = 'unknown shipping_method';
    END IF;

    IF TG_OP = 'UPDATE'
       AND NEW.shipping_method IS DISTINCT FROM OLD.shipping_method
       AND NEW.shipping_code IS NOT DISTINCT FROM OLD.shipping_code THEN
        NEW.shipping_code := expected_code;
    ELSIF NEW.shipping_code IS NULL THEN
        NEW.shipping_code := expected_code;
    ELSIF NEW.shipping_code IS DISTINCT FROM expected_code THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            CONSTRAINT =
                'ch11_order_shipping_pair_consistent',
            MESSAGE = 'shipping_method and shipping_code disagree';
    END IF;

    RETURN NEW;
END
$function$;

COMMENT ON FUNCTION shop_private.ch11_sync_shipping_code() IS
    'pg36 ch11 deterministic release lab; safe to rebuild';

CREATE TRIGGER ch11_order_shipping_bridge
BEFORE INSERT OR UPDATE
ON shop_private.ch11_order
FOR EACH ROW
EXECUTE FUNCTION shop_private.ch11_sync_shipping_code();

ALTER TABLE shop_private.ch11_order
    ADD CONSTRAINT ch11_order_shipping_pair_consistent
    CHECK (
        shipping_code IS NULL
        OR (
            (shipping_method = 'standard' AND shipping_code = 'STD')
            OR
            (shipping_method = 'express' AND shipping_code = 'EXP')
            OR
            (shipping_method = 'pickup' AND shipping_code = 'PUP')
        )
    )
    NOT VALID;

UPDATE shop_private.ch11_migration_state
   SET phase = 'expanded',
       expanded_at = pg_catalog.clock_timestamp(),
       updated_at = pg_catalog.clock_timestamp()
 WHERE migration_id = 'shipping-code-v1';

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'phase=' || phase
FROM shop_private.ch11_migration_state
WHERE migration_id = 'shipping-code-v1';
SELECT 'legacy_nulls=' || count(*)
FROM shop_private.ch11_order
WHERE shipping_code IS NULL;
SELECT 'bridge_trigger=' ||
       CASE
           WHEN EXISTS (
               SELECT 1
               FROM pg_catalog.pg_trigger
               WHERE tgrelid =
                     'shop_private.ch11_order'::regclass
                 AND tgname = 'ch11_order_shipping_bridge'
                 AND NOT tgisinternal
           )
           THEN 'present'
           ELSE 'absent'
       END;
