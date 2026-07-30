# ch03 to ch04 decision register

| Decision | Known fact | Still unresolved | ch04 acceptance evidence |
|---|---|---|---|
| Money | Order lines preserve purchase-time price; payment records an attempted amount | numeric vs minor units, currency, scale, rounding, refunds | Invalid scale and currency cases fail with documented SQLSTATE |
| Time | Order placement and payment occurrence are instants | business zone, precision, clock source, future/past bounds | Round-trip examples cover DST and client zones |
| Status | Order and payment state are different domains | allowed values, transitions, terminal states, representation | Invalid value and invalid transition are independently rejected |
| Identifier | Internal, business, idempotency, provider, and trace IDs have different meanings | bigint vs UUID, generation owner, ordering, exposure | Concurrent generation and duplicate cases are tested |

The v0 schema is intentionally not a production DDL. A decision is closed only
when its semantics, enforcement layer, error behavior, migration path, and
verification query are all recorded.
