# ADR-21: prove recoverability with an isolated named-point restore

- Status: accepted for the chapter-21 sandbox reference run
- Scope: `pg36-l2-vagrant/pg-test`
- Production approval: no

## Context

The retained teaching cluster already streams to two replicas and archives WAL
through pgBackRest into one MinIO repository. Those facts are necessary but
insufficient. Streaming replicas reproduce many operator mistakes, while an
`ok` backup catalog does not prove that the selected backup, WAL, configuration
and procedure can start a database and recover the intended business state.

The chapter needs an executable proof without overwriting the source cluster
or pretending that a small Vagrant result is a production guarantee.

## Decision

For every formal run:

1. pass the chapter-19 deployment gate;
2. insert a `base` marker;
3. take a new full pgBackRest backup;
4. insert `keep`, create a named restore point, then insert `discard`;
5. force and verify WAL archival;
6. restore the exact backup to that named point below a fresh path on
   `pg-test-3`;
7. start a separate Unix-socket-only postmaster with archive push disabled;
8. wait beyond read-only availability until promotion is complete;
9. prove that `base` and `keep` exist, `discard` does not, lineage matches,
   and a rollback-only write succeeds;
10. stop the isolated postmaster, retain its directory, and pass the
    chapter-19 postflight gate.

The live `pg-test-3` replica remains under Patroni on port 5432 throughout.

## Why a named point

A named point makes the intended transaction boundary unambiguous in a
teaching lab. It avoids wall-clock ambiguity, time-zone mistakes and “closest
visible row” reasoning. A production plan must also exercise time, LSN and
inclusive/exclusive semantics where those target forms are used.

## Why a fresh full backup

A fresh backup makes the evidence bundle self-contained: the runner can prove
which marker preceded the backup, which exact backup label was restored, and
which later WAL carried the recovery target. It does not imply that every
production run should take a full backup. Full, differential and incremental
cadence belongs to a capacity-and-retention design.

## Why restore on a replica host

The local sandbox has no unused fourth database guest. `pg-test-3` has adequate
free space, so a separate data directory and postmaster provide a useful
process and network-isolation exercise. This is explicitly accepted as
`EX21-SHARED-RESTORE-HOST`; it cannot prove host or failure-domain isolation.
Production restore tests should use infrastructure that cannot collide with a
live database member.

## Why archive mode is off

PITR creates a new timeline. A verification instance must not publish that
fork into the source repository. pgBackRest's restore option writes
`archive_mode=off` into the recovered configuration, and the runner verifies
the effective setting after promotion.

## Why “ready” has two timestamps

The development run exposed a subtle but important behavior. PostgreSQL logged
“ready to accept read-only connections” at the consistent recovery point,
then selected the new timeline and logged “ready to accept connections”
roughly 0.39 seconds later. `pg_ctl -w` can observe the first event. Therefore
the formal contract treats `pg_is_in_recovery() = false` plus a rollback-only
write probe as the completion event.

The same development run also rejected `max_connections=20` because the WAL
recorded `500` on the primary. That failure is retained as a teaching result,
not normalized away. The formal runner carries forward all
recovery-critical maxima captured from the source.

## Alternatives rejected

### Restore over `/pg/data`

Rejected. It would overwrite or collide with the live Patroni member and turn
a verification exercise into a destructive replacement procedure.

### Promote a streaming replica

Rejected as a backup test. Promotion proves a replication path, not that a
particular base backup and archive chain can satisfy a historical recovery
boundary.

### Trust `pgbackrest info` and `check`

Rejected as sufficient evidence. Catalog and archive checks do not execute the
restore path, PostgreSQL recovery, promotion, or business invariant checks.

### Use a logical dump

Rejected for this experiment. Logical export is valuable for selective
recovery and portability but cannot validate a physical base-backup/WAL PITR
chain.

### Report one RTO

Rejected. Backup copy, first query, promotion, validation and service cutover
are distinct clocks. Combining a subset into a production RTO would hide both
the read-only/promotion gap and omitted business work.

## Consequences

Positive consequences:

- the claim is backed by a real restore and a business boundary;
- source and restore evidence are separated;
- the recovered fork cannot advertise a TCP service or archive into the
  source repository;
- the retained directory supports post-run inspection;
- counterexamples make the decision rule executable.

Costs and limitations:

- each run creates a full backup and retains one restored copy;
- source and restore share local lab infrastructure;
- the local repository is neither independent nor proven immutable;
- timings from a small synthetic database are not capacity evidence;
- regional loss, missing WAL, missing keys and retention expiry remain
  production-gate work.
