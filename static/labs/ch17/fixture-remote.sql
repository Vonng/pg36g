INSERT INTO shop_ch17_shard.fixture_meta (
    fixture_version,
    generator_identity,
    shard_modulus,
    shard_remainder,
    tenant_count,
    accounts_per_tenant,
    day_count,
    sales_per_account_day,
    first_day,
    frozen_at
)
VALUES (
    'ch17-analytics-v1',
    'fixture-generator-v1',
    2,
    :shard_remainder,
    8,
    50,
    120,
    5,
    DATE '2026-01-01',
    TIMESTAMPTZ '2026-07-29 00:00:00+00'
);

INSERT INTO shop_ch17_shard.account_dim (
    tenant_id,
    account_id,
    segment,
    region
)
SELECT
    tenant_id,
    account_id,
    (
        ARRAY[
            'enterprise',
            'growth',
            'small'
        ]::text[]
    )[1 + pg_catalog.mod(account_id - 1, 3)],
    (
        ARRAY[
            'east',
            'central',
            'west',
            'international'
        ]::text[]
    )[1 + pg_catalog.mod(tenant_id - 1, 4)]
FROM pg_catalog.generate_series(1, 8) AS tenant(tenant_id)
CROSS JOIN pg_catalog.generate_series(1, 50)
    AS account(account_id)
WHERE pg_catalog.mod(tenant_id, 2) = :shard_remainder
ORDER BY tenant_id, account_id;

INSERT INTO shop_ch17_shard.sales_fact (
    sale_id,
    tenant_id,
    account_id,
    occurred_on,
    channel,
    units,
    amount
)
SELECT
    (
        (
            (
                (
                    (tenant_id - 1) * 50 +
                    (account_id - 1)
                ) * 120 +
                day_index
            ) * 5
        ) + slot
    )::bigint AS sale_id,
    tenant_id,
    account_id,
    DATE '2026-01-01' + day_index AS occurred_on,
    (
        ARRAY[
            'direct',
            'partner',
            'web'
        ]::text[]
    )[
        1 + pg_catalog.mod(
                tenant_id + account_id + day_index + slot,
                3
            )
    ] AS channel,
    (
        1 + pg_catalog.mod(
                tenant_id * 7 +
                account_id * 3 +
                day_index +
                slot,
                9
            )
    )::smallint AS units,
    (
        (
            pg_catalog.mod(
                tenant_id * 100 +
                account_id * 7 +
                day_index * 3 +
                slot * 11,
                50000
            ) + 100
        )::numeric / 100
    )::numeric(12,2) AS amount
FROM pg_catalog.generate_series(1, 8) AS tenant(tenant_id)
CROSS JOIN pg_catalog.generate_series(1, 50)
    AS account(account_id)
CROSS JOIN pg_catalog.generate_series(0, 119)
    AS day(day_index)
CROSS JOIN pg_catalog.generate_series(1, 5) AS event(slot)
WHERE pg_catalog.mod(tenant_id, 2) = :shard_remainder
ORDER BY sale_id;
