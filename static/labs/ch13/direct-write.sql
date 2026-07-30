\set ON_ERROR_STOP on

UPDATE shop_ch13.sales_order
SET
    status = 'canceled',
    version = version + 1
WHERE order_id = 105;
