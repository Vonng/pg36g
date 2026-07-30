\set ON_ERROR_STOP on

SELECT *
FROM shop_ch13.transition_order(
    103,
    0,
    'shipped',
    'app-invalid'
);
