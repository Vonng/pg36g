---
title: 第 29 章 移花接木：逻辑复制、迁移与异构同步
linkTitle: 29 移花接木：逻辑复制、迁移与异构同步
weight: 390
aliases:
- "/ch29/"
- "/volume-2/logical-replication-migration/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch29
book_number: 29
book_part: part-5
book_status: draft
---

逻辑复制能让数据流动，但“数据正在流动”离“迁移已经成功”还很远。

publication 不复制 DDL，sequence 不随表中 identity 值推进，大对象不在复制范围内；
subscription 停止后，slot 仍可能继续保留 WAL 与 catalog rows；本地写入 subscriber
既可能造成会报错的 apply conflict，也可能留下完全不报错的静默漂移；在切换窗口里，
源端是否真的停止写、目标序列是否安全、目标新增写如何反向带回，决定了回退是不是一句
空话。

本章把迁移建模为一个有证据、有门禁、可失败关闭的状态机：

```text
inventory and semantic preflight
  -> target schema
      -> initial snapshot
          -> incremental stream
              -> catch-up fence
                  -> source write fence
                      -> sequence / external state sync
                          -> shadow verification
                              -> route switch
                                  -> observation
                                      -> forward or rollback decision
```

其中每一条箭头都有前置条件、观测、超时、停手方式与恢复路径。不能用最终行数相同跳过
中间状态，也不能把“DNS 已改”当成目标端数据、权限和业务语义已经可用。

## 本章目标

理解逻辑复制、CDC 和数据搬迁的状态机，用校验与可回退切换完成迁移，而不是把“数据能流动”误当成迁移成功。

读完本章，读者应该能够：

1. 从 WAL、output plugin、publication、slot、subscription 和 apply worker 解释原生
   逻辑复制的数据路径；
2. 区分 initial table synchronization、持续 DML 与独立的 schema/sequence 迁移；
3. 为表选择 primary key、`REPLICA IDENTITY USING INDEX` 或受约束的 `FULL`；
4. 用 `pg_replication_slots`、`pg_stat_subscription`、
   `pg_stat_subscription_stats` 与 `pg_subscription_rel` 定位停滞和冲突；
5. 解释 slot 为什么提供可恢复位点，却不能天然提供 exactly-once 的外部副作用；
6. 为 CDC sink 设计 event identity、幂等提交、位点原子性与 replay 策略；
7. 设计 `COPY`/dump/restore 的并行装载顺序，并保留 rejected rows；
8. 用行数、摘要、分桶、不变量和抽样分别验证结构与数据；
9. 把在线迁移拆成 preflight、全量、增量、追平、写围栏、切流、观察和退出；
10. 区分 rollback、forward repair 与已经跨过不可逆点的前滚；
11. 为异构系统显式记录类型、精度、时区、排序、约束、顺序和 delete 语义损失；
12. 用 Pigsty 生成迁移上下文、观察两端集群，但不把生成脚本误认为自动切流授权；
13. 建立源、目标、验证和管理端点的独立凭据与网络边界；
14. 在源端主库切换时评审 logical slot failover，而不是默认 subscription 会自动跟随；
15. 完成一份含原始证据、公开摘要、回退记录和双端精确清理的迁移证据包。

## 一张图看清复制与迁移

```text
publisher database
  table DML
    -> WAL
      -> logical decoding
        -> pgoutput
          -> publication filter
            -> logical slot
              -> streaming protocol
                -> subscriber apply worker
                  -> same qualified table name

separate migration tracks
  DDL / ownership / privileges
  sequences
  large objects
  extensions and settings
  application routes and credentials
  validation and rollback state
```

publication 是某一个数据库中的变更集合；subscription 定义下游连接、publication
集合和 apply 行为；一个活动 subscription 通常对应源端一个持久 logical slot，初始
复制还会短暂创建 table synchronization slots。slot 的名称在整个 PostgreSQL cluster
中唯一，但 logical slot 只属于一个 database。

初始复制完成后，`pg_subscription_rel.srsubstate = 'r'` 只说明表同步状态 ready；
它不证明 sequence、DDL 或业务不变量一致。迁移验收必须把 PostgreSQL 内建状态与
独立 reconciliation 同时纳入。

## 本章正式实验

本章在两个具有不同 PostgreSQL system identifier 的 Pigsty 沙箱集群之间执行：

```text
source       pg-test / pg36_shop_src
target       pg-meta / pg36_shop_dst
PostgreSQL   18.4 on both sides
wal_level    logical
data         synthetic only
route        private evidence simulation only
production   not touched
```

正式 run：

```text
run id       7d95ca65-12a7-46c2-8e6c-ad8cbb5336c5
preflight    568c4034-5b7c-4be1-a5e0-48fa189bb782
source sysid 7668025967696967004
target sysid 7668025945980641675
```

初始复制：

| 对象 | 行数 | table sync state | logical manifest |
|---|---:|---|---|
| `shop.customers` | 5,000 | `r` | 相等 |
| `shop.orders` | 20,000 | `r` | 相等 |

随后增量执行：

```text
INSERT 500
UPDATE 200
DELETE 100
source marker acknowledged
logical manifests equal
```

暂停 subscription 后写入 3,000 行：

| 证据 | 暂停前 | 暂停后 |
|---|---:|---:|
| slot active | false | false |
| `confirmed_flush_lsn` | 不变 | 不变 |
| retained bytes | 227,008 | 2,867,128 |

恢复 subscription 后，marker 被确认且双端重新相等。

冲突与静默漂移：

```text
order_id 900000
  target local row + source incoming row
  -> confl_insert_exists: 0 -> 1
  -> apply_error_count:    0 -> 1
  -> remove exact target conflict
  -> replay and converge

order_id 1
  target-only value change
  -> no apply error required
  -> bucket 1 digest mismatch
  -> source-authoritative repair
  -> zero mismatched buckets
```

切换与回退：

```text
source runtime write attempt     SQLSTATE 42501
target sequence before           1
target sequence synchronized     900000
first target canary              900001
private route history            source -> target -> source
real platform route changed      false
target-only rows reconciled      1
source retained through rollback true
final customers                  5000
final orders                     23402
final manifests equal            true
orphan / negative / invalid      0 / 0 / 0
```

最后普通删除两端数据库、五个角色、subscription 与 slot；未使用 force drop，未终止
无关会话。29 个预声明反例和 19 个现场证据 mutant 全部被拒绝。公开结果见
[`migration-run.json`](/labs/ch29/migration-run.json)。

## 本章目录

### [29.1 逻辑复制原语](01/)

- [29.1.1 publication、subscription 与 replication slot](01/#item-29-1-1)
- [29.1.2 初始同步、流式变更与复制身份](01/#item-29-1-2)
- [29.1.3 DDL、序列、大对象与冲突边界](01/#item-29-1-3)

先建立 PostgreSQL 原生模型：哪些对象定义变更集，哪些对象保存位点，初始快照如何追上
主 apply 流，以及 UPDATE/DELETE 怎样定位目标行。最后明确没有进入这条流的内容。

### [29.2 CDC 与复制槽治理](02/)

- [29.2.1 逻辑解码、插件与消费位点](02/#item-29-2-1)
- [29.2.2 至少一次、重复事件与下游幂等](02/#item-29-2-2)
- [29.2.3 槽停滞、WAL 保留与磁盘风险](02/#item-29-2-3)

从内建 subscription 扩展到通用 CDC：区分产生事件、传输、处理、提交外部副作用与推进
位点，解释重放和重复为什么不可避免，并把 inactive slot 转成可预算的 source risk。

### [29.3 批量装载与数据校验](03/)

- [29.3.1 `COPY`、并行、约束和索引顺序](03/#item-29-3-1)
- [29.3.2 行数、摘要、分桶与业务不变量](03/#item-29-3-2)
- [29.3.3 装载速度不能牺牲可追溯错误](03/#item-29-3-3)

迁移常常先以批量方式搬运基线。本节讨论 server-side `COPY`、client-side `\copy`、
并行与约束顺序，重点是如何把坏行、批次、源文件散列和最终 reconciliation 留下来。

### [29.4 在线迁移状态机](04/)

- [29.4.1 预检查、全量、增量、追平与冻结窗口](04/#item-29-4-1)
- [29.4.2 影子读、双读、切流和观察](04/#item-29-4-2)
- [29.4.3 回退点、前滚点与不可逆动作](04/#item-29-4-3)

把工具动作提升为迁移项目：每一 phase 有 entry condition、exit evidence、owner、timeout
与 abort path。读路径和写路径分别验证，切换不是单一时刻，而是逐步关闭不确定性的过程。

### [29.5 异构同步的语义损失](05/)

- [29.5.1 类型、精度、排序规则与时区](05/#item-29-5-1)
- [29.5.2 约束、事务顺序与删除语义](05/#item-29-5-2)
- [29.5.3 目标端可查询不等于语义等价](05/#item-29-5-3)

跨引擎 CDC 不能只看连接器“green”。本节用可声明的 semantic contract 记录类型映射、
精度、排序、事务边界、tombstone、约束和重新处理行为，再用代表性查询验证目标用途。

### [29.6 多集群迁移环境](06/)

- [29.6.1 源、目标、验证端点与隔离凭据](06/#item-29-6-1)
- [29.6.2 观察槽、WAL、延迟与切换流量](06/#item-29-6-2)
- [29.6.3 保留源环境直到退出观察窗口](06/#item-29-6-3)

用 Pigsty 承担集群、端点、监控和迁移上下文的参考实现。明确
`pgsql-migration.yml` 生成的是操作手册与脚本，真实写围栏、路由和退出仍需按应用接入
方式设计、审批与执行。

### [29.7 实战：迁移 `pg36_shop`](07/)

- [29.7.1 完成全量加增量同步](07/#item-29-7-1)
- [29.7.2 注入消费者停滞与数据差异](07/#item-29-7-2)
- [29.7.3 验证、切流、回退并输出迁移证据包](07/#item-29-7-3)

用本章 runner 重演完整双集群实验，阅读私有证据与公开白名单，练习如何从一个失败阶段
安全恢复，而不是只观察成功路径。

## 推荐学习路线

应用开发者：

```text
29.1 -> 29.3 -> 29.4 -> 29.5 -> 29.7
```

重点是 schema/sequence 边界、数据校验、应用兼容、读写切换与异构语义。

平台工程师：

```text
29.1 -> 29.2 -> 29.4 -> 29.6 -> 29.7
```

重点是 slot/WAL、权限、进度、故障恢复、源端主库切换和迁移证据。

两条路线最终必须合流：平台可以保证 stream 可用，无法替应用决定订单状态是否等价；
应用可以定义不变量，无法独自保证 slot、磁盘、网络和切换窗口。

## 版本与证据权威

本章 PostgreSQL 语义以 18 为基线，正式 run 使用 18.4。逻辑复制能力跨版本变化明显：
row filter、column list、binary、streaming、two-phase、conflict statistics、failover
slot、generated columns 与 subscription 权限都必须以源、目标**实际 major/minor**
的官方文档为准。

Pigsty 示例以 4.4 为参考。当前 `pgsql-migration.yml` 生成迁移上下文、操作手册和脚本，
不会替操作者直接完成真实路由。生成物需要进入变更评审，secret 也不能因为出现在模板里
就进入仓库或公开证据。

核心资料：

- [PostgreSQL 18：Logical Replication](https://www.postgresql.org/docs/18/logical-replication.html)
- [PostgreSQL 18：Publication](https://www.postgresql.org/docs/18/logical-replication-publication.html)
- [PostgreSQL 18：Subscription](https://www.postgresql.org/docs/18/logical-replication-subscription.html)
- [PostgreSQL 18：Conflicts](https://www.postgresql.org/docs/18/logical-replication-conflicts.html)
- [PostgreSQL 18：Monitoring](https://www.postgresql.org/docs/18/logical-replication-monitoring.html)
- [PostgreSQL 18：Logical Decoding Concepts](https://www.postgresql.org/docs/18/logicaldecoding-explanation.html)
- [PostgreSQL 18：`pg_replication_slots`](https://www.postgresql.org/docs/18/view-pg-replication-slots.html)
- [PostgreSQL 18：`COPY`](https://www.postgresql.org/docs/18/sql-copy.html)
- [Pigsty：Data Migration](https://pigsty.io/docs/pgsql/migration/)
- [Pigsty：PGSQL Replication Dashboard](https://pigsty.io/docs/pgsql/dashboard/)

## 实验文件

```text
static/labs/ch29/
├── requirements.json
├── migration-contract.json
├── negative-cases.json
├── topology.mmd
├── lab-contract.md
├── capture.py
├── remote_experiment.py
├── exercise.py
├── validate.py
├── review.py
├── task.sh
└── migration-run.json
```

执行：

```bash
static/labs/ch29/task.sh lint

export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch29-run
static/labs/ch29/task.sh capture
static/labs/ch29/task.sh exercise
static/labs/ch29/task.sh verify
static/labs/ch29/task.sh review
```

`all` 会按相同顺序执行。`exercise` 会在两个沙箱集群上真实创建 subscription/slot、
生成 WAL 并注入冲突，只能在明确的一次性开发/测试环境运行。

## 本章验收

只有当迁移证据包能回答以下问题，才算完成：

```text
exact source and target identity
schema / extension / collation / setting diff
publication table and replica identity inventory
initial table synchronization states
source marker LSN and subscriber acknowledgement
slot restart / confirmed LSN, wal_status and safe_wal_size
row count + digest + bucket + business invariant
DDL / sequence / large object / external object plan
apply conflict statistics and repair record
source write-fence proof
route change, owner and rollback point
destination-only write reconciliation
source retention and exit criteria
subscription / slot / credential cleanup
production approval state
```

“两端 `count(*)` 相等”不是迁移验收。

---

[上一章：除旧布新：VACUUM、冻结与膨胀治理](/vacuum-freeze-bloat/) · [返回下卷导读](/lower-volume/) · [下一章：推陈出新：版本升级与回滚策略](/version-upgrade/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
