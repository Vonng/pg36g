# ADR-020: accept planned switchover behavior, not automatic failover

- Status: accepted with ten named sandbox exceptions
- Production gate: pending
- Release: `1.0-sandbox`
- PostgreSQL: 18.4
- Pigsty: v4.4.0
- Patroni: 4.1.3
- Scope: `pg36-l2-vagrant/pg-test`

## Context

Chapter 19 established that one declared Pigsty topology exists: one primary,
two streaming replicas, stable initialization choices, and observable service
endpoints. Static topology does not answer the questions that matter during a
role transition:

- Which failure is being handled?
- Who may choose a new writable history?
- What commit acknowledgement policy defines the data-loss envelope?
- How do clients find the new primary?
- What happens to in-flight transactions whose outcome is unknown?
- Does the old primary rejoin the chosen history?
- Can the final evidence distinguish a planned transition from a crash?

The sandbox cannot safely establish every answer in one chapter. All guests
share a laptop, the DCS is a single etcd member, the cluster is asynchronous,
and watchdog fencing is off. The useful decision is therefore narrower.

## Decision

### Start with an explicit failure model

Record nine distinct scenarios before operating the cluster. This chapter
observes only healthy planned primary maintenance. Process crash, host loss,
storage fault, network partition, DCS loss, and common-hypervisor failure
remain untested. Logical corruption is a recovery problem, not a replica
promotion problem.

### Keep the deployed asynchronous policy visible

Do not silently enable synchronous replication merely to obtain a more
attractive laboratory result. Capture `synchronous_mode=false`,
`synchronous_mode_strict=false`, `synchronous_standby_names=''`, active physical
slots, `use_pg_rewind=true`, `wal_log_hints=on`, and
`full_page_writes=on`.

This documents the actual durability/availability trade rather than presenting
a configuration recipe detached from evidence.

### Name both leader and candidate

Use Patroni's planned `switchover` operation with an explicit current leader
and candidate. Do not use `failover`, do not promote `pg-test-3`, and do not
allow an implicit candidate choice in this exercise.

After the forward action, require `pg-test-2` to be the sole leader and require
the old primary to return as a streaming replica. Then execute a second planned
switchover back to `pg-test-1`, preserving the chapter 19 teaching baseline.

### Observe lineage at two layers

Require all SQL endpoints to retain one system identifier across all phases.
Require the cluster timeline to advance on each switchover and require the
primary's WAL-derived current timeline to match Patroni.

Preserve the checkpoint timeline as a separate field. A live experiment showed
that one standby's control-file checkpoint timeline remained at 1 while the
member was correctly streaming on later timelines. The checkpoint value is
valid checkpoint evidence, not a generic current-timeline oracle.

### Measure through the client service

Write synthetic idempotency tokens through Pigsty's read-write service rather
than directly to whichever member the test already believes is primary.
Record monotonic client timings around the transition. Reconcile acknowledged
and outcome-unknown tokens after the service stabilizes.

The conservative gap is an observed sampled interruption. It is not called
RTO because no unplanned detection/election path ran, and it is not called an
SLO because one local run does not establish a distribution.

### Keep mutation and verification separate

`task.sh all` verifies and reviews existing evidence only.
`drill:switchover` requires explicit L2 guards and a new empty evidence
directory. `reset:fixture` is a separate destructive action. No ordinary
validation command is allowed to move a leader.

## Evidence decision

The formal reference run must show:

- one system identifier through three successive timelines;
- exact forward and restore leader/candidate identities;
- two streaming replicas after each stable transition;
- every acknowledged token present;
- every unknown outcome reconciled;
- no duplicate token;
- a conservative write gap inside the 15-second sandbox objective;
- ten deliberately corrupted cases rejected;
- chapter 19 acceptance before and after the drill; and
- zero exported secret values.

When these conditions hold, accept only:

```text
sandbox_planned_switchover=accepted-with-exceptions
unplanned_failure_drill=not-run
production_ch20_gate=pending
```

## Consequences

### Positive

- The reader sees HA as a failure-model and evidence problem, not a node-count
  label.
- The run connects PostgreSQL WAL lineage, Patroni authority, Pigsty service
  routing, and client commit semantics.
- A sampled client interruption cannot be confused with command duration.
- Baseline restoration is part of the contract, so later chapters inherit a
  known topology.
- The negative suite prevents several common overclaims from passing review.

### Costs and limits

- Two planned switchovers increment the timeline twice.
- The probe fixture writes synthetic rows and must be separately removed if
  cleanup is desired.
- Physical slots can retain WAL and require independent monitoring.
- No result qualifies host failure, fencing, DCS quorum, storage durability,
  split brain, or zero RPO.
- The external probe path's lack of TLS is unacceptable as a production
  security conclusion.

## Rejected alternatives

### Kill the leader to make the chapter look more realistic

Rejected for this gate. An unplanned fault adds fencing, common failure-domain,
and data-loss questions that the single-etcd/no-watchdog sandbox cannot answer
honestly without a broader authorization and runbook.

### Report `patronictl` command duration as RTO

Rejected. Command return, stable topology, first successful client write, and
application recovery are different clocks.

### Infer zero RPO because no acknowledged token was missing

Rejected. Asynchronous replication can lose an unreplicated tail after an
unplanned primary loss. A healthy switchover intentionally waits for an
eligible candidate and does not exercise that loss window.

### Retry every connection error

Rejected. An error after send has an unknown commit outcome. Blind retry can
duplicate a business operation; token reconciliation is required.

### Use checkpoint timeline as current standby timeline

Rejected after direct observation. Checkpoint metadata may lag replay. The
field remains useful when accurately named.

### Let `all` rerun the live transition

Rejected. Evidence verification must be safe to repeat and cannot surprise an
operator with a leader change.

## Revision triggers

Revisit this ADR when synchronization mode, DCS topology, watchdog/fencing,
service routing, member placement, PostgreSQL major version, Pigsty/Patroni
release, RPO/RTO objective, or production authority changes. Replace the
decision rather than stretching this sandbox result to cover a new target.
