\set ON_ERROR_STOP on
\pset pager off

SELECT *
FROM shop_ch13.order_snapshot(101);

SELECT *
FROM shop_ch13.transition_order(
    101,
    0,
    'canceled',
    'app-cancel'
);

SELECT *
FROM shop_ch13.capture_payment(
    102,
    0,
    'pay-ch13-102',
    2000,
    'app-payment'
);

SELECT *
FROM shop_ch13.order_snapshot(102);
