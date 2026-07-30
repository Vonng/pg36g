\set ON_ERROR_STOP on

SELECT *
FROM shop_ch13.capture_payment(
    103,
    0,
    'pay-ch13-wrong',
    1,
    'app-payment'
);
