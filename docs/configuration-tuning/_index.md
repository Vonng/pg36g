---
title: 第 27 章 精益求精：参数调优与资源治理
linkTitle: 27 精益求精：参数调优与资源治理
weight: 370
aliases:
- "/ch27/"
- "/volume-2/configuration-tuning/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch27
book_number: 27
book_part: part-5
book_status: draft
---

调优不是把一份“最佳参数”复制到 `postgresql.conf`。

同一个参数变化可能：

```text
让一条查询更快
  但让十条并发查询触发 OOM

减少 WAL
  但增加 primary CPU 和 replica replay CPU

提高单条分析查询速度
  但占满 parallel worker，让 OLTP tail latency 变差

增加连接槽
  但把 pool 中可控的队列搬进数据库

在 benchmark 中提高 TPS
  但降低 durability、HA headroom 或 recovery predictability
```

本章用一条严格的推理链替代参数清单：

```text
service objective
  -> observed bottleneck or resource risk
      -> parameter mechanism
          -> scope and precedence
              -> one-factor experiment
                  -> benefit + non-regression + failure behavior
                      -> rollback
                          -> ADR
```

如果中间缺了一环，默认动作不是“先改了看看”，而是补证据。

## 参数不是独立旋钮

PostgreSQL 参数形成资源系统：

```text
shared_buffers
  <-> OS page cache
  <-> checkpoint dirty-page work
  <-> max_wal_size

work_mem
  × active operations
  × sessions
  × parallel processes
  × hash_mem_multiplier

max_connections
  <-> backend/shared memory
  <-> pool queue
  <-> lock/context-switch pressure

parallel workers
  <-> CPU
  <-> work_mem
  <-> worker pool
  <-> other queries and maintenance

checkpoint / WAL
  <-> write smoothing
  <-> WAL volume
  <-> archive/replica
  <-> crash recovery time
```

所以本章不按字母解释 GUC，而按资源预算和失效机制组织。

## 本章实验故意得到“拒绝改参”

第 26 章参考 run 提供了几个事实：

- c8 时 server work ratio 约 84%，client 未先饱和；
- workload 使用 prepared protocol；
- 六个 cell 的 temp bytes 全为零；
- L 档有 block read，但 server iowait 很低；
- 只有 c1/c8，精确 knee 未知；
- production sustainable TPS 仍为 `null`。

这些事实**不支持**：

```text
increase work_mem
increase shared_buffers
increase max_connections
disable synchronous_commit
```

它们只使一个假设值得被证伪：

> prepared OLTP 在 `plan_cache_mode=auto` 下是否仍承担了足够的 custom planning
> 成本，使 `force_generic_plan` 获得至少 2% 的稳定收益？

正式实验只改变这个参数，而且只用 `PGOPTIONS` 改 benchmark session：

```text
baseline   plan_cache_mode=auto
candidate  plan_cache_mode=force_generic_plan
```

固定 M 数据、8 clients、prepared、50/30/20 mix；五组 paired repetition 使用相同
seed，A/B 顺序交错。共 10 次 12 秒 measured run、357,685 笔事务：

| arm | median TPS | pooled p50 | pooled p95 | pooled p99 | failure/late/skipped |
|---|---:|---:|---:|---:|---:|
| `auto` | 2,981.72 | 1.279 ms | 9.217 ms | 13.127 ms | 0 |
| `force_generic_plan` | 3,051.72 | 1.285 ms | 9.135 ms | 12.933 ms | 0 |

只看两个 median，candidate 好像快 2.35%。但正确的配对分析是：

```text
paired TPS ratio median       1.00735
bootstrap 95% interval        [0.98082, 1.02775]
candidate / baseline p95      0.99110
required bootstrap lower      >= 1.02
```

candidate 没有证明至少 2% 的稳定收益。plan probe 还发现：

```text
auto:
  first 5 custom + next 5 generic

force_generic_plan:
  10 generic + 0 custom
```

PostgreSQL 的 `auto` 已经为这两类稳定 plan 自动转向 generic。强制 generic 只省掉
少量早期 planning，却可能伤害参数敏感查询。最终 ADR：

```text
decision                    reject-persistent-change
persistent change applied   false
production gate             pending
```

这不是“没有调优成果”。它避免了一项没有稳定收益、却扩大 plan risk 的持久变更。

公共结果见 [`tuning-run.json`](/labs/ch27/tuning-run.json)，完整安全边界见
[`lab-contract.md`](/labs/ch27/lab-contract.md)。

## 本章学习成果

完成本章后，你应该能：

1. 从 SLO、bottleneck 和 non-regression 指标写调优假设；
2. 区分参数、SQL/schema、workload 与 topology 问题；
3. 为 shared memory、per-operation memory、maintenance 与 OS 留出完整预算；
4. 解释 `work_mem × 节点 × 并发 × parallel process` 的放大；
5. 用 WAL、checkpointer、I/O 与 recovery evidence 调整 checkpoint；
6. 区分 `effective_cache_size` estimate 与真实 cache allocation；
7. 校准 cost parameter，而不是用 `enable_seqscan=off` 长期逼 planner；
8. 计算 parallel worker 的 cluster budget 和降级行为；
9. 把 connection limit 与 pool/admission、reserved slot 和 emergency access 联动；
10. 从 `pg_settings.context/source/pending_restart` 判断变更方式；
11. 从 `pg_file_settings` 找出 syntax error 与被后项覆盖的配置；
12. 理解 system、database、role、role-in-database、session、transaction 的覆盖关系；
13. 用 Pigsty template、`pg_parameters` 与 IaC 保持 desired state；
14. 在 reload/restart/rolling change 前写 failure、rollback 与 validation；
15. 接受“拒绝修改”也是合格 ADR。

## 本章目录

### [27.1 调优是一套实验方法](01/)

- [27.1.1 先定义目标、瓶颈和不可退化指标](01/#item-27-1-1)
- [27.1.2 一次改变一个机制并准备回退](01/#item-27-1-2)
- [27.1.3 参数变化不修复错误 SQL 和错误模型](01/#item-27-1-3)

### [27.2 内存预算](02/)

- [27.2.1 shared buffers、操作系统页缓存与双重缓存](02/#item-27-2-1)
- [27.2.2 `work_mem` 按节点、并发和并行放大](02/#item-27-2-2)
- [27.2.3 maintenance、autovacuum 与后台进程内存](02/#item-27-2-3)
- [27.2.4 OOM 风险必须用最坏并发估算](02/#item-27-2-4)

### [27.3 WAL、检查点与写入平滑](03/)

- [27.3.1 WAL 生成、刷盘与提交延迟](03/#item-27-3-1)
- [27.3.2 检查点频率、写突发与恢复时间](03/#item-27-3-2)
- [27.3.3 压缩、全页写与归档代价](03/#item-27-3-3)

### [27.4 规划器、并行与连接参数](04/)

- [27.4.1 成本参数只能用硬件和计划证据校准](04/#item-27-4-1)
- [27.4.2 并行 worker 的全局预算与退化条件](04/#item-27-4-2)
- [27.4.3 连接上限、超时和锁等待边界](04/#item-27-4-3)

### [27.5 参数作用域与变更方式](05/)

- [27.5.1 编译、初始化、启动、reload 与会话级](05/#item-27-5-1)
- [27.5.2 系统、数据库、角色与事务覆盖层](05/#item-27-5-2)
- [27.5.3 配置漂移、审计、回退和滚动风险](05/#item-27-5-3)

### [27.6 模板参数与集群变更](06/)

- [27.6.1 从模板生成实例配置](06/#item-27-6-1)
- [27.6.2 区分 reload、restart 与滚动执行](06/#item-27-6-2)
- [27.6.3 用 SQL 和文件事实验证最终生效值](06/#item-27-6-3)

### [27.7 实战：只调一个已证实的瓶颈](07/)

- [27.7.1 从 ch26 证据提出参数假设](07/#item-27-7-1)
- [27.7.2 比较收益、副作用和故障恢复](07/#item-27-7-2)
- [27.7.3 输出参数 ADR、回退条件与拒绝修改项](07/#item-27-7-3)

## 阅读路线

应用开发者：

```text
27.1 -> 27.2.2 -> 27.4 -> 27.5.2 -> 27.7
```

重点是 per-query memory、plan、timeout、role/database scope 和 A/B。

平台工程师：

```text
27.1 -> 27.2 -> 27.3 -> 27.5 -> 27.6 -> 27.7
```

重点是 cluster resource budget、WAL/recovery、配置来源、IaC 与 rolling risk。

两条路线必须合流：应用知道 transaction 与 query shape，平台知道 failure domain 与
global resource envelope；任何一方单独调参都容易优化局部、破坏整体。

## 实验文件

```text
static/labs/ch27/
├── requirements.json
├── parameter-candidates.json
├── change-contract.json
├── negative-cases.json
├── topology.mmd
├── lab-contract.md
├── setup.sql
├── reset-run.sql
├── read-product.sql
├── read-order.sql
├── place-order.sql
├── plan-probe-counts.sql
├── plan-probe-product.sql
├── plan-probe-order.sql
├── remote_experiment.py
├── capture.py
├── exercise.py
├── validate.py
├── review.py
├── task.sh
└── tuning-run.json
```

实验：

- 只测试一个参数；
- 只在 benchmark session 生效；
- 不使用 `ALTER SYSTEM`、DCS edit、reload/restart；
- 保留 raw transaction log 与 plan-shape evidence；
- 用 28 个对抗变体验证 target、scope、配对、quantile、decision 和 cleanup；
- 专用 database、role 与远端临时目录全部清理；
- 不管 candidate 接受或拒绝，production gate 都保持 `pending`。

## 参考资料

- [PostgreSQL 18 server configuration](https://www.postgresql.org/docs/18/runtime-config.html)
- [PostgreSQL 18 setting parameters](https://www.postgresql.org/docs/18/config-setting.html)
- [PostgreSQL 18 resource consumption](https://www.postgresql.org/docs/18/runtime-config-resource.html)
- [PostgreSQL 18 WAL configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html)
- [PostgreSQL 18 query planning](https://www.postgresql.org/docs/18/runtime-config-query.html)
- [PostgreSQL 18 `pg_settings`](https://www.postgresql.org/docs/18/view-pg-settings.html)
- [PostgreSQL 18 `pg_file_settings`](https://www.postgresql.org/docs/18/view-pg-file-settings.html)
- [Pigsty parameter optimization policy](https://pigsty.io/docs/pgsql/template/tune/)
- [Pigsty PostgreSQL parameter scopes](https://pigsty.io/docs/pgsql/config/param/)

---

[上一章：胸有成竹：容量规划与压测基线](/capacity-benchmarking/) · [返回下卷导读](/lower-volume/) · [下一章：除旧布新：VACUUM、冻结与膨胀治理](/vacuum-freeze-bloat/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
