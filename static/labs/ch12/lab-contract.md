# ch12 reference service lab contract

## Scope

This lab runs one Go reference API against the dedicated `shop_ch12` schema in
the `pg36_shop` teaching database. The API connects as `pg36_app`; setup,
observation, verification, and reset connect through the reviewed administrative
service. The fixture never mutates the chapter 4 business tables.

The service demonstrates:

- atomic inventory reservation and order creation;
- request and payment idempotency with payload fingerprints;
- an outbox record committed with each business transition;
- stable parameterized read queries;
- bounded whole-transaction retry for `40001`;
- request cancellation, database statement timeout, and pool acquisition
  timeout as different failure classes;
- liveness, readiness, structured logs, and low-cardinality metrics.

It does not call a payment provider, publish an outbox event, manage secrets, or
claim a high-availability test. Those are explicit production boundaries, not
omitted implementation details.

## Preconditions

- PostgreSQL 14 or later;
- database `pg36_shop` with the verified ch04-v1 model;
- constrained roles `pg36_owner` and `pg36_app`;
- a `PGSERVICEFILE` entry selected by `PGSERVICE`;
- Go 1.25 or later for the frozen pgx v5.10.0 sample.

The local suite validates the driver and application-side `pgxpool` through a
direct PostgreSQL endpoint. A v1.0 promotion still requires the same suite
through the declared Pigsty primary/PgBouncer endpoint and the PostgreSQL
14–18 matrix.

## Isolation and destructive boundary

`setup.sql` may rebuild only schema `shop_ch12`, and only if the schema carries
the exact lab marker and no API session remains. `reset.sql` additionally
requires:

```text
PG36_RESET_TOKEN=RESET_CH12_SERVICE_LAB
PG36_RESET_TARGET=pg36_shop/shop_ch12
```

Reset refuses an unmarked schema, unknown table, sequence, or function, and any
remaining `application_name=pg36-ch12-api` database session. It does not drop a
database, role, extension, or any object outside `shop_ch12`.

## Deterministic final state

The acceptance workload creates two orders and one payment:

| object | accepted state |
|---|---|
| `PG36-SKU-001` | available `8`, version `1` |
| `PG36-SKU-002` | available `4`, version `1` |
| orders | `2` |
| payments | `1` |
| outbox events | `3` |
| successful order requests | `2` |
| successful payment requests | `1` |

Replays, mismatched idempotency payloads, insufficient inventory, statement
timeout, client cancellation, and pool exhaustion must not add business rows.
The chapter 4 checksum must remain
`f8a7bfae59c6d16cd323abecfefe1014`.

## Stop conditions

Stop and preserve evidence if any of these occurs:

- the target database, role, model marker, or writable-instance guard fails;
- the API acquires DDL or `DELETE` privilege;
- an injected failure changes inventory, orders, payments, or outbox counts;
- a retry duplicates a write or external side effect;
- a client-cancelled database worker remains active;
- liveness depends on a database connection;
- the connection path or pool mode cannot be identified.

Do not relax a timeout, widen a role, or edit an expected count merely to make
the review pass.
