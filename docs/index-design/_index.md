---
title: 第 9 章 巧夺天工：索引设计与效果验证
linkTitle: '09 巧夺天工：索引设计与效果验证'
weight: 190
aliases:
- "/ch09/"
- "/volume-1/index-design/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch09
book_number: 9
book_part: part-2
book_status: draft
---

索引不是“给字段加速”的装饰，而是为一组操作符、谓词、排序与返回形状维护的额外数据结构。每增加一个索引，读取路径多一个候选，写入路径也多一份维护、WAL、缓存和生命周期成本。

因此索引设计从第 8 章的已证实 workload 开始：

```text
query family + representative parameters + SLO
  → predicate operators and expression semantics
  → join/order/group/limit and returned columns
  → data distribution, correlation and write pattern
  → access method + operator class + key order/predicate/include
  → before/after read evidence
  → size, HOT, WAL, write and maintenance evidence
  → build/failure/recovery plan
  → retain, merge or reject
```

“出现 Index Scan”不等于成功，“仍是 Seq Scan”也不等于失败。小表、低选择率、大范围、缓存与成本参数都可能让 Seq Scan 合理；一个被 planner 使用的索引也可能只优化冷门参数，却让所有写入变贵。

## 本章目标

完成本章后，读者应当能够：

- 把 access method、data type、operator class 与 query operator 对应起来；
- 解释 B-tree、Hash、GiST、SP-GiST、GIN、BRIN 与 Bloom 的边界；
- 从等值、范围、连接、排序、Top-N 与返回列推导 key order；
- 知道“最具选择性的列放最前”不是通用多列索引算法；
- 说明 PostgreSQL 18 B-tree skip scan 的能力及 14–17 的版本边界；
- 正确设计 expression index，并处理函数 volatility、collation 与语义一致性；
- 解释 partial index 的 predicate implication 与 generic parameter 陷阱；
- 使用 `INCLUDE`，同时理解 visibility map、heap fetch 与宽 payload 成本；
- 量化索引的空间、写放大、WAL、cache、vacuum 与复制代价；
- 解释 HOT 的两个条件，以及 indexed/update column 如何使 HOT 失效；
- 区分重复、重叠、未使用、无效与约束支撑索引；
- 设计数据、cache、参数、并发一致的 before/after 实验；
- 选择普通或 concurrent build，监控阶段并处理 INVALID 残留；
- 在 Pigsty 中关联 query、table/index、WAL、锁、I/O 与复制延迟；
- 为订单、库存、全文搜索与时间序列给出 retain/reject 决策；
- 把索引收益与代价证据追加到 `PREF-PLAN-005`。

## 实验边界

实验基线为 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04 L1；主体 SQL 保持 PostgreSQL 14–18 可用，PG18 skip scan 单独标注。实验只在 `shop_private` 建七张带 marker 的 `ch09_*` fixture：

```text
orders        200000 rows / placed=5% / customer 42 target=10
inventory     300000 rows / 30 warehouses / SKU 4242 target=30
search        100000 rows / full-text target=100
events        400000 rows / physically time-correlated / target=600
write twins   50000 + 50000 rows
unique probe  10000 rows / 5000 duplicate groups
```

`setup` 在 marker 完全匹配后重建，属于 R1。`reset` 删除专属对象，属于 R2，需要 action/target 双 token。实验不为 `shop` 业务表新增或删除任何索引。

候选索引使用 `CREATE INDEX CONCURRENTLY`，但这只是 L1 机制演练：生产上线还要独立评估长事务、两次扫描、CPU/I/O、WAL、磁盘峰值、复制延迟、唯一语义与失败恢复。

下载资产：

- [实验合同](/labs/ch09/lab-contract.md)
- [上下文 guard](/labs/ch09/context.sql)
- [机器计划上下文](/labs/ch09/plan-context.sql)
- [确定性 fixture](/labs/ch09/setup.sql)
- [订单查询](/labs/ch09/order-query.sql)
- [订单参数计划](/labs/ch09/order-parameter.sql)
- [库存查询](/labs/ch09/inventory-query.sql)
- [全文检索查询](/labs/ch09/search-query.sql)
- [事件范围查询](/labs/ch09/event-query.sql)
- [候选索引生命周期](/labs/ch09/create-candidates.sh)
- [候选 VACUUM](/labs/ch09/vacuum-candidates.sql)
- [无额外索引写对照](/labs/ch09/write-base.sql)
- [有 volatile 索引写对照](/labs/ch09/write-indexed.sql)
- [写统计快照](/labs/ch09/write-stats.sql)
- [写 fixture 恢复](/labs/ch09/restore-write.sql)
- [并发失败注入](/labs/ch09/concurrent-failure.sh)
- [索引 catalog 快照](/labs/ch09/catalog.sql)
- [索引决策账本](/labs/ch09/index-decisions.json)
- [语义分析器](/labs/ch09/analyze_indexes.py)
- [v0.4 规则提案](/labs/ch09/baseline-v0.4-proposal.json)
- [状态验收](/labs/ch09/verify.sql)
- [双 token reset](/labs/ch09/reset.sql)
- [任务入口](/labs/ch09/task.sh)

## 所属位置

- 卷别：[上卷：应用开发](/upper-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第二篇：应用——从 SQL 正确走向稳定交付
- 兼容入口：`/ch09/`、`/volume-1/index-design/`

## 本章目录

### [9.1 索引方法与操作符类](01/)

- [9.1.1 B-tree 与 Hash 的适用查询](01/#item-9-1-1)
- [9.1.2 GiST、SP-GiST 与空间、范围、近邻问题](01/#item-9-1-2)
- [9.1.3 GIN 与数组、JSONB、文本检索](01/#item-9-1-3)
- [9.1.4 BRIN 与物理相关的大表；Bloom 的扩展边界](01/#item-9-1-4)

### [9.2 从谓词、连接与排序推导索引](02/)

- [9.2.1 等值、范围与多列顺序](02/#item-9-2-1)
- [9.2.2 连接键、排序、分组与 Top-N](02/#item-9-2-2)
- [9.2.3 选择率、相关性与访问路径](02/#item-9-2-3)

### [9.3 表达式、部分与覆盖索引](03/)

- [9.3.1 表达式必须与查询语义一致](03/#item-9-3-1)
- [9.3.2 部分索引的谓词蕴含与参数陷阱](03/#item-9-3-2)
- [9.3.3 `INCLUDE`、index-only scan 与可见性图](03/#item-9-3-3)

### [9.4 索引也有写入和生命周期成本](04/)

- [9.4.1 写放大、缓存占用与 WAL](04/#item-9-4-1)
- [9.4.2 HOT 更新、页分裂与填充因子](04/#item-9-4-2)
- [9.4.3 重复、未使用与失效索引的判断](04/#item-9-4-3)

### [9.5 验证而不是“加完就快”](05/)

- [9.5.1 计划、缓冲区、延迟分布与写入代价](05/#item-9-5-1)
- [9.5.2 数据规模和缓存状态一致的 A/B 对照](05/#item-9-5-2)
- [9.5.3 线上创建、失败回收与监控窗口](05/#item-9-5-3)

### [9.6 实战：为订单、库存与搜索入口设计索引](06/)

- [9.6.1 从真实查询清单提出候选索引](06/#item-9-6-1)
- [9.6.2 在 Pigsty L1 保留、合并或拒绝并记录证据](06/#item-9-6-2)
- [9.6.3 将索引审查规则追加到规约](06/#item-9-6-3)

## 实测摘要

一次 PostgreSQL 18.4 全量验收得到：

```text
order:
  literal/custom → partial covering index-only / Heap Fetches=0
  generic status parameter → cannot use partial predicate
inventory:
  before → warehouse-first primary key skip scan
  after  → reverse covering index-only / Heap Fetches=0 / rows=30
search:
  generated tsvector GIN / rows=100
event:
  BRIN retained / B-tree comparison rejected and removed
  BRIN/B-tree size fraction=0.00273
write:
  unindexed volatile column HOT ratio=1.0
  indexed volatile column HOT ratio=0
  statement WAL bytes=11257432→11631392
concurrent:
  SQLSTATE 23505 / INVALID observed / exact drop / remaining=0
decisions:
  retain=4 / reject=4
final:
  worker=0 / rejected-or-failed index=0
  relation checksum=f8a7bfae59c6d16cd323abecfefe1014
```

时间、cost、buffers、WAL 精确值与节点组合不是 golden；它们受硬件、cache、checkpoint、版本和数据布局影响。稳定断言是 partial/generic 语义、结果行数、index-only heap fetch、BRIN 相对空间、HOT 失效方向、WAL 增长方向、INVALID 生命周期和最终 catalog。

## 章节验收

1. 每个候选先有 query/parameter/order/return shape 与 SLO；
2. 能从 operator class 证明某个 clause 可被索引，而非只看列名；
3. 多列顺序由 equality/range/order/workload 推导；
4. PG18 skip scan 不被写成 PG14–17 的通用前提；
5. partial index 的 query predicate 可在 planning time 蕴含 index predicate；
6. generic parameter 不能证明任意值满足 partial predicate；
7. covering index 同时检查 projection、VM/heap fetch 与 payload 宽度；
8. GIN/BRIN 的 lossy/recheck、write 与物理相关边界明确；
9. 索引评审包含 size、WAL、HOT、write latency 与 cache；
10. 不以 `idx_scan=0` 单独删除索引；
11. constraint、replica identity、rare critical query 与统计 epoch 已排除；
12. A/B 使用同一数据、统计、参数、cache、并发和重复方法；
13. concurrent build 的阶段、额外扫描、长事务与磁盘水位已评估；
14. build 失败后查询 `pg_index.indisvalid/indisready` 并精确回收；
15. Pigsty 面板结论能落回 query、catalog、plan 与 WAL/复制证据；
16. `task.sh all` 与双 token reset 均通过，业务 checksum 不变。

下一章 [ch10《顾此失彼：并发控制与隔离异常》](/concurrency-isolation/) 将验证即使单条查询和索引都正确，并发交错仍可能破坏业务不变量。

## 参考资料

- [PostgreSQL 18：Indexes](https://www.postgresql.org/docs/18/indexes.html)
- [PostgreSQL 18：Index Types](https://www.postgresql.org/docs/18/indexes-types.html)
- [PostgreSQL 18：Multicolumn Indexes](https://www.postgresql.org/docs/18/indexes-multicolumn.html)
- [PostgreSQL 18：Partial Indexes](https://www.postgresql.org/docs/18/indexes-partial.html)
- [PostgreSQL 18：Index-Only Scans](https://www.postgresql.org/docs/18/indexes-index-only-scans.html)
- [PostgreSQL 18：CREATE INDEX](https://www.postgresql.org/docs/18/sql-createindex.html)
- [PostgreSQL 18：Heap-Only Tuples](https://www.postgresql.org/docs/18/storage-hot.html)
- [Pigsty：PostgreSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)

---

[上一章：抽丝剥茧：慢 SQL 诊断方法论](/slow-query-diagnosis/) · [返回上卷导读](/upper-volume/) · [下一章：顾此失彼：并发控制与隔离异常](/concurrency-isolation/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
