# ADR-018: compose `pg36_shop` as a PostgreSQL-centered data service

- Status: proposed; accepted for lower-volume validation, not production
  approval
- Release: `1.6-proposal`
- Decision owners: shop service owners and database platform team
- Evidence date: 2026-07-29
- PostgreSQL evidence target: 18.4 local development fixture
- Pigsty reference: 4.4; L1 not run

## Context

The upper volume has shown that one PostgreSQL database can enforce relational
invariants, encapsulate short atomic logic, provide lexical and semantic
search, represent spatial and temporal facts, and serve operational analytics.
That breadth creates two opposite architectural mistakes:

1. treating PostgreSQL as a replaceable key/value persistence detail; or
2. treating every installable PostgreSQL extension as a reason to absorb every
   data-system responsibility into one failure and resource domain.

The decision must therefore be made per capability and per data domain. Product
names are downstream details. Authority, consistency, freshness, failure,
rebuild, reconciliation, deletion, and exit are upstream contracts.

## Decision

### Keep authoritative transactional state in PostgreSQL

Orders, inventory, payments, product metadata, and their invariants remain in
`pg36_shop`. Constraints and short database routines may reject invalid state
inside the transaction. Remote calls, unbounded retries, and long-running
orchestration do not run inside those transactions.

### Admit capabilities by lifecycle

| Capability | Placement | Lifecycle |
|---|---|---|
| relational transaction core | PostgreSQL | accepted |
| short atomic database logic | PostgreSQL | accepted with scope |
| lexical and fuzzy product search | PostgreSQL + `pg_trgm` | accepted |
| semantic product search | PostgreSQL + `vector` | pilot |
| spatiotemporal delivery state | PostgreSQL + PostGIS / `btree_gist` | conditional |
| operational analytics | PostgreSQL summaries + offline replica | accepted first step |
| loopback `postgres_fdw` federation | development lab only | not production-admitted |

“Installed” and “production-admitted” are deliberately different states.
Package parity, preload requirements, backup/restore, replication, upgrade,
performance, privileges, and operational ownership must pass the applicable
lower-volume gates.

### Externalize by contract, not by fashion

- A cache may hold a derived product projection; PostgreSQL keeps authority for
  product business state.
- An event bus may own delivery and replay history; the database transaction
  owns the business mutation and outbox publication intent.
- Object storage owns media bytes; PostgreSQL owns stable identity, ownership,
  lifecycle state, and checksum metadata.
- A lakehouse may own an analytical projection; every dataset names a source
  watermark and rebuild path.
- A specialized search system is deferred until a measured quality, scale,
  language, or availability trigger defeats the PostgreSQL baseline.

Each external copy is governed by
`external-data-contracts.json`. No external component becomes a universal
“source of truth”; authority is assigned per data domain.

### Offer services rather than raw instances

The proposed platform catalog contains:

- `pg-dev` for expiring development/test use without an HA promise;
- `pg-ha-standard` for the default production transaction service;
- `pg-ha-critical` for workloads whose explicitly modeled failure domain
  justifies stronger synchronous and isolation controls; and
- `pg-analytics-offline` for stale-tolerant ETL and analytical reads.

The availability, RPO, RTO, and freshness values are objectives to test, not
achievements to advertise.

### Use Pigsty as the reference implementation

Pigsty maps the desired service to a declarative inventory and combines
PostgreSQL with node management, Patroni/etcd coordination, HAProxy service
routing, optional PgBouncer pooling, pgBackRest recovery, and an observability
stack. An offline instance is the reference placement for isolated slow,
interactive, ETL, and OLAP reads.

This mapping is an implementation choice, not part of the data contract.
Changing automation, proxy, monitoring, or backup products must not change
business authority or client-visible service semantics.

## Proposed topology

```text
applications
    |
write/read service contracts
    |
primary + 2 HA replicas ---- offline analytical replica
    |
authoritative PostgreSQL state
    +-- derived cache
    +-- outbox -> event delivery
    +-- immutable media metadata -> object bytes
    +-- versioned analytics/search projections
```

Node count does not prove failure-domain independence. Chapter 19 must identify
the actual host, rack, zone, power, network, storage, and control-plane
dependencies; chapter 20 must then prove election, fencing, and data-loss
behavior.

## Consequences

### Positive

- Strong relational invariants and unified queries stay close to authoritative
  data.
- Feature experiments can begin without prematurely adding a distributed
  system.
- External copies have explicit ownership and can be rebuilt or removed.
- Platform consumers request a service class with bounded semantics rather
  than assemble unreviewed PostgreSQL instances.
- The lower volume receives concrete questions and evidence gates instead of a
  vague “make it production-ready” instruction.

### Costs and risks

- Diverse workloads compete for CPU, memory, workers, WAL, temporary files,
  storage bandwidth, locks, and maintenance windows.
- Every admitted extension expands packaging, security, recovery, replication,
  and upgrade responsibility.
- A shared cluster can turn one workload's saturation into another workload's
  incident unless quotas and isolation are enforced.
- Derived copies introduce lag, duplication, deletion, and reconciliation
  obligations.
- Pigsty reduces implementation toil but cannot supply service ownership,
  threat models, capacity evidence, change approval, or incident judgment.

## Rejected alternatives

### Put every capability in PostgreSQL

Rejected as a universal rule. PostgreSQL may implement a capability but still
fail its independent scaling, availability, retention, cost, or operational
boundary.

### Split every capability into a specialized product immediately

Rejected. It spends network, consistency, delivery, observability, and staffing
complexity before evidence shows that the simpler PostgreSQL baseline is
insufficient.

### Treat the loopback FDW lab as distributed production proof

Rejected. It does not model network delay, remote authentication, independent
failure, operational ownership, or shard rebalance. Its
`password_required=false` mapping is explicitly lab-only.

### Declare Pigsty installation equivalent to production readiness

Rejected. Installation is implementation convergence. Readiness additionally
requires the chapters 19–36 evidence package and accountable owners.

## Validation and revision

The proposal advances only by passing the gates in
`lower-volume-gates.json`. A failed capacity, recovery, security, or lifecycle
gate may:

1. change an extension lifecycle;
2. move a capability outside PostgreSQL;
3. require a dedicated cluster or service class;
4. revise an SLO; or
5. trigger a new distribution ADR.

The ADR must be revisited whenever authority changes, an externalization trigger
fires, a service objective changes, a major PostgreSQL/Pigsty/extension version
changes, or an incident disproves an assumption.
