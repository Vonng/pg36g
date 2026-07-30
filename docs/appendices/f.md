---
title: 附录 F：术语与技术边界表
linkTitle: 附录 F 术语与技术边界表
weight: 60
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

同一个词在 PostgreSQL、Pigsty、云平台和 Kubernetes 中可能指不同对象。本附录固定
全书用语；命令执行前仍要解析 exact identity，不能只靠名词。

## F.1 PostgreSQL、Pigsty、Patroni、PgBouncer 与 HAProxy 术语 {#appendix-f-1}

| 组件 | 核心职责 | 不负责 |
|---|---|---|
| PostgreSQL | SQL、事务/MVCC、存储、WAL、复制原语、catalog | 跨节点共识、业务 SLO、外部 route |
| Pigsty | 声明式 inventory、部署、HA/backup/pool/route/monitoring 组合 | 替业务定义 good event、RPO 接受与不变量 |
| Patroni | 用 DCS 协调 PostgreSQL role、leader lock、failover/rejoin | 提供 DCS quorum、网络/硬件绝对围栏 |
| etcd/DCS | 保存 leader/cluster 协调状态并提供共识语义 | 保存业务数据、替 PostgreSQL 复制 WAL |
| PgBouncer | 复用 client/server connection，控制 pool/queue | 选择 PostgreSQL leader、保持所有 session state |
| HAProxy | 按 health/selector 将 service port 路由到 backend | 理解 transaction commit 或业务正确性 |
| pgBackRest | physical backup、WAL archive、restore 工具链 | 自动选择业务正确的 PITR target |
| monitoring stack | 采集、存储、展示、评估与通知 signals | 自动把 component metric 变成 user SLI |

### PostgreSQL

全书核心知识对象。原生证据来自 SQL/catalog/stats、server log、control/WAL/backup
metadata 和 filesystem/OS。平台结论最终要能回到这些语义验证。

### Pigsty

PostgreSQL 数据库服务的参考实现/发行与管理平台。它把多个独立组件通过配置、playbook、
service 和监控组合起来。`pig` 是相关 CLI/package/operations 工具，其版本号与 Pigsty
release 不同，例如正式实验观察到 `pig 1.5.1` 与 Pigsty `v4.4.0`。

### Patroni 与 DCS

Patroni 不“复制数据库”；PostgreSQL streaming replication 复制 WAL。Patroni 根据
DCS leader state、成员健康和配置协调 promotion/demotion。DCS 可用不证明 PostgreSQL
数据最新，PostgreSQL 可写也不证明它仍拥有集群 authority。

### PgBouncer

三种 pool mode（session/transaction/statement）改变 server connection 的租用边界。
transaction pooling 下，不应假定跨 transaction 保留 temp table、session GUC、
prepared statement 或 advisory-lock 语义；实际能力还受 PgBouncer/driver 版本与配置
影响。

### HAProxy

Pigsty service port 用 health endpoint/selector 将流量送到合适 instance/PgBouncer。
client 连接 HAProxy 的 address 与 PostgreSQL `inet_server_addr()` 返回的 backend
address 不同，是正常的两层 identity。

## F.2 实例、database cluster、Pigsty cluster 与服务端点 {#appendix-f-2}

### 对象层级

```text
host/node
  -> PostgreSQL instance/server (one postmaster + PGDATA + port)
     -> PostgreSQL database cluster (all databases in that PGDATA)
        -> database
           -> schema
              -> relation/function/type/extension objects
```

PostgreSQL 官方术语中的 **database cluster** 是一个 server/PGDATA 管理的 database
集合，不等于三节点 HA cluster。

### Pigsty `pg_cluster`

Pigsty 把共享 `pg_cluster` 名称的 PostgreSQL instances 组织为一个管理/HA 单元：

```text
pg-test
  pg-test-1 primary
  pg-test-2 replica
  pg-test-3 replica/offline
```

每个 instance 有自己的 PGDATA，是同一 PostgreSQL system lineage 的物理副本。
`pg-meta` 与 `pg-test` 名称相近也可能拥有不同 system identifier，不能互相 restore/
rewind。

### 容易混淆的 identity

| 名词 | 示例 | 验证 |
|---|---|---|
| environment | `pg36-l2-vagrant` | authority/inventory/host set |
| node/host | `pg-test-1` | machine ID、address、OS |
| Pigsty cluster | `pg-test` | inventory + Patroni scope |
| instance/member | `pg-test-1` | Patroni member + PostgreSQL identity |
| PostgreSQL database cluster | instance PGDATA | system identifier/control data |
| database | `pg36_shop` | `current_database()` / `pg_database` |
| schema | `shop` | `pg_namespace` / `search_path` |
| role | `app_rw` | `current_user` / `pg_roles` |
| service | primary/replica/default/offline | HAProxy config + actual backend |

### service endpoint

服务端点表达能力语义，而不是机器：

```text
primary service  -> current writable authority, usually via pool
replica service  -> selected read-only members, may lag
default service  -> current primary direct PostgreSQL
offline service  -> offline/analytics-selected member
```

具体端口与 selector 以当前 Pigsty config 为准。DNS、VIP、HAProxy node 和 backend 是
不同层；连接串只显示入口，SQL identity 显示实际 backend。

### system identifier 与 timeline

```text
system identifier
  PostgreSQL lineage identity；不同初始化通常不同

timeline
  WAL history 分支；promotion 通常产生新 timeline

LSN
  某条 timeline/WAL stream 内的位置语义
```

同 LSN 字符串在不同 system/timeline 不能直接比较。failover、rewind、PITR、restore
必须同时证明 source direction、system identifier 和 timeline history。

## F.3 `[PG]`、`[平台]`、`[Pigsty]` 能力映射 {#appendix-f-3}

这些标签用于作者的能力分析，不出现在顶层导航标题中：

```text
PostgreSQL native capability
  引擎/SQL/catalog/tool 直接提供并可原生验证

generic platform responsibility
  任何生产数据库服务都必须承担，但不一定由 PostgreSQL 自己完成

Pigsty mapping
  Pigsty 对平台责任的具体组件、inventory、playbook、service 或 dashboard 实现
```

### 示例

| 主题 | PostgreSQL 原生 | 平台责任 | Pigsty 映射 |
|---|---|---|---|
| transaction | MVCC、isolation、lock、WAL | retry/idempotency、SLO | dashboard/query + service baseline |
| HA | streaming replication、timeline | quorum、fence、route、client outcome | Patroni + etcd + HAProxy/PgBouncer |
| backup | backup API、WAL/recovery | repository、retention、exercise、RPO | pgBackRest + policy/monitoring/playbook |
| security | role、HBA、TLS、RLS、audit hooks | identity/secrets/network/review | inventory + cert/access templates |
| observability | stats/views/logs | storage、dashboard、alert/notification | exporters + Victoria/Grafana/Alertmanager |
| capacity | counters/settings/execution | workload model、hardware/cost/headroom | host/PG monitoring + declarative baseline |

### 使用规则

1. 先解释 PostgreSQL 语义；
2. 再说明生产服务缺少什么组合责任；
3. 给出 Pigsty reference implementation；
4. 回到 SQL、config 或 component state 复核；
5. 标明替换平台时必须保留的责任，而不是复制 Pigsty 命令。

例如“backup green”不是 PostgreSQL 原生结论；它组合 pgBackRest、repository、monitor、
restore drill 与业务 manifest。迁移到 RDS/Operator 后工具不同，责任仍在。

## F.4 托管 RDS、自建 Patroni 与 Operator 的职责对照 {#appendix-f-4}

### 三种交付模型

| 责任 | 托管 PostgreSQL/RDS | 自建 Patroni/Pigsty | Kubernetes Operator |
|---|---|---|---|
| host/OS | provider 多数承担 | 用户/平台团队 | node/cloud + cluster platform |
| PostgreSQL config/version | API 约束下共享 | 用户完整承担 | CR/operator + image/package |
| HA control | provider 实现 | Patroni/DCS/route 自管 | operator + DCS/lease/service |
| backup repository | provider feature + 用户 policy | pgBackRest/repository 自管 | operator integration + storage |
| network/identity | provider primitive + 用户配置 | 用户全栈 | cloud/K8s/network policy + 用户 |
| monitoring | provider baseline + 用户 SLI | 用户组合全栈 | operator/exporter + platform |
| restore/failover validation | 用户仍需验证 | 用户需设计/执行 | 用户需设计/执行 |
| business invariant | 用户 | 用户 | 用户 |
| data classification/SLO | 用户 | 用户 | 用户 |

“托管”转移部分实施责任，不转移业务正确性、权限配置、查询/模式、RPO/RTO 接受、
external side effect 与 vendor failure 的验证责任。

### 自建 Patroni/Pigsty

优点：

```text
完整 PostgreSQL/extension/OS 控制
可审查组件与数据路径
统一声明式平台和可观测
```

代价：

```text
DCS/fencing/failure domain
package/OS/security lifecycle
backup repository and restore
on-call and incident authority
```

Pigsty 提供强 reference baseline，但 production topology、secrets、capacity、DR 与业务
合同仍由采用者验收。

### Operator

Operator 用 Kubernetes reconciliation 管理 PostgreSQL lifecycle；它不等于：

```text
Kubernetes automatically provides database consistency
pod restart equals failover safety
PVC equals backup
Service equals correct writer authority
```

需要理解 operator CRD、leader/lease、pod/PVC/node/zone failure domain、backup
integration、disruption/upgrade 和 platform control-plane dependency。

### 选择问题

```text
required PostgreSQL/extension control
team operating skill and on-call model
failure domains and regulatory/data residency
RPO/RTO and restore evidence
version/upgrade cadence
cost and lock-in
observability/export/access
exit and migration path
```

不要只比较“有没有 HA/backup”勾选项；比较故障模型、验证接口、责任边界和失败时的
authority。

---

[返回附录目录](../) · [对象与证据速查](../b/) ·
[第 1 章全局地图](/postgresql-pigsty-map/) · [查看全书目录](/toc/)
