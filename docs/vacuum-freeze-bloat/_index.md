---
title: 第 28 章 除旧布新：VACUUM、冻结与膨胀治理
linkTitle: 28 除旧布新：VACUUM、冻结与膨胀治理
weight: 380
aliases:
- "/ch28/"
- "/volume-2/vacuum-freeze-bloat/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch28
book_number: 28
book_part: part-5
book_status: draft
---

PostgreSQL 的写入并不在提交时把旧世界擦掉。

`UPDATE` 写出新行版本，`DELETE` 标记旧版本失效；旧版本必须继续存在，直到所有可能看见
它的快照都离开。这个选择换来了读写并发，也把空间、统计、事务年龄和索引维护变成一套
持续运行的生命周期：

```text
write
  -> create obsolete row versions
      -> wait until no snapshot can see them
          -> prune / VACUUM
              -> make page space reusable
                  -> update FSM / VM / statistics
                      -> freeze old XID / MXID
```

这条链上任一环被阻断，表现都可能是“膨胀”，但处理方法完全不同：

```text
autovacuum 尚未触发         -> 触发参数与变化速率
worker 已触发但排队         -> worker / I/O / cost budget
VACUUM 扫过却没清掉         -> 长快照、槽、预备事务
页内空间已经可重用          -> 不一定需要缩小文件
数据稳定但 XID 很老         -> aggressive vacuum / freeze
heap 正常但 index 膨胀      -> index diagnosis / reindex
过期数据天然按时间成片      -> detach partition，不做海量 DELETE
```

所以本章不把 `VACUUM` 当作一个“清垃圾命令”，而把它放回四条相互关联的控制回路：

| 控制回路 | 主要问题 | 关键证据 |
|---|---|---|
| MVCC 回收 | 哪些旧版本已经无人可见 | `backend_xmin`、`pgstattuple`、dead tuple |
| 空间与访问 | 空间能否复用，VM/FSM 是否更新 | relation size、FSM、VM、HOT |
| 事务年龄 | 离回卷保护线还有多远 | `relfrozenxid`、`datfrozenxid`、`relminmxid` |
| 结构与生命周期 | 是否需要重建或整片退役 | `amcheck`、`pg_index`、partition manifest |

## 三个必须分开的结论

### “不可见”不等于“已经移除”

一条旧版本对当前事务不可见，不代表它对所有事务不可见。决定是否可回收的是全局清理
边界，而不是当前查询的快照。

### “已经回收”不等于“文件已经缩小”

普通 `VACUUM` 主要把空间登记为关系内部可复用。它在特定条件下可能截断关系尾部，但
不承诺把散落在文件中间的空洞交还操作系统。`VACUUM FULL` 会重写表并取得
`ACCESS EXCLUSIVE` 锁，不能作为日常扫尾。

### “dead tuple 很多”不等于“表已经异常膨胀”

`n_dead_tup` 是累计统计系统的估计；一次写入尖峰、健康的稳态 churn、被长事务阻断、
真正的 heap bloat，可能给出相似的瞬时数字。至少要联合：

```text
change rate
last vacuum / autovacuum
dead tuple estimate and physical sample
relation growth
free space
oldest xmin holders
workload reuse behavior
```

再决定“等下一轮、手工 VACUUM、解除保留者、在线重建，还是安排离线重写”。

## 本章实验：让旧快照亲自阻断回收

正式实验在已确认的 Pigsty `pg-test` 沙箱创建一次性数据库：

```text
database   pg36_maintenance
role       dbuser_pg36maint
PostgreSQL 18.4
data       synthetic only
risk       L2 bounded disposable fixture
```

夹具初始有 60,000 行。实验先开启一个 `REPEATABLE READ` 事务并确认它持有非空
`backend_xmin`，然后：

```text
UPDATE 40,000 rows
DELETE 10,000 rows
VACUUM while old snapshot remains
```

结果：

| 时点 | 当前行 | `pgstattuple` dead tuple | heap bytes | FSM 可用空间 |
|---|---:|---:|---:|---:|
| 初始 | 60,000 | 0 | 61,440,000 | 19,680,000 |
| churn 后 | 50,000 | 50,000 | 87,040,000 | 27,877,376 |
| 旧快照仍在，普通 VACUUM 后 | 50,000 | 50,000 | 87,040,000 | 17,480,000 |
| 精确释放旧快照并 `VACUUM FREEZE` 后 | 50,000 | 0 | 87,040,000 | 51,920,000 |

这个结果同时证明两件事：

1. 扫过并不等于能清；旧快照仍需要那些版本时，普通 `VACUUM` 必须保留它们；
2. 回收并不等于缩文件；最后 dead tuple 为零、FSM 可用约 51.9 MB，heap 文件仍是
   87.04 MB。

最后一次维护还得到：

```text
all-visible pages   10,625
all-frozen pages    10,625
relfrozenxid age    14 -> 2
```

注意：这不是在声称普通 `VACUUM` 永远不会截断文件。本夹具只观察到“文件未缩、空间
可复用”；生产结论必须保留普通 vacuum 有条件截断尾部的例外。

## 同一条证据链中的索引与分区

实验没有在 heap 回收后停止。

### 完整性与重建

```text
bt_index_check(... heapallindexed=true, checkunique=true)      pass
bt_index_parent_check(... rootdescend=true, ...)               pass
REINDEX INDEX CONCURRENTLY                                     pass
invalid index after                                            0
_ccnew / _ccold artifact after                                 0
```

被重建的二级索引从 3,227,648 bytes 降到 1,589,248 bytes；`relfilenode` 改变，
索引仍只有一个、`indisready/indisvalid/indislive` 全为真。这个数据只说明夹具中的
重建完成，不能外推生产窗口的耗时、锁等待或空间余量。

### 分区退役

10,000 行过期分区采用：

```text
logical manifest
  -> DETACH PARTITION CONCURRENTLY
      -> CSV export + SHA-256
          -> independent restore table
              -> row count / range / sum / digest equality
                  -> drop detached partition
```

导出文件为 547,894 bytes。只有在回灌后的 10,000 行逻辑摘要完全一致后，实验才删除
独立分区；父表保留 5,000 行当前数据。

公开结果见 [`maintenance-run.json`](/labs/ch28/maintenance-run.json)，安全边界见
[`lab-contract.md`](/labs/ch28/lab-contract.md)。

## 本章学习成果

完成本章后，你应该能：

1. 从 MVCC 快照解释 `UPDATE`、`DELETE` 为什么留下旧版本；
2. 区分 tuple visibility、deadness、removability 与 reusable space；
3. 解释 page pruning、HOT、regular vacuum、aggressive vacuum 的分工；
4. 用 FSM、VM、relation size 和 physical tuple evidence 分别回答不同问题；
5. 正确计算 PostgreSQL 18 的 autovacuum update/delete 与 insert 触发阈值；
6. 用表级 storage parameter 做定点治理，同时避免把关闭 autovacuum 当调优；
7. 从 worker、cost delay、memory、I/O 和 workload 联合判断维护竞争；
8. 读取 `pg_stat_progress_vacuum`，但不把块比例冒充 ETA；
9. 从 `backend_xmin`、复制槽 `xmin/catalog_xmin`、两阶段事务找出保留者；
10. 监控 `relfrozenxid/datfrozenxid` 和 `relminmxid`，避免只看数据库总年龄；
11. 在回卷紧急态按安装版本的官方流程解除保留者并让普通 `VACUUM` 完成；
12. 区分 stable-state bloat、transient churn、index bloat 和 statistics error；
13. 评估 `VACUUM FULL`、在线重写和并发索引重建的锁、空间、WAL 与失败残留；
14. 用 `DETACH ... CONCURRENTLY`、归档清单和回灌验证完成分区退役；
15. 用 `amcheck` 建立分层完整性检查，而不把它当页校验或恢复演练的替代品；
16. 把 Pigsty 历史指标、日志和 dashboard 与 PostgreSQL 原生视图交叉验证；
17. 输出日常、每周、每月和事件驱动的维护清单；
18. 在过载与疑似损坏时分别安全路由到第 34、35 章。

## 本章目录

### [28.1 死元组与可见性](01/)

- [28.1.1 UPDATE/DELETE 如何产生旧版本](01/#item-28-1-1)
- [28.1.2 vacuum、prune、HOT 与可见性图](01/#item-28-1-2)
- [28.1.3 回收可重用空间不等于归还文件系统](01/#item-28-1-3)

### [28.2 autovacuum 的触发与资源](02/)

- [28.2.1 阈值、比例、插入触发与表级覆盖](02/#item-28-2-1)
- [28.2.2 worker、cost delay、I/O 与业务竞争](02/#item-28-2-2)
- [28.2.3 进度、阻塞与“为什么没清掉”](02/#item-28-2-3)

### [28.3 冻结、XID 与保留者](03/)

- [28.3.1 XID 年龄、冻结与回卷保护](03/#item-28-3-1)
- [28.3.2 长事务、`backend_xmin` 与 idle in transaction](03/#item-28-3-2)
- [28.3.3 复制槽 `xmin` 与孤儿 `pg_prepared_xacts`](03/#item-28-3-3)
- [28.3.4 紧急态先解除保留并让 VACUUM 完成](03/#item-28-3-4)

### [28.4 膨胀与重建](04/)

- [28.4.1 表膨胀、索引膨胀与统计误判](04/#item-28-4-1)
- [28.4.2 `VACUUM FULL`、在线重建与额外空间](04/#item-28-4-2)
- [28.4.3 `REINDEX CONCURRENTLY` 的版本和失败处理](04/#item-28-4-3)

### [28.5 分区生命周期](05/)

- [28.5.1 新分区预建、约束和父表显式 ANALYZE](05/#item-28-5-1)
- [28.5.2 `DETACH`、归档、验证后删除](05/#item-28-5-2)
- [28.5.3 用分区退役替代大批量 `DELETE`](05/#item-28-5-3)
- [28.5.4 将 ch04/ch07/ch11/ch16/ch28 串成能力索引](05/#item-28-5-4)

### [28.6 `amcheck` 与例行完整性检查](06/)

- [28.6.1 `bt_index_check` 与更深检查的成本](06/#item-28-6-1)
- [28.6.2 `heapallindexed`、锁与业务窗口](06/#item-28-6-2)
- [28.6.3 `amcheck` 不替代数据页 checksum 和备份恢复](06/#item-28-6-3)

### [28.7 实战：建立维护节奏](07/)

- [28.7.1 制造膨胀、长事务与分区到期](07/#item-28-7-1)
- [28.7.2 从指标与原生视图判定维护优先级](07/#item-28-7-2)
- [28.7.3 执行清理、检查和分区退役并验证副作用](07/#item-28-7-3)
- [28.7.4 输出维护清单及 ch34/ch35 的安全路由](07/#item-28-7-4)

## 阅读路线

应用开发者：

```text
28.1 -> 28.2.1 -> 28.3.2 -> 28.5 -> 28.7
```

重点是事务生命周期、长事务边界、表级写入特征和分区保留策略。

平台工程师：

```text
28.1 -> 28.2 -> 28.3 -> 28.4 -> 28.6 -> 28.7
```

重点是触发、资源、回卷安全、重建窗口和完整性检查。

两条路线必须合流：应用定义事务与数据生命周期，平台维护全局清理边界和资源预算。
应用留下无限事务，平台无法“调快 VACUUM”；平台盲目重写，应用也无法获得可预测服务。

## 版本与证据权威

本章命令以 PostgreSQL 18 为基线，正式 run 使用 18.4；平台示例以 Pigsty 4.4 为
参考实现。维护与紧急恢复语义应按**实际安装 major/minor 的 PostgreSQL 官方文档**
执行，不把旧版本博客或平台二次说明覆盖到新版本。

特别是事务 ID 即将耗尽的处置，PostgreSQL 18 官方流程要求先处理 prepared xact、
长事务和旧复制槽，再运行普通 `VACUUM`；它明确不建议在该状态使用
`VACUUM FULL` 或 `VACUUM FREEZE`，一般也不需要 single-user mode。本章 28.3.4
按这个版本事实展开。

核心资料：

- [PostgreSQL 18：Routine Vacuuming](https://www.postgresql.org/docs/18/routine-vacuuming.html)
- [PostgreSQL 18：VACUUM](https://www.postgresql.org/docs/18/sql-vacuum.html)
- [PostgreSQL 18：Vacuuming Configuration](https://www.postgresql.org/docs/18/runtime-config-vacuum.html)
- [PostgreSQL 18：VACUUM Progress](https://www.postgresql.org/docs/18/progress-reporting.html#VACUUM-PROGRESS-REPORTING)
- [PostgreSQL 18：Visibility Map](https://www.postgresql.org/docs/18/storage-vm.html)
- [PostgreSQL 18：Heap-Only Tuples](https://www.postgresql.org/docs/18/storage-hot.html)
- [PostgreSQL 18：Table Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [PostgreSQL 18：amcheck](https://www.postgresql.org/docs/18/amcheck.html)
- [Pigsty：PostgreSQL Monitoring](https://pigsty.io/docs/pgsql/monitor/)
- [Pigsty：PGSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)
- [Pigsty：`pig pg` Maintenance Commands](https://pigsty.io/docs/pig/pg/)

## 实验文件

```text
static/labs/ch28/
├── requirements.json
├── maintenance-contract.json
├── negative-cases.json
├── topology.mmd
├── lab-contract.md
├── capture.py
├── remote_experiment.py
├── exercise.py
├── validate.py
├── review.py
├── task.sh
└── maintenance-run.json
```

执行：

```bash
static/labs/ch28/task.sh lint

export PG36_EVIDENCE_DIR=/private/path/to/new-empty-dir
static/labs/ch28/task.sh capture
static/labs/ch28/task.sh exercise
static/labs/ch28/task.sh verify
static/labs/ch28/task.sh review
```

`all` 会按同一顺序执行。`exercise` 会产生真实 I/O、WAL、锁和短暂维护负载，只能在
已确认的一次性开发/测试环境运行。

## 本章验收

只有当你能交付以下证据，才算掌握本章：

```text
trigger calculation
holder inventory
progress and blocker evidence
before/after physical + cumulative statistics
XID and MXID headroom
lock / space / WAL budget
maintenance command and rollback
index validity after rebuild
partition archive and restore manifest
exact cleanup or production change record
```

“我跑了 VACUUM，没有报错”不是验收。

---

[上一章：精益求精：参数调优与资源治理](/configuration-tuning/) · [返回下卷导读](/lower-volume/) · [下一章：移花接木：逻辑复制、迁移与异构同步](/logical-replication-migration/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
