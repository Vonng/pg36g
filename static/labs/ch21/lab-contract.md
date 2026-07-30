# Chapter 21 isolated-recovery lab contract

## Purpose and claim boundary

This lab answers one narrow question:

> Can one fresh physical backup of the retained `pg-test` sandbox, together
> with its archived WAL, be restored to a named point in an isolated
> postmaster so that reviewed business markers satisfy the expected boundary?

A passing run proves that proposition only for the captured run. It does not
prove a production RPO/RTO, regional disaster recovery, repository
immutability, arbitrary-time recovery, application cutover, or recovery from
lost encryption keys.

The authoritative machine-readable contract is `requirements.json`. The
scenario map is `recovery-scenarios.json`.

## Risk levels and default actions

| Action | Level | Default |
|---|---:|---|
| Inspect source, repository and Patroni state | L0 | allowed |
| Validate or review an existing evidence bundle | L0 | allowed |
| Insert synthetic markers and create a named restore point | L1 | guarded |
| Take one additional full sandbox backup | L1 | guarded |
| Restore into a new, empty isolated path and start a private postmaster | L2 | guarded |
| Delete a fixture or retained restore directory | L3 | separate reset command only |
| Restore over `/pg/data`, stop Patroni, alter routing, or touch production | L4 | forbidden |

`task.sh all` is read-only. It never takes a backup, writes a marker, creates a
restore point, starts PostgreSQL, deletes a directory, or changes routing.

## Exact target and authority

The mutating action `drill:pitr` refuses to run unless all of these are true:

- `PG36_CH21_TARGET=pg36-l2-vagrant/pg-test`
- `PG36_CH21_NONPRODUCTION=true`
- `PG36_CH21_PRODUCTION_DATA=false`
- `PG36_CH21_PRODUCTION_TRAFFIC=false`
- `PG36_CH21_CONFIRM=BACKUP_AND_ISOLATED_PITR_CH21`
- `PG36_CH19_INVENTORY` names a reviewed mode-0600 inventory used by the
  chapter-19 preflight and postflight gates.

The drill also requires the retained topology: `pg-test-1` is leader, both
replicas are streaming, and `pg-test-3` remains a live replica throughout.

## Source mutation

The drill creates one schema and one small table if absent. For a fresh run ID
it inserts:

1. `base`, before the new full backup;
2. `keep`, after the backup and before a named restore point;
3. `discard`, after that restore point.

It then forces a WAL switch and runs `pgbackrest check`. These are intentional
non-destructive sandbox writes. The drill neither deletes old backups nor
expires the repository.

## Restore isolation

The restore host is `pg-test-3`, but the live Patroni member is not used as the
restore target. The private postmaster must use:

- a fresh directory below `/data/pg36-ch21-restore/<run-id>`;
- a private mode-0700 Unix socket directory;
- `listen_addresses=''`, so no TCP listener exists;
- port `55432`, distinct from the live member on `5432`;
- a private HBA file allowing only local peer-authenticated `postgres`;
- `ssl=off`, because the postmaster is Unix-socket-only;
- `archive_mode=off`, so the recovered fork cannot push WAL into the source
  repository;
- empty `primary_conninfo`, `primary_slot_name` and
  `shared_preload_libraries`;
- no Patroni configuration and no DCS membership.

The restored cluster deliberately has the same PostgreSQL system identifier as
its source: that proves physical lineage. It must fork onto a new timeline
after promotion. Evidence stores only the equality relation, not the raw
identifier.

## Recovery-critical configuration

During recovery, PostgreSQL rejects several settings when they are lower than
the values recorded by the source WAL. The drill captures and reuses the live
values of:

- `max_connections`
- `max_worker_processes`
- `max_wal_senders`
- `max_prepared_transactions`
- `max_locks_per_transaction`

Reducing these merely because the restore is “small” is unsafe. The formal
runner does not retry a failed start with altered evidence; it fails the run
and leaves the path for review.

## Two readiness moments

With hot standby enabled, `pg_ctl -w start` may return when the recovered
database first accepts **read-only** connections. `recovery_target_action =
'promote'` can finish slightly later. The runner therefore records:

- start to first read-only connection;
- start to `pg_is_in_recovery() = false`;
- the interval between those moments.

Only the second moment, followed by a rollback-only write probe, counts as
completed promotion. A successful read-only query alone is not accepted.

## Success criteria

A run is accepted only when all of the following are machine-checked:

- chapter-19 preflight and postflight gates pass;
- source topology stays healthy;
- repository and fresh full backup report status `ok`;
- the archive range covers the target restore point's WAL segment;
- pgBackRest restores the exact fresh backup to the exact named point;
- `archive_mode=off`, no TCP listener, private socket, and no Patroni
  membership are observed;
- promotion completes and the recovered instance is writable;
- `base` and `keep` exist with the expected tokens, while `discard` does not;
- physical lineage matches and the restored timeline is newer;
- the isolated postmaster is stopped and its socket is absent;
- all declared exceptions remain attached to the decision;
- every counterexample in `negative-cases.json` is rejected with its intended
  policy code.

## Evidence retention and reset

The completed restore directory is stopped but retained for inspection.
Retention is not cleanup. It consumes storage and contains a physical copy of
the sandbox database.

`reset-fixture.sh` is not called by any normal action. It requires an exact run
ID and separate destructive confirmation. It refuses symlinks, unexpected
paths, a running postmaster, or an active socket before deleting one retained
directory and the matching synthetic rows.

## Interpreting the measurements

The observed backup, copy and recovery times are components, not a complete
business RTO:

\[
RTO_{\text{business}} \ge
T_{\text{provision}} + T_{\text{restore}} + T_{\text{replay}} +
T_{\text{validate}} + T_{\text{cutover}} + T_{\text{dependency}}
\]

The named boundary demonstrates transaction selection. It does not measure the
maximum data loss under an archive outage:

\[
RPO_{\text{archive}} \approx
t_{\text{failure}} - t_{\text{last durable off-host WAL}}
\]

Production acceptance needs representative data volume, independent
infrastructure, adversarial failure cases, application validation, and a
reviewed cutover plan.
