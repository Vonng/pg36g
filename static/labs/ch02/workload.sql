\set fixture_id random(1, 100)
BEGIN;
SET LOCAL ROLE pg36_owner;
SELECT payload
FROM shop.ch02_fixture
WHERE fixture_id = :fixture_id;
COMMIT;
