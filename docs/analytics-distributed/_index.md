---
title: 第 17 章 合纵连横：分析加速与分布式选型
linkTitle: 17 合纵连横：分析加速与分布式选型
weight: 270
aliases:
- "/ch17/"
- "/volume-1/analytics-distributed/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch17
book_number: 17
book_part: part-3
book_status: draft
---

“数据越来越多，所以要上分布式”不是一个架构结论，只是一句尚未完成的
问题描述。

同样一条慢月报，可能分别来自：

```text
统计信息失真
  -> 规划器选错路径
缺少合适索引
  -> 选择性查询扫描过多数据
work_mem 不足
  -> 排序或哈希落到临时文件
每次重算历史事实
  -> 缺少可接受新鲜度的汇总层
OLTP 与 OLAP 争用资源
  -> 缺少负载隔离
单节点资源确已越界
  -> 才可能需要横向拆分
```

若不先辨认瓶颈，把数据分到更多节点只会把一个可观测的本地问题变成网络、
路由、远端事务、再平衡和部分失败共同参与的问题。

本章坚持一条次序：

> 先定义服务目标，再证明单机边界；先减少无效工作，再隔离负载；只有明确
> 哪一种资源无法在单节点满足目标后，才比较分布式候选。

这并不是反对分布式。恰恰相反，只有把进入条件、分布键、数据局部性、
失败语义和撤退路线写清楚，分布式才是一项可评审的工程决策，而不是对增长
焦虑的技术性反射。

## 本章完成后

你应当能够：

- 把“分析慢”改写为数据量、并发、P50/P95/P99、吞吐、新鲜度、正确性、
  RPO/RTO 和成本目标；
- 区分 CPU、存储 I/O、缓存、临时文件、锁等待、计划误差和远端传输瓶颈；
- 用 `EXPLAIN (ANALYZE, BUFFERS)`、系统统计和冻结工作负载建立单机证据；
- 从计划中识别 `Gather`、parallel scan、partial/final aggregate 与实际
  worker 数；
- 解释“计划允许并行”与“执行时拿到 worker”为什么是两件事；
- 用 covering B-tree、BRIN、物化汇总和批处理分别解决不同访问形状；
- 解释 Index Only Scan 的 visibility map 前置条件，不把一次偶然计划当
  稳定合同；
- 用 `work_mem` 的外排/内排反例说明为什么不能按单查询峰值做全局调参；
- 区分 PostgreSQL 原生物化视图的完整刷新与应用维护的增量汇总；
- 识别 OLTP/OLAP 共存时对 CPU、buffer、temp、WAL、vacuum 和副本延迟的
  竞争；
- 写出进入分布式评审的硬门槛，而不是只写“未来数据会增长”；
- 选择候选分布键，计算数据倾斜，并审计跨分片查询、JOIN、事务与唯一性；
- 解释 PostgreSQL HASH 分区 remainder 为什么不等于整数 `% modulus`；
- 比较 PostgreSQL 扩展、兼容数据库与专用 OLAP 时区分 SQL、类型、事务、
  扩展、运维和故障兼容；
- 用相同冻结输入、相同查询和相同失败条件比较候选；
- 通过 `postgres_fdw` 计划分清过滤下推、聚合下推、协调端聚合与行传输；
- 解释“数据同分片”为什么仍不能自动证明某条 JOIN 已被下推；
- 定义单分片不可达时，单租户读、全局读、写入与重试分别应如何表现；
- 在 Pigsty 中把分析读隔离到 offline replica，或声明一个待验收的 Citus
  拓扑，同时不把配置片段当生产验收；
- 输出一份包含证据、限制、生产代价、复审触发器和退出路线的 ADR。

## 贯穿本章的销售分析

实验生成一份完全确定的合成数据：

```text
8 tenants
50 accounts per tenant
120 days
5 sales per account per day

400 accounts
240,000 sales
1,200,000 units
2,256,000.00 amount
```

同一份业务月报由四条路径计算：

```text
local raw facts
local daily materialized summary
partitioned postgres_fdw parent
two-stage remote daily + coordinator monthly aggregation
```

四条路径都必须逐字节等于
[`frozen-monthly.csv`](/labs/ch17/frozen-monthly.csv) 的 32 行。正确性不一致
时，不允许继续比较计划或性能。

冻结事实：

| 项目 | 数值 |
|---|---:|
| 本地事实 | 240,000 行 |
| shard A / shard B | 120,000 / 120,000 行 |
| 本地日汇总 | 2,880 行 |
| 最终月报 | 32 行 |
| 租户 3 的 4 月 | 7,500 笔，69,375.00 |
| 朴素 FDW 返回协调端 | 240,000 行 |
| 两阶段聚合返回协调端 | 960 行 |
| 业务校验和 | `42fb8ab5444469eba1f104a8e1e529dd` |
| 月报校验和 | `644d45544ebbc2a80c42270c38ac6885` |

这里的“返回行数”描述数据流形状，不是网络字节，也不是耗时。三个数据库都在
一台机器的一个 PostgreSQL 18.4 实例中，没有独立 CPU、磁盘、网络或故障域。

## 先看单机还能做什么

冻结计划证明四件不同的事。

月聚合可并行：

```text
Finalize HashAggregate
  -> Gather
       Workers Planned: 2
       Workers Launched: 2
       -> Partial HashAggregate
            -> Parallel Seq Scan on sales_fact
```

租户 3 的选择性查询可走 covering index：

```text
Index Only Scan using sales_fact_tenant_day_idx
  actual rows=7500
  Heap Fetches: 0
```

`Heap Fetches: 0` 并不是 `INCLUDE` 自动保证的。实验重建后显式执行
`VACUUM (ANALYZE)`，让 visibility map 建立 all-visible 信息，再验证零回表。
如果跳过这一步，新表可能合理地使用 Bitmap Heap Scan。

同一排序在两个会话级配置下呈现不同资源路径：

```text
work_mem=64kB -> external merge, Disk ~= 5.9MB
work_mem=32MB -> quicksort, Memory ~= 13.6MB
```

这只说明 spill 可被计划证据观察。一个查询需要 32MB，不等于应该把全局
`work_mem` 设置成 32MB；一个并发查询可以包含多个 sort/hash 节点，还有
并行 worker 和并发会话共同放大内存。

物化日汇总把月报输入从 240,000 行降为 2,880 行，但随之引入：

```text
freshness target
refresh schedule
refresh failure recovery
late-arriving correction
locking and WAL cost
definition version
```

PostgreSQL 的物化视图持久保存查询结果，读取时像表；数据不会自动保持最新，
需要 `REFRESH MATERIALIZED VIEW`。官方
[Materialized Views](https://www.postgresql.org/docs/18/rules-materializedviews.html)
把“读得更快”与“可能不新鲜”明确放在同一项权衡里。

## 再看分布式改变了什么

实验的协调端由 LIST 分区父表接管两个外表：

```text
sales_fact_distributed PARTITION BY LIST (tenant_id)
├── sales_fact_dist_0: tenants 2,4,6,8 -> pg36_shard_a
└── sales_fact_dist_1: tenants 1,3,5,7 -> pg36_shard_b
```

租户 3 的查询只访问 shard B，计划中的远端 SQL 带上租户和日期：

```text
Foreign Scan on sales_fact_dist_1
Remote SQL:
  SELECT amount
  FROM shop_ch17_shard.sales_fact
  WHERE occurred_on >= '2026-04-01'
    AND tenant_id = 3
```

全局月报若直接从分区父表聚合，两个 Foreign Scan 各返回 120,000 行，
协调端接收 240,000 条事实后聚合。改成每个远端先按租户、日期聚合：

```text
shard A: 120,000 facts -> 480 daily aggregates
shard B: 120,000 facts -> 480 daily aggregates
coordinator: 960 daily aggregates -> 32 monthly rows
```

结果相同，传输形状完全不同。这是分布式查询最重要的思维之一：

> 尽量让过滤、连接和聚合靠近数据发生；但必须用实际计划证明下推，不可从
> SQL 外观或拓扑图推断。

反例也被固定下来：租户 3 的账户与销售位于同一分片，查询通过两个分区外表
父表连接时，实测仍在协调端执行 `Hash Join`，接收 7,500 条销售与 50 条
账户。`postgres_fdw` 的远端优化、代价、`fetch_size`、连接与事务管理以
PostgreSQL 官方
[`postgres_fdw`](https://www.postgresql.org/docs/18/postgres-fdw.html)
文档为准。

## HASH 分区不是整数取模

本章第一版失败原型使用：

```text
remote fixture routing = tenant_id % 2
coordinator routing = PARTITION BY HASH (tenant_id)
```

它们不是同一算法。PostgreSQL HASH 分区先使用数据类型的哈希支持函数，再按
`MODULUS/REMAINDER` 判断分区；`REMAINDER 0` 不表示“偶数值”。当查询带
`tenant_id` 时，协调端会按自己的哈希算法裁剪到一个分区，而目标租户可能被
生成器放在另一个数据库，于是出现“全表看似有数据，按租户裁剪却静默漏数”
的危险结果。

冻结实验改用显式 LIST 路由，使物理分片和协调端边界完全一致。生产系统不应
手写八个租户清单，而应让同一个经过版本化的路由算法或分片元数据成为写入、
读取、再平衡和恢复的共同事实来源。

PostgreSQL 官方
[Table Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
说明 HASH 分区以 modulus/remainder 描述分区边界；不能把这些名词误读为对
原始整数直接做 `%`。

## Pigsty 中的两条候选路径

本章不把 Pigsty 等同于某一种分布式数据库。它首先提供一种声明和交付运行
环境的方法。

路径 A 是保留一个 PostgreSQL 数据体系，把 OLAP/ETL/交互慢查询隔离到
offline replica 或带 `pg_offline_query` 标签的副本：

```yaml
all:
  children:
    pg-analytics:
      hosts:
        10.10.10.11: { pg_seq: 1, pg_role: primary }
        10.10.10.12:
          pg_seq: 2
          pg_role: replica
          pg_offline_query: true
      vars:
        pg_cluster: pg-analytics
        pg_conf: olap.yml
```

路径 B 是在硬门槛满足后评估 Citus。Pigsty 4.4 文档要求 Citus 拓扑声明
`pg_mode: citus`、`pg_shard`、各分片的 `pg_group`、`pg_primary_db`，
并配置数据节点间访问规则；完整生产设计还必须补齐 coordinator/worker HA、
服务路由、备份恢复、再平衡、监控和升级。

Pigsty 的
[配置入口](https://pigsty.io/docs/pgsql/config/)
和
[集群/实例类型](https://pigsty.io/docs/pgsql/config/cluster/)
给出了 offline 与 Citus 的当前声明方式。本章资产
[`pigsty-declaration.example.yml`](/labs/ch17/pigsty-declaration.example.yml)
只是两个互斥候选的草图，未执行 L1，不能直接合并进生产 inventory。

## 实验资产

规范与决策：

- [实验合同](/labs/ch17/lab-contract.md)
- [ADR-017](/labs/ch17/analytics-distributed-adr.md)
- [冻结夹具清单](/labs/ch17/fixture-manifest.json)
- [v1.5 proposal](/labs/ch17/baseline-v1.5-proposal.json)
- [Pigsty 4.4 拓扑草图](/labs/ch17/pigsty-declaration.example.yml)

生成与建立：

- [数据库壳 bootstrap](/labs/ch17/bootstrap.sql)
- [本地确定性生成器](/labs/ch17/fixture.sql)
- [远端确定性生成器](/labs/ch17/fixture-remote.sql)
- [分片建立](/labs/ch17/remote-setup.sql)
- [协调端建立](/labs/ch17/setup.sql)
- [协调端环境保护](/labs/ch17/context.sql)
- [远端环境保护](/labs/ch17/remote-context.sql)

结果与计划：

- [本地月报](/labs/ch17/monthly-local-export.sql)
- [物化汇总月报](/labs/ch17/monthly-summary-export.sql)
- [朴素分布式月报](/labs/ch17/monthly-distributed-export.sql)
- [两阶段分布式月报](/labs/ch17/monthly-two-stage-export.sql)
- [本地并行计划](/labs/ch17/local-parallel-plan.sql)
- [低内存 spill 计划](/labs/ch17/spill-low-plan.sql)
- [高内存计划](/labs/ch17/spill-high-plan.sql)
- [覆盖索引计划](/labs/ch17/selective-index-plan.sql)
- [租户裁剪计划](/labs/ch17/tenant-pruned-plan.sql)
- [朴素 FDW 计划](/labs/ch17/distributed-naive-plan.sql)
- [两阶段聚合计划](/labs/ch17/distributed-two-stage-plan.sql)
- [同分片 JOIN 反例](/labs/ch17/collocated-parent-plan.sql)

审计与退出：

- [单分片失败探针](/labs/ch17/shard-failure.sql)
- [协调端验证](/labs/ch17/verify.sql)
- [远端验证](/labs/ch17/remote-verify.sql)
- [最终状态](/labs/ch17/final-state.sql)
- [自动审查器](/labs/ch17/review.py)
- [协调端精确复位](/labs/ch17/reset.sql)
- [远端精确复位](/labs/ch17/remote-reset.sql)
- [任务驱动器](/labs/ch17/task.sh)

## 快速运行

本地开发数据库先完成第 4 章的角色与物理模型，然后提供管理员 service：

```bash
export PGSERVICEFILE=/path/to/pg_service.conf
export PGSERVICE=pg36-admin

PG36_EVIDENCE_DIR="$PWD/evidence/ch17" \
  ./static/labs/ch17/task.sh all
```

`all` 会执行两个完整周期：

```text
bootstrap retained database shells
  -> rebuild shard A and B
  -> rebuild coordinator
  -> export and compare four monthly paths
  -> collect local and distributed plans
  -> prove application write denial
  -> make shard B temporarily unreachable
  -> prove shard A scoped read still works
  -> prove global read fails with 08001
  -> review all evidence
  -> prove reset token/target/active-worker guards
  -> pre-verify all three databases
  -> exact per-database reset
  -> rebuild everything
  -> repeat evidence and review
```

正式实测输出：

```text
status=ok
fixture=frozen-byte-identical-four-paths
single_node=parallel+index+summary+spill
distributed=tenant-pruning+fdw+two-stage
counterexamples=hash-is-not-modulo+join-not-pushed
failure=healthy-shard-read+global-08001
guards=P3660+P3661+P3663
postgres_fdw=1.2
pigsty_l1=not-run
release_candidate_checksum=3dcb7308cf6983122ee860ad3dc2a4b44651549e3d5631770839bb9a0be450c6
```

> **破坏边界**
>
> `task.sh all` 会在精确身份、marker、对象清单、权限和数据校验和匹配后，
> 删除并重建 `shop_ch17`、`shop_ch17_ext`、两个 foreign server、六个
> user mapping，以及两个分片数据库中的 `shop_ch17_shard`。它保留空的
> `pg36_shard_a`、`pg36_shard_b` 数据库壳。只可用于本书受控开发 fixture，
> 不得在生产执行。

## 本章目录

### [17.1 先证明单机边界](01/)

- [17.1.1 定义数据量、并发、延迟与新鲜度目标](01/#item-17-1-1)
- [17.1.2 区分 CPU、I/O、内存、锁与计划瓶颈](01/#item-17-1-2)
- [17.1.3 单机未被正确使用前不急于分布式](01/#item-17-1-3)

### [17.2 单机分析能力](02/)

- [17.2.1 并行扫描、连接、聚合与限制](02/#item-17-2-1)
- [17.2.2 分区、物化视图、增量汇总与批处理](02/#item-17-2-2)
- [17.2.3 列式能力候选必须写入版本基线](02/#item-17-2-3)
- [17.2.4 OLTP 与分析负载在同机共存的代价](02/#item-17-2-4)

### [17.3 何时需要分布式](03/)

- [17.3.1 容量、吞吐、地域与组织边界](03/#item-17-3-1)
- [17.3.2 分片键、数据局部性与跨分片事务](03/#item-17-3-2)
- [17.3.3 一致性、运维复杂度与退出成本](03/#item-17-3-3)

### [17.4 比较分布式候选](04/)

- [17.4.1 PostgreSQL 扩展、兼容数据库与专用分析系统](04/#item-17-4-1)
- [17.4.2 SQL 兼容不等于事务、扩展和运维兼容](04/#item-17-4-2)
- [17.4.3 用同一工作负载和失败条件比较](04/#item-17-4-3)

### [17.5 部署最小分布式 PoC](05/)

- [17.5.1 明确 PoC 只验证一个关键假设](05/#item-17-5-1)
- [17.5.2 记录组件、版本、拓扑和数据分布](05/#item-17-5-2)
- [17.5.3 不把演示集群的绝对性能外推到生产](05/#item-17-5-3)

### [17.6 实战：从单机证据到选型 ADR](06/)

- [17.6.1 证明一个边界，拒绝一个伪瓶颈](06/#item-17-6-1)
- [17.6.2 比较单机加速与一个分布式候选](06/#item-17-6-2)
- [17.6.3 输出 ADR、PoC 证据、生产代价和撤退路线](06/#item-17-6-3)
- [17.6.4 验收采用 `checklist:evidence`](06/#item-17-6-4)

---

[上一章：经天纬地：时序、空间与时空查询](/spatiotemporal/) · [返回上卷导读](/upper-volume/) · [下一章：万法归宗：PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
