\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

DO $precheck$
BEGIN
    IF (
        SELECT phase
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM 'validated' THEN
        RAISE EXCEPTION 'switch requires validated phase';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM shop_private.ch11_order
        WHERE shipping_code IS DISTINCT FROM
              CASE shipping_method
                  WHEN 'standard' THEN 'STD'
                  WHEN 'express' THEN 'EXP'
                  WHEN 'pickup' THEN 'PUP'
              END
    ) THEN
        RAISE EXCEPTION 'shadow-read comparison found a mismatch';
    END IF;
END
$precheck$;

-- Rollback window probe: an old writer still succeeds after the new read path.
INSERT INTO shop_private.ch11_order (
    order_id,
    order_ref,
    shipping_method,
    created_at,
    payload
)
VALUES (
    90004,
    'ch11-old-writer-after-switch',
    'express',
    timestamptz '2025-03-01 00:00:03+00',
    'old writer remains compatible during rollback window'
);

-- New writer keeps dual-writing until contract is separately approved.
INSERT INTO shop_private.ch11_order (
    order_id,
    order_ref,
    shipping_method,
    shipping_code,
    created_at,
    payload
)
VALUES (
    90005,
    'ch11-new-writer-after-switch',
    'standard',
    'STD',
    timestamptz '2025-03-01 00:00:04+00',
    'new writer still dual-writes during rollback window'
);

UPDATE shop_private.ch11_migration_state
   SET phase = 'switched',
       switched_at = pg_catalog.clock_timestamp(),
       updated_at = pg_catalog.clock_timestamp()
 WHERE migration_id = 'shipping-code-v1';

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'phase=switched';
SELECT 'shadow_mismatches=' || count(*)
FROM shop_private.ch11_order
WHERE shipping_code IS DISTINCT FROM
      CASE shipping_method
          WHEN 'standard' THEN 'STD'
          WHEN 'express' THEN 'EXP'
          WHEN 'pickup' THEN 'PUP'
      END;
SELECT 'rollback_window=legacy-column+bridge-retained';
SELECT 'contract=not-executed';
