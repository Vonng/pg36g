# ADR-019: accept the four-node Pigsty deployment as an L2 sandbox baseline

- Status: accepted with six sandbox exceptions; not production approval
- Release: `2.0-sandbox`
- Evidence date: 2026-07-29
- PostgreSQL: 18.4 (`server_version_num=180004`)
- Pigsty: exact `v4.4.0` tag at
  `2d5a45f759274048de0c197829228a71d0182e5c`
- Next gate: chapter 20 HA behavior

## Context

Chapter 18 proposed PostgreSQL-centered service classes but intentionally left
the lower-volume evidence gates open. Before discussing failure, recovery, or
performance, the book needs one concrete environment whose declaration,
machine identity, initialization choices, topology, and service endpoints can
be observed and reproduced.

A workstation SSH configuration originally mapped the four `10.10.10.x`
addresses through one forwarded guest. Direct SSH with `-F /dev/null` proved
that the addresses are in fact four distinct Ubuntu guests. This is why
hostname, address, and hashed machine identity are all part of the acceptance
contract rather than relying on an apparently successful connection.

## Decision

### Pin the implementation

Use an archive of the exact Pigsty `v4.4.0` Git tag, not the maintainer's dirty
working tree. Generate the starting configuration from `conf/ha/full.yml` with:

```text
./configure -c ha/full -s -n -g -v 18 -r default
```

Keep the generated live inventory private and mode `0600`. Export only an
allowlisted projection that records the release, non-secret initialization
settings, host membership, declared roles, and how many secret fields were
redacted.

### Treat two clusters as two service units

- `pg-meta` is a single-node control and validation unit on `10.10.10.10`.
- `pg-test` is a three-member teaching unit: primary on `.11`, HA replica on
  `.12`, and offline-query replica on `.13`.

The offline tag is placement intent, not proof of workload isolation. Service
routing and pooling semantics are deferred to chapter 22.

### Freeze irreversible initialization choices

The observed PostgreSQL contract is version 18, UTF-8, built-in `C.UTF-8`
locale provider, data checksums on, 8 KiB blocks, 16 MiB WAL segments,
`Etc/UTC`, SCRAM password encryption, and TLS on. Inventory intent is
insufficient: each member must report these facts from SQL.

### Accept by evidence layers

Acceptance requires agreement across:

1. secret-free inventory declaration;
2. four direct host observations;
3. PostgreSQL identity and recovery-role SQL;
4. Patroni membership and role state; and
5. endpoint reachability and service state.

The deployment completed with return code zero and no unreachable or failed
host in the Ansible recap. A fresh read-only capture then passed the normal
policy and all nine negative tests.

## Exceptions

| ID | Accepted only for this sandbox | Production consequence |
|---|---|---|
| `EX19-SHARED-HYPERVISOR` | four guests share one laptop | node count does not prove independent failure domains |
| `EX19-SINGLE-ETCD` | one etcd member | DCS availability is unqualified |
| `EX19-SINGLE-BACKUP-TARGET` | one local MinIO/control guest | disaster recovery is unproven |
| `EX19-VIRTUAL-STORAGE` | Vagrant virtual disks | no capacity, latency, endurance, or durability claim |
| `EX19-INVENTORY-SECRETS` | random credentials in a private inventory | production secret authority and rotation are missing |
| `EX19-LAB-RESOURCE-FLOOR` | three guests have 1 vCPU and about 1.9 GiB RAM | success cannot justify production sizing or concurrency |

The last exception does not silently redefine the recommendation. The hard
sandbox acceptance floor is recorded separately from the recommended
2-vCPU/2-GiB teaching floor.

## Consequences

### Positive

- Subsequent chapters have an exact, observable Pigsty/PostgreSQL target.
- Declarative intent is checked against live SQL and coordination state.
- Secret values remain outside source control and evidence.
- The test suite rejects production overclaim, identity reuse, host drift,
  clock/resource defects, initialization drift, split role declarations, and
  secret leakage.

### Costs and limits

- The environment consumes local resources and must be retained for later
  chapter gates.
- Fresh evidence is required because machine, package, endpoint, and role facts
  can drift.
- A successful deploy says nothing about switchover, data-loss envelope,
  restore correctness, throughput, saturation, or production failure domains.
- Kernel package changes observed during bootstrap may require a separately
  approved reboot; chapter 19 does not reboot hosts merely to clear a warning.

## Rejected alternatives

### Call `deploy.yml` success production readiness

Rejected. Playbook convergence proves that automation ran; it does not prove
the service objectives in chapter 18.

### Commit the generated live inventory

Rejected. Redacting values after publication is too late. Only an allowlisted
projection belongs in evidence.

### Lower the teaching recommendation without recording the resource gap

Rejected. The real guests deployed below the recommendation, so the difference
is an explicit exception and blocks capacity inference.

### Rebuild automatically before every lab

Rejected. Rebuild is destructive, erases incident evidence, and makes later
chapters unable to distinguish convergence from recovery. Normal actions are
read-only; reset remains a separately guarded exercise.

## Revision triggers

Revisit this ADR when the Pigsty or PostgreSQL major version changes, the host
set or initialization contract changes, any exception is removed or expanded,
chapter 20 disproves the topology assumptions, chapter 21 disproves recovery,
or the target is proposed for real production data or traffic.
