# Chapter 19 lab contract

## Purpose

This lab turns a deployment proposal into a bounded L2 sandbox acceptance
decision. It asks whether one exact Pigsty release can converge four distinct
Linux guests into the declared PostgreSQL topology and whether inventory,
host, SQL, Patroni, and endpoint evidence agree.

The result is deliberately narrower than “production ready.” The four guests
share one laptop and several control-plane dependencies, three guests are below
the chapter's recommended teaching resource floor, and no fault, recovery, or
capacity test runs here.

## Risk and authority

- Risk class of `project`, `capture`, `verify`, `review`, and `all`: **L0,
  read-only against the deployed service**. They write only to the selected
  local evidence directory.
- Formal target: `pg36-l2-vagrant`, a disposable local Linux sandbox containing
  `pg-meta` and `pg-test`.
- Reference implementation: exact Pigsty `v4.4.0` tag at commit
  `2d5a45f759274048de0c197829228a71d0182e5c`, PostgreSQL 18.
- Allowed reads: a secret-free inventory projection, host facts over SSH,
  PostgreSQL identity queries as the local database OS user, Patroni list/REST
  identity, and TCP reachability.
- Forbidden in normal actions: package changes, configuration convergence,
  DDL/DML, failover, switchover, service restart, backup/restore, cluster
  removal, and secret-value export.
- `all` never deploys, reconfigures, fails over, restores, or resets anything.

`reset:cluster` is a separate destructive exercise. It is not an acceptance
prerequisite and must not be run against this retained environment unless the
operator intentionally supplies every guard described below.

## Inputs

| Input | Meaning |
|---|---|
| `requirements.json` | sandbox requirements, initialization contract, and named exceptions |
| `baseline-v2.0-sandbox.json` | accepted deployment decision and interpretation boundary |
| private Pigsty inventory | authoritative live declaration; must remain mode `0600` |
| `negative-cases.json` | nine counterexamples that must fail with stable policy codes |
| `deployment-run.json` | sanitized account of the completed deployment, not a substitute for fresh evidence |

The private inventory contains credentials and is never copied into the
repository or evidence bundle. `inventory_projection.py` exports only an
allowlisted topology plus source mode and redaction counts. A hash of the full
secret-bearing inventory is deliberately withheld; the manifest hashes only
the safe projection.

## Normal actions

```bash
export PG36_CH19_INVENTORY=/absolute/path/to/private/pg36.yml
export PG36_EVIDENCE_DIR=/absolute/path/to/evidence/ch19

static/labs/ch19/task.sh project
static/labs/ch19/task.sh capture
static/labs/ch19/task.sh verify
static/labs/ch19/task.sh review
static/labs/ch19/task.sh all
```

- `project` creates only the secret-free inventory projection.
- `capture` reads the four hosts and creates a fresh evidence bundle.
- `verify` validates an existing bundle and runs all nine counterexamples.
- `review` checks the reports, source checksums, evidence boundary, and
  deployment account.
- `all` performs `capture`, `verify`, then `review`.

SSH deliberately uses `-F /dev/null`. This prevents a workstation SSH alias or
port-forward from mapping several declared addresses back to one guest.
`PG36_SSH_USER` defaults to `vagrant`.

## Acceptance

`all` passes only when:

1. the private inventory is mode `0600`, exports no secret values, declares
   Pigsty `v4.4.0`, PostgreSQL 18, locale `C.UTF-8`, and the exact four members;
2. the addresses resolve to four distinct machine identities with uniform
   Ubuntu 24.04/aarch64 hosts, synchronized `Etc/UTC` clocks, THP `never`, no
   swap, and the sandbox resource/free-space floor;
3. PostgreSQL reports version 18, UTF-8 with the built-in `C.UTF-8` provider,
   checksums on, 8 KiB blocks, 16 MiB WAL segments, SCRAM, TLS, and the declared
   recovery roles;
4. members of one cluster share one system identifier while `pg-meta` and
   `pg-test` do not;
5. inventory, SQL, and Patroni agree on one `pg-meta` primary plus one
   `pg-test` primary and two streaming replicas;
6. HAProxy, PgBouncer, Patroni, etcd/nginx where applicable, the declared TCP
   endpoints, and Patroni identity are observable;
7. all six sandbox exceptions remain explicit;
8. all nine negative cases fail with their intended stable code; and
9. every captured source checksum matches the source used for review.

## Named exceptions and production boundary

The accepted exceptions are shared hypervisor/power/storage, one etcd member,
one local backup target, unqualified virtual storage, temporary inventory-based
secret handling, and three guests below the recommended 2-vCPU/2-GiB teaching
floor.

Therefore a passing result means only
`sandbox_l2=accepted-with-exceptions`. It keeps
`production_ch19_gate=pending`. Chapter 20 owns HA behavior and fault drills;
chapter 21 owns recovery; later chapters own capacity, security, upgrade, and
operations. None is implied by a successful installation.

## Destructive reset contract

`task.sh reset:cluster` delegates to `reset-cluster.sh`, which requires:

- the exact target token and reset phrase;
- explicit assertions that no production data exists and clients are drained;
- the exact Pigsty home and private inventory;
- a previously reviewed machine-identity allowlist;
- a fresh passing `all` evidence bundle; and
- an interactive second acknowledgement.

It removes `pg-test` before `pg-meta`. It never runs from `all`, and this book
does not authorize the reader or automation to invoke it on any production
system.
