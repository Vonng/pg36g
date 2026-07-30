# Chapter 22 service, pooling and routing lab contract

## Purpose

The lab proves a bounded service contract on the retained local `pg-test`
sandbox:

1. four Pigsty service ports select the documented role and pool/direct path;
2. a two-slot PgBouncer pool queues synthetic clients instead of opening more
   than two server connections;
3. transaction pooling does not preserve arbitrary SQL session state;
4. protocol-level prepared statements work for the exact tested
   PgBouncer/psycopg versions, while SQL-level `PREPARE` is not treated as
   portable across backend reassignment;
5. one asynchronous replica-read visibility delay is measured without being
   promoted into a consistency guarantee;
6. a modest reconnect probe survives two healthy planned switchovers with
   acknowledged writes reconciled;
7. the original PgBouncer settings and final leader are restored.

It does not prove production capacity, TLS, a redundant load-balancer
entrypoint, unplanned failover, fencing or bounded replica staleness.

## Exact target

Mutating action `drill:service` requires:

- `PG36_CH22_TARGET=pg36-l2-vagrant/pg-test`
- `PG36_CH22_NONPRODUCTION=true`
- `PG36_CH22_PRODUCTION_DATA=false`
- `PG36_CH22_PRODUCTION_TRAFFIC=false`
- `PG36_CH22_CONFIRM=POOL_ROUTE_SWITCH_AND_RESTORE_CH22`
- a mode-0600 chapter-19 inventory for preflight and postflight.
- a separate mode-0600 reviewed Pigsty inventory containing the declared
  nonproduction `test` user's PgBouncer credential.

The initial and final topology is:

```text
pg-test-1 primary/running
pg-test-2 replica/streaming
pg-test-3 replica/streaming
```

Only healthy planned switchovers are authorized:

```text
pg-test-1 -> pg-test-2
pg-test-2 -> pg-test-1
```

No process, host, network, storage or DCS fault may be injected.

## Risk levels

| Action | Risk | Mutation |
|---|---:|---|
| `capture` | L0 | none |
| `verify`, `review`, `all` | L0 | none |
| fixture schema setup | L1 | one synthetic schema using a declared sandbox login |
| temporary pool override | L1 | runtime settings on pg-test-1 PgBouncer |
| saturation and prepared-state probes | L1 | synthetic transactions |
| planned switch and baseline restore | L2 | Patroni role/timeline changes |
| `reset:fixture` | L3 | drops the synthetic schema; preserves the declared login |

`all` never sets PgBouncer configuration, creates connections, switches
leaders, writes rows or resets the fixture.

## Fixture and secret handling

The runner uses the pre-existing Pigsty-declared login and creates:

```text
role     test LOGIN, pgbouncer=true (pre-existing, preserved)
database test (pre-existing)
schema   pg36_ch22
table    pg36_ch22.route_probe
```

It extracts only that user's credential from the private declaration and writes
one local mode-0600 libpq service file in a mode-0700 temporary directory. The
password is never printed, hashed into evidence or committed. The temporary
directory is removed on exit. The runner verifies the deployed role's safe
attributes and never creates, alters, owns or drops it. This is deliberate:
creating a PostgreSQL `LOGIN` role alone does not deliver that identity through
PgBouncer's managed authentication surface.

## Endpoint contract

The single sandbox entry address is `10.10.10.11`:

| Service | Port | Destination | Health selector |
|---|---:|---|---|
| primary | 5433 | current primary PgBouncer :6432 | `/primary` |
| replica | 5434 | replica-preferred PgBouncer :6432 | `/read-only` |
| default | 5436 | current primary PostgreSQL :5432 | `/primary` |
| offline | 5438 | declared offline PostgreSQL :5432 | `/replica` |

The service file uses `target_session_attrs=read-write` for the primary path
and `read-only` for replica/offline paths. TLS is `prefer` because client TLS
is disabled on this sandbox PgBouncer; this remains an explicit exception.

## Temporary PgBouncer override

Before any application connection activates the dedicated sandbox `test/test`
pool, the runner snapshots these changeable settings on
the current primary:

```text
default_pool_size=50
reserve_pool_size=30
reserve_pool_timeout=1
query_wait_timeout=120
```

It temporarily sets:

```text
default_pool_size=2
reserve_pool_size=0
query_wait_timeout=5
```

The scope is one PgBouncer process on one nonproduction node. A `finally`
handler restores the exact snapshot and verifies it before any switchover.
The lab fails if restoration cannot be proved.

Before that snapshot, the runner issues `RECONNECT test` on all three
PgBouncer processes. This closes only idle/finished server connections for the
teaching database and makes each pool rediscover the member's current
read-write/read-only state. The step is evidence-bearing because a pool can
otherwise retain role metadata from an earlier promotion or demotion even when
Patroni and PostgreSQL already show the correct topology.

## Pool and session experiments

Twelve clients run `pg_sleep(0.25)` through the primary service. PgBouncer
`SHOW POOLS` is sampled from its local Unix admin socket. Acceptance requires:

```text
maximum server-active <= 2
at least one client observed waiting
all client queries finish
```

The session-state probe deliberately reassigns two clients across two server
connections. It proves that a SQL `SET search_path` is not a sticky
client-session property in transaction pooling and may be visible on the
backend assigned to another client. It then issues `RECONNECT test` after the
clients disconnect so that altered backend state is not retained.

The protocol prepared-statement probe uses psycopg's extended protocol with
`prepare_threshold=1` and must return correct results across transactions.
The SQL-level `PREPARE` probe forces backend reassignment and must receive
`InvalidSqlStatementName`. This is an expected negative behavior, not a lab
failure.

## Replica visibility

The runner inserts one unique token through port 5433 and records its commit
LSN. It polls port 5434 until the exact token is visible and records elapsed
time, selected replica and replay LSN. Passing proves only one observation
under current load. The async baseline forbids a general read-your-writes or
bounded-staleness claim.

## Planned switch probe

Six workers repeatedly create short connections to port 5433 using
`target_session_attrs=read-write`. Every attempt has a unique idempotency token.
On failure, each worker applies capped exponential backoff with jitter; it
does not resubmit the same logical token.

The runner:

1. waits for warm-up acknowledgements;
2. switches to `pg-test-2`;
3. waits for one-primary/two-streaming stability;
4. issues `RECONNECT test` on all three pools and requires a post-refresh
   acknowledgement;
5. restores the baseline to `pg-test-1`;
6. refreshes all three pools again and requires another acknowledgement;
7. lets the 24-second probe finish;
8. reconciles every acknowledged and unknown token.

Acceptance requires no missing acknowledged token, duplicate token or
unreconciled unknown outcome. The observed write gap includes sampling and
backoff, role convergence and pool refresh; it is not a production failover
SLO. Pool refresh is part of the measured recovery path, not hidden setup.

## Stop conditions

The runner stops before switching if:

- the chapter-19 gate fails;
- topology or dynamic Patroni policy drifts;
- endpoint definitions or versions drift;
- the fixture schema collides or the declared login's safe attributes drift;
- PgBouncer settings are not changeable or cannot be restored;
- the pool experiment exceeds its two-server cap;
- the primary endpoint is read-only or replica endpoint is writable.

After the forward switch, it attempts the planned baseline restore only if the
cluster is stable with `pg-test-2` as sole leader. It never forces an action on
an ambiguous or degraded topology.

## Evidence and interpretation

The secret-free bundle records:

- chapter-19 pre/post gates;
- source topology and exact safe configuration projection;
- endpoint observations;
- PgBouncer before/during/restored settings and `SHOW POOLS` maxima;
- prepared/session behavior;
- replica token visibility;
- switch phases, client events and reconciliation;
- source hashes, exceptions and adversarial validation.

It does not record a password, SCRAM verifier, raw inventory, HAProxy stats
credential or database system identifier.

## Reset

`reset-fixture.sh` is not used by any normal action. It requires an exact
destructive token, terminates only chapter-tagged sessions and drops only
`pg36_ch22`. It preserves the Pigsty-declared `test` role. Planned switch
timelines and historical backup evidence are not reset.
