# Chapter 18 lab contract

## Purpose

This lab closes the upper volume by answering a different question from the
preceding feature labs: **what can the retained `pg36_shop` evidence support as
an architecture decision, and what still remains a proposal?**

It therefore audits, rather than rebuilds, the chapter 4 and chapter 13–17
fixtures. The database is one source of evidence; the service catalog,
extension lifecycle, external data contracts, and lower-volume evidence gates
are equally important.

## Risk and authority

- Risk class: **L0, read-only**.
- Target: the confirmed local `pg36_shop` development fixture.
- Database identity: PostgreSQL 18.x, formal fixture validated on 18.4.
- Required administrator identity: `postgres` through a private
  `PGSERVICEFILE`.
- Pigsty version used for the reference mapping: 4.4.
- Pigsty L1 deployment validation: **not run**.
- Allowed operations: catalog reads, retained-fixture verification, local file
  reads, deterministic JSON validation, and evidence-directory writes.
- Forbidden operations: DDL, DML, role changes, extension changes, service
  deployment, secret discovery, failover, backup/restore, and any reset.

The lab has no `setup` or `reset` action by design. If a prerequisite fixture is
missing, it fails and points back to the owning chapter; it does not silently
repair state.

## Inputs

| Input | Meaning |
|---|---|
| `baseline-v1.6-proposal.json` | proposed production capability placement |
| `service-catalog.json` | proposed service classes and extension bundles |
| `external-data-contracts.json` | authority and lifecycle of derived copies |
| `lower-volume-gates.json` | chapters 19–36 as pending evidence contracts |
| `negative-cases.json` | architecture-policy counterexamples |
| chapter 4 and 13–17 fixtures | PostgreSQL evidence retained by the upper volume |

The JSON documents are versioned proposals. A schema-valid document is not
automatically a sound architecture; `validate.py` cross-checks their
references and policies.

## Actions

```bash
export PGSERVICEFILE=/path/to/private/pg_service.conf
export PGSERVICE=pg36-admin

static/labs/ch18/task.sh verify
static/labs/ch18/task.sh capture
static/labs/ch18/task.sh all
```

- `verify` runs the retained-fixture preflights and the document policy suite.
- `capture` adds one read-only catalog snapshot and reviews it.
- `all` captures two cycles and requires the deterministic evidence files to be
  byte-identical.
- `review` reviews one already captured cycle directory.

`PG36_EVIDENCE_DIR` selects an output directory. It must be outside source
control for a real environment because manifests include host-local version
information and timestamps.

## Acceptance

`all` passes only when:

1. chapter 4 and chapters 13–17 still pass their own verification;
2. the canonical business relation checksum is
   `f8a7bfae59c6d16cd323abecfefe1014`;
3. the exact extension identities and lifecycle evidence match the formal
   fixture;
4. `pg36_owner` remains `NOLOGIN`, `pg36_app` remains a non-superuser login,
   and the catalog session has the expected administrator identity;
5. the blueprint references four service offerings, five extension bundles,
   five external contracts, nine capability decisions, and all 18 lower-volume
   gates;
6. all seven counterexamples fail with their intended stable policy code;
7. the two catalog and policy snapshots are byte-identical; and
8. the result still says `pigsty_l1=not-run` and `mutation=none`.

## Interpretation boundary

A passing lab proves internal consistency of the teaching fixture and the
architecture proposal. It does **not** prove availability, RPO, RTO, capacity,
security, backup recoverability, upgrade safety, or Pigsty convergence. Those
claims belong to chapters 19–36 and must be supported by target-environment
evidence.
