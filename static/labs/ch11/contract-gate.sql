\set ON_ERROR_STOP on
\pset pager off
\ir context.sql

\if :{?contract_token}
\else
  \set contract_token ''
\endif
\if :{?contract_target}
\else
  \set contract_target ''
\endif
\if :{?observation_evidence}
\else
  \set observation_evidence ''
\endif

SELECT
    :'contract_token' =
        'CONTRACT_CH11_AFTER_OBSERVATION' AS token_ok,
    :'contract_target' =
        'pg36_shop/shop_private/ch11_order/shipping_method'
        AS target_ok,
    :'observation_evidence' =
        'legacy-readers=0;legacy-writers=0;rollback-window=elapsed'
        AS observation_ok
\gset

\if :token_ok
\else
  DO $contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3612',
          MESSAGE =
              'contract refused: explicit action token is missing';
  END
  $contract_error$;
\endif
\if :target_ok
\else
  DO $contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3612',
          MESSAGE =
              'contract refused: exact target identity is missing';
  END
  $contract_error$;
\endif
\if :observation_ok
\else
  DO $contract_error$
  BEGIN
      RAISE EXCEPTION USING
          ERRCODE = 'P3612',
          MESSAGE =
              'contract refused: observation evidence is missing';
  END
  $contract_error$;
\endif

DO $state_guard$
BEGIN
    IF (
        SELECT phase
        FROM shop_private.ch11_migration_state
        WHERE migration_id = 'shipping-code-v1'
    ) IS DISTINCT FROM 'switched' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P3612',
            MESSAGE = 'contract refused: release is not switched';
    END IF;
END
$state_guard$;

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';

DROP TRIGGER ch11_order_shipping_bridge
ON shop_private.ch11_order;
DROP FUNCTION shop_private.ch11_sync_shipping_code();
ALTER TABLE shop_private.ch11_order
    DROP CONSTRAINT ch11_order_shipping_pair_consistent;
ALTER TABLE shop_private.ch11_order
    DROP COLUMN shipping_method;

COMMIT;

\pset format unaligned
\pset tuples_only on
SELECT 'status=ok';
SELECT 'contract=executed';
