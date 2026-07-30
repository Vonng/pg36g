---
title: 第 7 章 追本溯源：执行计划与统计信息
linkTitle: 07 追本溯源：执行计划与统计信息
weight: 170
aliases:
- "/ch07/"
- "/volume-1/query-plans-statistics/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch07
book_number: 7
book_part: part-2
book_status: draft
---

第 5 章已经说明：优化器比较的是基于统计与成本参数的候选路径，不是在预言未来耗时；第 6 章又把“看到 Seq Scan 或高 cost 不直接判错”写进 `PREF-PLAN-005`。本章开始为这条规则补运行证据。

读计划的核心不是认节点图标，而是沿一棵数据流树回答：

```text
关系语义
  → planner 估计每一步会输出多少行
  → 候选路径怎样消费这些行
  → cost model 选择总成本较低者
  → executor 实际产生多少行、循环多少次、访问多少 buffer/WAL
  → 偏差来自统计、参数、条件表达、资源还是等待
```

本章用 100000 行确定性 fixture 制造两种经典偏差：`region` 与 `order_status` 完全相关，但普通统计分别观察两列；`tenant_id=1` 有 90000 行，其余 tenant 各 10 行，使 custom 与 generic plan 面对完全不同的选择率。另一个四分区 fixture 对照规划时裁剪、执行初始化裁剪和包裹分区键导致的失效。

## 本章目标

完成本章后，读者应当能够：

- 从叶子到根读懂 scan、join、sort、aggregate、materialize 的数据流；
- 区分 startup cost、total cost、estimated rows、width 与实际时间；
- 解释 cost 是相对比较单位，父节点 cost 已包含子树；
- 正确使用 `EXPLAIN`、`ANALYZE`、`BUFFERS`、`WAL`、`SETTINGS` 与机器可读格式；
- 知道 `EXPLAIN ANALYZE` 会真实执行 SQL，写语句必须有受控事务和副作用边界；
- 区分 planning、executor、server/client/network 与排队时间；
- 从 `pg_stats` 理解 null fraction、n_distinct、MCV、histogram 与 correlation；
- 用 dependency/MCV 扩展统计修复跨列估算，而不把统计当约束；
- 识别陈旧统计、数据倾斜、采样误差和表达式不匹配；
- 区分 plan-time、initialization-time 与 execution-time partition pruning；
- 知道 partition parent 不会由 autovacuum 自动分析，何时要显式 `ANALYZE`；
- 对照 custom/generic plan，理解参数敏感查询；
- 把 plan change 当调查信号，而不是自动回归；
- 正确使用 `pg_stat_statements` 的归一化聚合视角；
- 评估 `auto_explain` 的阈值、采样、参数泄露与 per-node timing 成本；
- 从 Pigsty 时间窗关联 query、database/user/application、wait、plan 与资源；
- 产出 baseline v0.2 proposal，为 `PREF-PLAN-005` 增加 runtime evidence。

## 实验边界

实验基线为 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04 L1；SQL 保持 PostgreSQL 14–18 可用。fixture 只创建：

- `shop_private.ch07_plan_probe`（100000 行）；
- `shop_private.ch07_event_probe`（3650 行、四个季度分区）；
- `shop_private.ch07_region_status_stats`。

`setup` 会在 marker 完全匹配后重建这些专属对象，属于 R1；`reset` 删除它们，属于 R2，要求 action/target 双 token。`EXPLAIN ANALYZE` 即使查询只读也会真实执行并消耗资源，所以只在已确认 L1 运行。

下载资产：

- [实验合同](/labs/ch07/lab-contract.md)
- [上下文 guard](/labs/ch07/context.sql)
- [确定性 fixture](/labs/ch07/setup.sql)
- [扩展统计变更](/labs/ch07/apply-extended-statistics.sql)
- [分区父表 ANALYZE](/labs/ch07/analyze-partition-parent.sql)
- [相关组合计划](/labs/ch07/correlation-present.sql)
- [不可能组合计划](/labs/ch07/correlation-impossible.sql)
- [参数计划模板](/labs/ch07/parameter-plan.sql)
- [常量裁剪](/labs/ch07/partition-constant.sql)
- [失效裁剪](/labs/ch07/partition-wrapped.sql)
- [generic parameter 裁剪](/labs/ch07/partition-generic.sql)
- [机器计划分析器](/labs/ch07/analyze_plans.py)
- [v0.2 规则提案](/labs/ch07/baseline-v0.2-proposal.json)
- [状态验收](/labs/ch07/verify.sql)
- [双令牌 reset](/labs/ch07/reset.sql)
- [任务入口](/labs/ch07/task.sh)

## 所属位置

- 卷别：[上卷：应用开发](/upper-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第二篇：应用——从 SQL 正确走向稳定交付
- 兼容入口：`/ch07/`、`/volume-1/query-plans-statistics/`

## 本章目录

### [7.1 优化器如何选择路径](01/)

- [7.1.1 扫描、连接、排序、聚合与物化节点](01/#item-7-1-1)
- [7.1.2 成本、选择率、行数与路径竞争](01/#item-7-1-2)
- [7.1.3 计划树的阅读顺序与数据流](01/#item-7-1-3)

### [7.2 正确使用 EXPLAIN](02/)

- [7.2.1 `EXPLAIN`、`ANALYZE`、`BUFFERS`、`WAL`](02/#item-7-2-1)
- [7.2.2 规划时间、执行时间与客户端时间](02/#item-7-2-2)
- [7.2.3 对写语句使用 `ANALYZE` 的事务保护](02/#item-7-2-3)

### [7.3 统计信息与估算偏差](03/)

- [7.3.1 直方图、高频值、空值率与相关性](03/#item-7-3-1)
- [7.3.2 扩展统计解决跨列相关](03/#item-7-3-2)
- [7.3.3 数据倾斜、陈旧统计与采样误差](03/#item-7-3-3)

### [7.4 分区裁剪的两种时机](04/)

- [7.4.1 规划时裁剪与常量条件](04/#item-7-4-1)
- [7.4.2 执行时裁剪、参数化节点与通用计划](04/#item-7-4-2)
- [7.4.3 分区父表统计需要显式 `ANALYZE`](04/#item-7-4-3)
- [7.4.4 产出裁剪生效与失效的计划对照](04/#item-7-4-4)

### [7.5 参数、缓存计划与计划漂移](05/)

- [7.5.1 自定义计划与通用计划](05/#item-7-5-1)
- [7.5.2 预备语句、数据倾斜与参数敏感](05/#item-7-5-2)
- [7.5.3 计划变化是症状，不自动等于回归](05/#item-7-5-3)

### [7.6 建立计划证据基线](06/)

- [7.6.1 `pg_stat_statements` 的归一化视角](06/#item-7-6-1)
- [7.6.2 `auto_explain` 的阈值、采样与日志成本](06/#item-7-6-2)
- [7.6.3 从 Pigsty 时间窗保存 SQL、参数、统计、计划与环境上下文](06/#item-7-6-3)

### [7.7 实战：解释订单查询的计划变化](07/)

- [7.7.1 用固定数据种子制造估算偏差](07/#item-7-7-1)
- [7.7.2 修复统计与条件表达后重新比较](07/#item-7-7-2)
- [7.7.3 把一条有证据的计划规则追加到规约](07/#item-7-7-3)

## 实测摘要

一次 PostgreSQL 18.4 运行得到：

```text
correlated_estimate≈6300 → 25000 / actual=25000
impossible_estimate≈6300 → 1 / actual=0
custom_hot=Seq Scan / estimate=90000 / actual=90000
custom_cold=Index Scan / estimate=10 / actual=10
generic_estimate=100 / hot_actual=90000 / cold_actual=10
partition_counts=constant:1, wrapped:4, generic:1
partition_parent_stats=0→4
```

`ANALYZE` 使用统计抽样，所以修复前的约 6300 每次可能略变；node type、cost、buffers 和时间也不是 golden。稳定断言是偏差方向、修复幅度、参数敏感性、裁剪集合与前后业务 checksum。

## 章节验收

1. 能从叶子到根解释计划树，正确使用 `loops × rows`；
2. 不把 cost 当毫秒，不把 estimated rows 当扫描行数；
3. 采集计划时同时保存 SQL、参数、版本、统计、settings 和 buffer/WAL；
4. 对写计划知道怎样 rollback，并明确 sequence/外部副作用例外；
5. 能读 `pg_stats`，知道 MCV/histogram 是 sample summary；
6. 能说明单列统计为什么把相关条件近似独立相乘；
7. 能选择 dependencies、ndistinct、MCV 的适用问题；
8. 能证明 `ANALYZE` 后 estimate 改善，而不是只说“统计更新了”；
9. 能区分三种 partition pruning 时机；
10. 能从 `Subplans Removed`、loops 与 never executed 识别执行期裁剪；
11. 能说明为何 partition parent 需显式 ANALYZE；
12. 能对照 custom/generic plan 并识别参数倾斜；
13. plan 变化时先检查结果、SLO、估算、数据、统计、settings 和 wait；
14. 不把 `pg_stat_statements.queryid` 当跨大版本永久 ID；
15. 不在生产无评估开启 `auto_explain.log_analyze/timing`；
16. `task.sh all` 和双令牌 reset 均通过，ch04-v1 checksum 不变。

下一章 [ch08《抽丝剥茧：慢 SQL 诊断方法论》](/slow-query-diagnosis/) 将把单条计划
放回真实 workload、等待与时间序列中。

## 参考资料

- [PostgreSQL 18：Using EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html)
- [PostgreSQL 18：Statistics Used by the Planner](https://www.postgresql.org/docs/18/planner-stats.html)
- [PostgreSQL 18：Table Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [PostgreSQL 18：PREPARE](https://www.postgresql.org/docs/18/sql-prepare.html)
- [PostgreSQL 18：pg_stat_statements](https://www.postgresql.org/docs/18/pgstatstatements.html)
- [PostgreSQL 18：auto_explain](https://www.postgresql.org/docs/18/auto-explain.html)

---

[上一章：立木取信：开发规约与交付基线](/development-standards/) · [返回上卷导读](/upper-volume/) · [下一章：抽丝剥茧：慢 SQL 诊断方法论](/slow-query-diagnosis/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
