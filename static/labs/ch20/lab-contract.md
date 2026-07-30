# Chapter 20 lab contract

## Purpose

This lab measures one deliberately narrow behavior on the retained chapter 19
sandbox: a healthy, operator-planned Patroni switchover from `pg-test-1` to
`pg-test-2`, followed by a second planned switchover that restores
`pg-test-1` as the teaching baseline.

The client probe writes idempotency tokens through the Pigsty read-write
service while the first transition runs. It records acknowledged and
outcome-unknown attempts, then reconciles every token against PostgreSQL. The
lab therefore tests topology transition, lineage, client-visible interruption,
and commit-outcome accounting together.

It does **not** inject a PostgreSQL crash, host loss, storage fault, network
partition, DCS loss, or shared-hypervisor failure. A pass is not evidence of
automatic failover, fencing, split-brain exclusion, zero RPO, or a production
RTO.

## Target and authority

- Target: `pg36-l2-vagrant/pg-test`, the retained local four-guest sandbox.
- Data: synthetic rows in database `test`, schema `pg36_ch20`.
- PostgreSQL: 18.4.
- Pigsty: exact `v4.4.0` tag used by chapter 19.
- Patroni: 4.1.3 on the deployed guests.
- Initial/final leader: `pg-test-1`.
- Temporary candidate: `pg-test-2`.
- Unplanned failure injection: forbidden by this chapter's executable.
- Production data and traffic: forbidden.

The environment has one etcd member, no hardware watchdog, asynchronous
streaming, one shared laptop, and a non-TLS external PgBouncer path. These
conditions are named exceptions, not hidden substitutions for production
design.

## Risk classes

| Action | Risk | Service mutation |
|---|---:|---|
| `capture` | L0 | none; reads SQL, Patroni, and projected local policy |
| `verify` | L0 | none; validates an existing evidence bundle |
| `review` | L0 | none; audits provenance and interpretation |
| `all` | L0 | none; exactly `verify` plus `review` |
| `drill:switchover` | L2 | creates the synthetic fixture and performs two planned switchovers |
| `reset:fixture` | destructive | drops only schema `pg36_ch20` from database `test` |

`all` is intentionally not an alias for the live drill. Re-running a service
transition merely because a reader wanted to validate files would be an unsafe
interface.

## Inputs

| Input | Role |
|---|---|
| `requirements.json` | exact members, policy, actions, client objective, and exceptions |
| `failure-model.json` | nine failure domains and the one behavior actually observed |
| private chapter 19 inventory | mode-0600 authority used only to derive a temporary libpq service file |
| `setup.sql` | idempotent synthetic probe schema |
| `ha-facts.sql` | PostgreSQL lineage, WAL, sender, slot, receiver, and archive facts |
| `negative-cases.json` | ten invalid claims or evidence mutations that must be rejected |

The private inventory and generated service file never enter the repository or
evidence bundle. The service helper prints only status, never a password. The
drill manifest reports `secret_values_exported=0`.

## Read-only actions

Capture current state:

```bash
export PG36_EVIDENCE_DIR=/absolute/path/to/evidence/ch20-current
static/labs/ch20/task.sh capture
```

Validate and review a retained complete drill:

```bash
export PG36_EVIDENCE_DIR=/absolute/path/to/evidence/ch20-formal
static/labs/ch20/task.sh verify
static/labs/ch20/task.sh review
static/labs/ch20/task.sh all
```

These actions never switch a leader, change Patroni policy, create a fixture,
drop an object, restart a service, reinitialize a member, or inject a fault.

## Guarded planned drill

Run only on the named disposable sandbox:

```bash
export PG36_CH19_INVENTORY=/absolute/path/to/private/pg36.yml
export PG36_EVIDENCE_DIR=/absolute/path/to/new-empty/ch20-formal
export PG36_CH20_TARGET=pg36-l2-vagrant/pg-test
export PG36_CH20_NONPRODUCTION=true
export PG36_CH20_PRODUCTION_DATA=false
export PG36_CH20_PRODUCTION_TRAFFIC=false
export PG36_CH20_CONFIRM=SWITCH_CH20_PG_TEST_1_TO_2_AND_BACK

static/labs/ch20/task.sh drill:switchover
```

The wrapper refuses a non-empty evidence directory. It first runs a fresh
chapter 19 acceptance, creates a mode-0600 temporary libpq service file, runs
the two planned transitions, validates normal and negative evidence, restores
the baseline leader, and finally runs chapter 19 acceptance again. The
temporary credential file is removed on exit.

If an error occurs after the forward transition, `drill.py` attempts the
baseline restore only when it can confirm `pg-test-2` as the sole healthy
leader. It never guesses through an ambiguous topology.

## Acceptance

The sandbox planned-switchover decision passes only when:

1. chapter 19 passes immediately before and after the drill;
2. all three members retain one PostgreSQL system identifier;
3. the pre-switch timeline is stable, then advances on each planned
   switchover;
4. SQL and Patroni agree on the active primary's current WAL timeline;
5. the old primary rejoins as a streaming replica after the forward action;
6. the final leader is again `pg-test-1`, with two streaming replicas;
7. two active physical replication slots and the expected asynchronous policy
   remain visible;
8. every acknowledged client token exists, no token is duplicated, and every
   outcome-unknown attempt is reconciled;
9. the sampled conservative write gap is no more than 15 seconds;
10. the probe writes no unexpected stderr and no secret value is exported;
11. all ten counterexamples fail with their intended stable policy code; and
12. all source-input checksums match the reviewed source.

The 15-second bound is a chapter sandbox objective. It includes probe sampling
interval and is neither a production SLI nor a promise that unplanned failover
will meet the same number.

## Interpreting timelines

Patroni reports the current cluster timeline. On a standby,
`pg_control_checkpoint().timeline_id` describes the last checkpoint control
record and can lag the timeline currently being replayed. Therefore the
evidence keeps `checkpoint_timeline_id` under that exact name and requires it
only to be no greater than the current phase timeline. On the primary,
`current_wal_timeline_id` is derived from the current WAL filename and must
equal Patroni's timeline.

Treating a stale standby checkpoint timeline as proof that the member failed
to follow promotion would be a measurement bug, not an HA finding.

## Commit outcomes

An error returned after a client sends a statement does not prove whether the
server committed it. The probe assigns one unique token to each business
attempt and does not blindly turn an outcome-unknown attempt into a new
action. Reconciliation classifies it by token lookup.

The lab can prove that all acknowledged tokens from this run remained present.
It cannot prove zero RPO for asynchronous replication: the sampled write stream
did not force the failure window that would expose the asynchronous tail.

## Named exceptions and decision boundary

The six chapter 19 exceptions remain in force. Chapter 20 adds:

- `EX20-ASYNC-BASELINE`: `synchronous_mode=false`; zero RPO is not established.
- `EX20-WATCHDOG-OFF`: no hardware-watchdog fencing is exercised.
- `EX20-CLIENT-PROXY-NO-TLS`: external port 5433 accepts the probe with
  `sslmode=prefer`, not a production transport-security contract.
- `EX20-PLANNED-ONLY`: no unplanned fault is injected.

A pass means
`sandbox_planned_switchover=accepted-with-exceptions` and keeps
`production_ch20_gate=pending`. Backup recovery belongs to chapter 21, client
routing to chapter 22, security to chapter 23, and the separately authorized
failure exercise to chapter 33.

## Destructive fixture reset

Reset is not part of acceptance. It requires a still-reviewable evidence
bundle plus all normal target guards, an explicit drained-client assertion,
and the exact token `DROP_PG36_CH20_FIXTURE`. It drops only
`pg36_ch20` from database `test`.

Never run it against a production database. This book does not authorize
cluster removal, member reinitialization, WAL deletion, or any other cleanup
under the name of this fixture reset.
