\set ON_ERROR_STOP on
\pset pager off

UPDATE shop_ch16.delivery_event
SET event_type = 'tampered'
WHERE event_id = 'e001';
