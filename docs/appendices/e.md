---
title: 附录 E：实验拓扑、风险与复位手册
linkTitle: 附录 E 实验拓扑、风险与复位手册
weight: 50
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

本附录定义实验“在哪里运行、能改变什么、怎样回到可信状态”。它不是生产授权书；
每个章节的 lab contract 与当前环境 authority 优先。

## E.1 L1/L2/L3 资源规格、网络和成本说明 {#appendix-e-1}

### L1：单节点学习环境

| 项 | 安装下限 | 本书最低 | 推荐 |
|---|---:|---:|---:|
| node | 1 | 1 | 1 |
| vCPU | 1 | 2 | 4 |
| RAM | 2 GiB | 4 GiB | 8 GiB |
| 可用磁盘 | 20 GiB | 40 GiB | 80 GiB |

用途：ch01～ch18 的对象、SQL、应用与 extension PoC。默认单节点 `meta` 模板包含
PostgreSQL 与可观测组件，但不提供独立故障域或生产 HA。见[第 0 章](/ch00/)。

### L2：四 VM 生产仿真

正式拓扑 `pg36-l2-vagrant`：

```text
pg-meta-1  10.10.10.10  control + single PostgreSQL service
pg-test-1  10.10.10.11  pg-test primary at baseline
pg-test-2  10.10.10.12  pg-test replica
pg-test-3  10.10.10.13  pg-test replica/offline + disposable drill host
```

合同：

```text
Pigsty v4.4.0 / PostgreSQL 18
Ubuntu 24.04 / aarch64 in formal run
UTC + synchronized clocks
data_checksums=on / UTF8 / C.UTF-8 / scram-sha-256 / SSL
distinct machine identities
minimum root free 8 GiB at acceptance
```

三台 `pg-test` VM 的正式教学运行只有 1 vCPU、约 1.9 GiB RAM；这被记录为 accepted
sandbox exception。推荐至少给每个 PostgreSQL VM `2 vCPU / 2 GiB`，控制/压测 client
使用 `2 vCPU / 4 GiB` 以上，并为 WAL、backup、clone 和 fixture 预留更多磁盘。

所有 VM 共享一台 laptop/hypervisor/power/storage，因此：

```text
3 PostgreSQL members != 3 production failure domains
1 etcd member          != production DCS quorum
local MinIO/repository != offsite disaster recovery
virtual disk result    != production IOPS/durability
```

见 [ch19 正式合同](/labs/ch19/requirements.json)。

### L3：从可信点分叉的事故现场

L3 不是“把 L2 破坏得更严重”，而是：

```text
managed L2 read-only/controlled boundary
  +
stopped snapshot or deterministic source
  ->
private disposable case/working/recovery copies
```

第 32～35 章在 L2 host 上使用 exact UUID temporary root、private Unix socket、
非业务端口/无 TCP listener，并与 Patroni、DCS、HAProxy、PgBouncer、backup repository
和业务 route 隔离。L3 需要额外磁盘至少容纳 source + cases + working/recovery +
evidence；运行前按 fixture 实测，而不是假定固定 8 GiB 足够。

### 网络

```text
operator -> SSH to exact lab aliases
L2 internal 10.10.10.0/24 teaching network
service path and direct instance path both identifiable
disposable cluster listen_addresses='' where contract requires
no production route or public exposure
```

### 成本

本地成本来自 host RAM/CPU、磁盘、耗电与时间；云端另有 compute、volume/snapshot、
public IP、egress、object storage/API。价格随 region/日期变化，本书不冻结金额。每个
环境设置 owner、expiration 与 budget alert，并把保留 evidence 的费用计入。

## E.2 R0–R3 风险标记 {#appendix-e-2}

`L1/L2/L3` 描述实验环境；`R0–R3` 描述动作风险。两者不能互推：L3 中仍有 R0
查询，L1 上误删唯一数据仍是破坏性动作。

| 风险 | 定义 | 例子 | 必备 |
|---|---|---|---|
| R0 观察 | 不改变目标状态 | identity/catalog/stats、plain `EXPLAIN`、capture | exact context、query cost、隐私 |
| R1 可逆变更 | 改状态但有已验证回退 | fixture DDL、bounded config、canary、精确 cancel | owner、before/after、stop、rollback |
| R2 受控状态变更/演练 | 有非平凡状态影响，但范围隔离且恢复路径已验证 | 一次性对象删除、隔离 PITR/failover、fault injection | guard、批准、恢复源、停止线、证据 |
| R3 生产敏感/潜在不可逆 | 触及真实数据/流量、authority/lineage，或恢复昂贵 | 生产 failover/cutover、rewind/reinit、host rebuild、`pg_resetwal` | 原件保留、明确授权、独立复核、业务验收 |

同一命令没有固定风险等级：在 disposable clone 上恢复一份 candidate 可以是 R2；让它
接管生产流量、覆盖真实目标或改变唯一权威时就是 R3。

### 风险升级因素

```text
production data or traffic
target identity ambiguity
large or unknown scope
irreversible external effect
unique copy
weak/untested rollback
authority/lineage change
service restart or route change
long lock / resource saturation
secret or personal data exposure
```

任一因素都可能把看似普通命令升级。风险低不代表无成本：复杂 catalog query、
`EXPLAIN ANALYZE`、日志导出也可能造成负载或泄露。

### guard 不是免责声明

```yaml
target:
environment:
production_data:
production_traffic:
scope:
confirmation:
authority:
rollback_source:
```

guard 必须在 mutation 前解析并 fail closed。设置
`I_KNOW_WHAT_I_AM_DOING=true` 这种通用 token 不证明 target 或 authority。

各章脚本还可能使用 `L0/L1/L2/L3` 表示其内部 mutation level；以对应
`lab-contract.md` 定义为准，不与拓扑层级混用。

## E.3 `reset:sql`、`reset:cluster`、`reset:host` {#appendix-e-3}

### 三种复位不是强度旋钮

| 复位 | 目标 | 不应做 |
|---|---|---|
| `reset:sql` | 删除/重建本章 owned fixture，恢复数据库对象起点 | drop 未解析 schema/database |
| `reset:cluster` | 恢复服务、角色、配置、路由与本章 fixture baseline | 删除 managed PGDATA 猜测重建 |
| `reset:host` | 从 clean OS/storage + pinned inventory 重建不可信宿主机 | 当作一条普通可复制命令 |

名称是全书实验合同类别，不保证每章存在同名脚本。

### `reset:sql`

前置：

```text
current database/role/system identity match
owned object manifest complete
no production data/traffic
dependent session/job stopped
only pg36 chapter namespace/object selected
```

执行后验证 object absent/recreated、其他 schema digest 不变、connection context 仍正确。
用明确对象列表，不使用模糊 wildcard/cascade。

### `reset:cluster`

可能包含：

```text
remove exact fixture sessions/roles/schema
restore parameter and pending_restart state
restore Patroni role/topology baseline
restore HAProxy/PgBouncer route
re-enable archive/backup/monitoring/automation
reconcile temporary privilege and secret
```

先生成 plan，逐项 before/after。计划切换后的 baseline restore 仍是 HA 变更，需要
authority 和 client validation；不是测试清理的附带步骤。

### `reset:host`

只有当 OS、storage、package 或 PostgreSQL 基线不再可信才进入：

```text
preserve/hash evidence outside target
fence host from writer authority and routes
prove trusted backup or healthy source
pin inventory/release/packages/secrets
obtain destructive production approval
provision clean host/storage
restore or join as fresh replica
validate lineage, backup, monitoring, business
observe before traffic
```

不要复用 suspect PGDATA，不删除唯一 evidence。第 35 章只生成
[`l3-rebuild-plan.json`](/labs/ch35/l3-rebuild-plan.json)，没有执行 managed
`reset:host`。

### reset 也需要验证器

```text
exact target resolved
owned fixture removed
unrelated object/topology unchanged
temporary process stopped
route/automation restored
retained evidence still present
cleanup path exact
```

“脚本执行完”不等于 baseline 已恢复。

## E.4 随机种子、快照、校验和与故障场景清单 {#appendix-e-4}

### 可复现 fixture

```yaml
generator_revision:
seed:
row_count:
distribution:
time_anchor:
locale_timezone:
scale:
expected:
  counts:
  sums:
  ordered_digest:
```

固定 seed 不足以保证相同结果；generator、PRNG、locale、timezone、dependency 与输入
排序都要固定。摘要至少组合 row count、关键 sum/range 与确定顺序 digest。

### snapshot 树

```text
known-good immutable source
  -> case-A original
     -> working-A1
     -> working-A2
  -> case-B original
     -> recovery-B
```

记录 snapshot ID、parent、created_at、filesystem/database consistency、system
identifier/timeline projection 和 hash。实验只改 case/working，known-good 与 original
在结论完成前保持不变。

### checksum 的四种含义

| checksum/hash | 证明 |
|---|---|
| PostgreSQL data checksum | data page 写入/读取校验范围内的物理一致性 |
| file SHA-256 | 同一 byte stream 未变 |
| canonical JSON/source hash | 合同/证据 source 未漂移 |
| business digest | 所选字段/顺序在定义范围内一致 |

它们不能互换。hash 匹配不证明来源可信，business digest 不证明每个 page 可读。

### 场景清单

```yaml
scenario_id:
hidden_truth:
public_packet:
allowed_mutations:
forbidden_targets:
required_evidence:
classifier_predicates:
unknown_route:
safe_actions:
dangerous_actions:
cleanup:
claims_not_made:
```

blind exercise 把 hidden truth 与 participant/classifier input 分离；场景 source 在公开
教材中不是密码学秘密，正式考核由主持人控制访问或生成私有 seed。

### evidence bundle

```text
contract + source manifest
environment identity
before / during / after
blind packet + hidden answer
decision/classification
business manifest
negative cases
cleanup
redacted public summary
```

raw logs、PGDATA、query payload、credentials 和个人数据留在受控 evidence store，
仓库只发布去敏 projection。

---

[返回附录目录](../) · [症状索引](../c/) · [术语边界](../f/) ·
[查看全书目录](/toc/)
