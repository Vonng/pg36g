# ADR: transaction-scoped tenant identity with forced RLS

- Status: accepted for the chapter fixture; production transport gate pending
- Scope: synthetic `pg36_ch23` workload on `pg-test`

## Decision

Use an authenticated login only to enter the database. Inside every application
transaction:

1. `BEGIN`;
2. `SET LOCAL ROLE pg36_ch23_runtime`;
3. bind the already authorized tenant UUID with
   `set_config('app.tenant_id', $1, true)`;
4. execute tenant SQL;
5. `COMMIT`.

The owner, migration, runtime, and read-only roles cannot log in. The login may
`SET` runtime and read-only roles but does not inherit them and cannot delegate
them. The migration role may `SET` the owner role but neither inherits nor
delegates it.

The table has both `ENABLE ROW LEVEL SECURITY` and
`FORCE ROW LEVEL SECURITY`. Separate `USING` and `WITH CHECK` policies apply to
reads and writes. Missing context returns no rows; malformed UUID context
raises an error; cross-tenant insert and update fail.

## Why

PgBouncer transaction pooling does not preserve a client-to-server session
mapping. A session-level `SET` can remain on a reused server connection when
`server_reset_query_always=0`; the next client can inherit it. Transaction-local
role and tenant state automatically expires at commit or rollback and matches
the pool's ownership boundary.

RLS is defense in depth, not authentication. The application must derive the
tenant from an authenticated, authorized identity rather than copy an
unverified request parameter into the GUC.

## Alternatives rejected

- One login role owns all objects: owner bypass, migration authority, and
  runtime authority collapse into one credential.
- One schema per tenant: useful for some isolation and lifecycle requirements,
  but operationally heavier and not a replacement for this shared-table case.
- Application `WHERE tenant_id = $1` only: easy to omit in one query and does
  not constrain direct SQL paths.
- Session-level `SET app.tenant_id`: incompatible with transaction pooling and
  formally reproduced as a leak.
- `DISCARD ALL` as the sole control: reset behavior depends on pool mode and
  configuration; correctness should be transactional, not cleanup-dependent.

## Consequences

- Every code path, including background jobs, must open an explicit
  transaction and establish both role and tenant.
- Table owners still need forced RLS; superusers and `BYPASSRLS` remain
  break-glass identities outside this boundary.
- Migration tooling needs a separate endpoint and identity contract.
- Pool-mode changes, driver behavior, policy changes, and role-graph changes
  require the chapter tests to be rerun.
- Transport security is independent. This ADR remains valid even though the
  retained sandbox fails the production TLS gate.
