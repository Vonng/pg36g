\set ON_ERROR_STOP on

SELECT *
FROM shop_ch13.transition_order(
    104,
    0,
    'paid',
    'app-no-payment'
);
