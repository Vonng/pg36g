# Chapter 23 security lab contract

## Purpose

This L2 lab proves a narrow security contract on the retained
`pg36-l2-vagrant/pg-test` sandbox:

- a login identity is separated from owner, migration, runtime, and read-only
  roles;
- forced row-level security isolates two synthetic tenants;
- transaction-local role and tenant context survives PgBouncer transaction
  pooling without leaking into the next transaction;
- a deliberately unsafe session-level setting is reproduced as a
  counterexample;
- direct TLS, certificate-name verification, SCRAM channel binding, password
  rotation, `NOLOGIN`, and the separate PgBouncer authentication surface are
  observed;
- all known production gaps remain visible.

The lab does **not** claim certification, rotate a CA, change HBA, change a
firewall, read a private key, or use production data.

## Authority and mutation boundary

`task.sh drill:security` requires all of the following exact guards:

```text
PG36_CH23_TARGET=pg36-l2-vagrant/pg-test
PG36_CH23_NONPRODUCTION=true
PG36_CH23_SYNTHETIC_DATA_ONLY=true
PG36_CH23_PRODUCTION_TRAFFIC=false
PG36_CH23_CONFIRM=SECURITY_RLS_ROTATION_CH23
```

It also requires a private mode-`0600` Pigsty inventory outside the source tree.
The inventory is used only to authenticate the already declared `test` login.
The projection records structure and redaction flags, never its credential.

The drill may:

1. retain five clearly commented, non-login synthetic roles;
2. retain one clearly commented schema with four synthetic rows;
3. add two non-inheriting, non-admin `SET ROLE` memberships to the existing
   `test` sandbox login without changing that login's attributes or password;
4. temporarily set the primary PgBouncer pool size for database `test` to one;
5. temporarily enable and rotate one direct-only synthetic login.

The PgBouncer settings are restored exactly and all three pools are
`RECONNECT`ed. The rotation role finishes as `NOLOGIN PASSWORD NULL`. Patroni
topology is never changed. The bounded fixture remains so the chapter can be
re-run and inspected.

## Evidence semantics

Evidence files are mode `0600`. They can contain:

- public certificate metadata and fingerprints;
- HBA projections;
- safe role attributes and membership options;
- table grants, policy expressions, row counts, SQLSTATEs, backend PIDs, and
  endpoint observations.

They must not contain:

- passwords or SCRAM verifiers;
- a PgBouncer raw userlist;
- server or CA private keys;
- raw customer data;
- exception text that might repeat a connection string.

`sslmode=require` proves encryption, not server identity. Only the named
`verify-full` case is accepted as server-identity evidence. An existing session
remaining usable after password change or `NOLOGIN` is an observation, not an
endorsement.

## Production gate

The expected production gate is `pending`. The retained sandbox exposes at
least these gaps:

- ordinary intranet business HBA records are `host`, not `hostssl`;
- PgBouncer client TLS is disabled;
- CRL inputs are unset;
- client CA distribution and certificate rotation are not exercised here;
- pgAudit is absent;
- some non-error statement logs may retain complete bind parameters.

The lab passes only when it detects these gaps and refuses to translate them
into a production approval.

## Destructive reset

No normal action calls reset. `task.sh reset:fixture` additionally requires:

```text
PG36_CH23_TARGET=pg36-l2-vagrant/pg-test
PG36_CH23_NONPRODUCTION=true
PG36_CH23_SYNTHETIC_DATA_ONLY=true
PG36_CH23_RESET_CONFIRM=DROP_CH23_SYNTHETIC_SECURITY_FIXTURE
```

Reset checks exact schema ownership, comments, role comments, and absence of
active synthetic-role sessions. It then removes only schema `pg36_ch23`, the
five synthetic roles, and the memberships introduced by this lab. It preserves
the declared `test` login and every non-fixture object.
