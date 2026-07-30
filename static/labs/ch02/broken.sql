\set ON_ERROR_STOP on
\ir context.sql

INSERT INTO shop.ch02_fixture (fixture_id, sku, label, amount, payload)
VALUES (999, 'SKU-0999', 'must-be-rolled-back', 9.99, md5('broken'));

SELEC 'intentional syntax error: the previous row must roll back';
