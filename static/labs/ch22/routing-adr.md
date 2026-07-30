# ADR-22: test semantic service endpoints through the delivered data path

- Status: accepted for the chapter-22 sandbox reference run
- Production approval: no
- Depends on: chapter 19 deployment baseline and chapter 20 HA model

## Context

The retained `pg-test` cluster exposes TCP ports 5432, 5433, 5434, 5436, 5438,
6432 and Patroni 8008 on each member. Reachability alone does not identify:

- which role a service selects;
- whether a connection is pooled or direct;
- whether session state is preserved;
- how many PostgreSQL backends concurrent clients consume;
- what a replica read can observe;
- what clients see across a role transition.

The chapter needs an end-to-end experiment that starts at the client endpoint,
cross-checks HAProxy/PgBouncer/PostgreSQL evidence and preserves the
nonproduction teaching baseline.

## Decision

Use the four default Pigsty services through one HAProxy entry node:

```text
5433 primary -> PgBouncer -> writable leader
5434 replica -> PgBouncer -> preferred replicas
5436 default -> direct PostgreSQL -> writable leader
5438 offline -> direct PostgreSQL -> pg-test-3
```

Use the Pigsty-declared nonproduction `test` login and its `test/test`
PgBouncer pool, which is otherwise idle in the retained sandbox. A dynamically
created PostgreSQL role is intentionally insufficient because Pigsty manages
PgBouncer's authentication surface separately. Temporarily reduce one
process's pool to two server connections, run deterministic
queue/session/prepared experiments, and restore the runtime settings before
changing database roles.

Then run a modest reconnecting write probe across one forward and one reverse
planned switchover. After each role convergence, refresh the teaching database
pool on all members and require a subsequent acknowledgement. Reconcile
commits by token and finish with the original leader.

## Why not connect directly to member IPs

Direct connections prove a member property, not a service contract. The
primary and replica probes must traverse HAProxy and, where declared,
PgBouncer. Direct port 5436 is tested separately because it intentionally
bypasses pooling.

## Why use a runtime pool override

The delivered default pool is 50 plus a reserve of 30. Saturating it would need
a noisier workload and would teach less. A two-slot dedicated user/database
pool makes queueing and backend reassignment deterministic.

The override is accepted only because:

- the target is an exact nonproduction sandbox;
- no production traffic exists;
- the original changeable values are captured;
- a `finally` handler restores and verifies them;
- the switch phase cannot begin until restoration passes.

This is not a replacement for declaring per-database/user budgets in Pigsty.

The run also performs `RECONNECT test` on every member before measuring endpoint
semantics. A retained server pool on `pg-test-2` was observed to reject
`target_session_attrs=read-only` after an earlier role cycle even though direct
PostgreSQL evidence showed recovery/read-only state. Recycling that database
pool restored the contract. This makes post-role-change pool refresh and
endpoint revalidation an explicit operational responsibility.

## Why test both prepared statement forms

PgBouncer 1.25.2 with `max_prepared_statements=256` rewrites and tracks
protocol-level named prepared statements. Psycopg can therefore use server
prepare through transaction pooling in this exact version matrix.

SQL text commands `PREPARE`, `EXECUTE` and `DEALLOCATE` are not rewritten. A
prepared name created on one backend may be absent on the next. The experiment
forces that reassignment and requires the expected failure, preventing the
book from repeating the obsolete blanket claim that “prepared statements
never work” or the equally unsafe claim that all prepared statements work.

## Why test session-state leakage

Transaction pooling releases the backend after each transaction.
`server_reset_query=DISCARD ALL` is configured, but
`server_reset_query_always=0`; PgBouncer does not promise arbitrary SQL
session state in transaction mode. A forced reassignment makes both failure
directions visible:

- the original client cannot rely on its `search_path`;
- another client can receive the backend carrying that state.

The safe pattern is startup parameters explicitly tracked by PgBouncer,
transaction-local `SET LOCAL`, fully qualified names, or a reviewed
session/direct endpoint.

## Why one replica visibility sample

The cluster is asynchronous. A token usually becomes visible quickly in the
local sandbox, but port 5434 cannot promise read-your-writes without an
explicit consistency protocol. Measuring one commit-LSN/replay-LSN path makes
the delay observable while an exception blocks generalization.

## Why another planned switch

Chapter 20 proved HA control and one client stream. Chapter 22 asks a different
question: whether the semantic primary service plus short-lived reconnecting
clients, jitter and PgBouncer survive role changes. The switch remains healthy
and planned; no failure or fencing claim is added.

## Alternatives rejected

### Saturate `max_connections`

Rejected. Exhausting 500 PostgreSQL slots is unnecessary and risks losing
administrative access. The chapter should demonstrate queueing before the
database ceiling, not create an outage.

### Edit `/etc/pgbouncer/pgbouncer.ini`

Rejected for the experiment. That would create configuration-management drift
and require a file rollback/reload. Runtime `SET` is bounded, observable and
restored, while the production recommendation remains declarative.

### Use only `SHOW POOLS`

Rejected. Admin counters do not prove the user-visible result or endpoint role.
Client results and PostgreSQL facts are required.

### Claim consistency from zero lag

Rejected. A metric sample of zero and a fast token read are observations, not
an asynchronous-replication guarantee.

### Inject an unplanned failure

Rejected. The current watchdog/fencing and single-DCS exceptions remain. An
unplanned failure needs separate authority and a failure-specific client
contract.

## Consequences

The experiment yields direct evidence for role selection, queueing, versioned
prepared-statement support, session hazards, asynchronous visibility and
planned reconnect behavior.

It also leaves explicit gaps:

- one HAProxy entry address;
- client TLS disabled on PgBouncer;
- laptop-scale synthetic load;
- one PgBouncer runtime override rather than a declared multi-node policy;
- planned switch only;
- no production driver/ORM matrix.
