\set ON_ERROR_STOP on

SELECT *
FROM shop_ch13.transition_order(
    101,
    0,
    'expired',
    'app-stale'
);
