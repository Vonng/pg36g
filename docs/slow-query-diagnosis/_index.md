---
title: 第 8 章 抽丝剥茧：慢 SQL 诊断方法论
linkTitle: '08 抽丝剥茧：慢 SQL 诊断方法论'
weight: 180
aliases:
- "/ch08/"
- "/volume-1/slow-query-diagnosis/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch08
book_number: 8
book_part: part-2
book_status: draft
---

“数据库慢”不是根因，甚至还不是一个足够好的问题。它可能表示某个请求在连接池排队、某条 SQL 被事务锁住、一个参数命中了错误的通用计划、结果集已经算完却写不进慢客户端，也可能只是用户把一次偶发抖动概括成了整体退化。

本章把第 5 章的事务与锁、第 7 章的计划与统计放回真实请求链路，建立一条可复核的诊断闭环：

```text
定义症状与时间窗
  → 界定服务、实例、数据库、查询族与参数
  → 观察 activity、wait 与 blocking edge
  → 关联查询统计、日志、计划、主机资源和变更事件
  → 按证据排列可证伪假设
  → 只改变一个解释变量
  → 比较效果、正确性与副作用
  → 修复、回退、复位并沉淀证据
```

顺序很重要。先跑 `EXPLAIN` 会漏掉锁与客户端背压；先建索引会把相关性当因果；只看面板截图则容易丢失指标定义、时间范围与原始身份。正确做法是从用户可见 SLI 向内收敛，再从平台视图回到 PostgreSQL 原生证据。

## 本章目标

完成本章后，读者应当能够：

- 用时间窗、样本数、p50/p95/p99、吞吐、并发和错误率定义“慢”；
- 区分单次慢、参数簇慢、持续退化、实例退化与全链路退化；
- 把端到端时间拆成排队、应用、数据库执行、传输和客户端消费；
- 正确联合解释 `pg_stat_activity.state`、`wait_event_type`、`wait_event`；
- 用 `pg_blocking_pids()` 证明阻塞边，不把等待者误当根因；
- 从 `pg_stat_statements` 按总预算、调用数、均值、最大值和资源量排序；
- 知道累计查询统计没有原生延迟分位数，且不能跨边界滥用 `queryid`；
- 建立带会话、查询、时间和变更身份的日志最小基线；
- 关联 SQL 指标、主机资源、锁、日志、部署和配置变更；
- 把“计划、锁、I/O、CPU、内存、客户端、网络、连接池”写成可证伪假设；
- 设计单变量、可回退、记录冷热缓存与参数分布的实验；
- 在 Pigsty 中定位范围，并用 SQL、日志和机器可读计划复核；
- 独立区分估算/计划、锁等待与客户端慢消费三种相似的“请求不返回”；
- 产出证据包、假设树、修复对照、负对照与复位结果。

## 实验边界

实验基线为 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04 L1；SQL 与诊断原则保持 PostgreSQL 14–18 可用。实验复用：

- ch07 的 90000/10 tenant skew，制造 generic/custom estimate 对照；
- ch05 的 rollback-only 行锁编排，制造一条可证明的 blocker edge；
- `generate_series` 派生结果与受控慢 reader，制造 `Client/ClientWrite`。

本章不创建持久对象。锁实验最终回滚，客户端实验只生成结果流，estimate 实验只读 ch07 fixture。若 ch07 fixture 缺失，`task.sh setup/all` 会通过 marker guard 受控重建专属对象，属于 L1/R1；不会自动清理业务对象、全局重置 `pg_stat_statements`、修改日志/连接池参数或取消非本章会话。

每个并发 worker 都有唯一 `application_name`。取消动作必须同时匹配 PID、`backend_start`、database 与 application identity；最终验收要求 `active_lab_workers=0`，并重新计算 ch04-v1 业务 checksum。

下载资产：

- [实验合同](/labs/ch08/lab-contract.md)
- [诊断记录模板](/labs/ch08/hypothesis-template.md)
- [estimate case](/labs/ch08/estimate-case.sh)
- [lock case](/labs/ch08/lock-case.sh)
- [client case](/labs/ch08/client-case.sh)
- [ClientWrite 编排](/labs/ch08/client-write-lab.sh)
- [慢 reader](/labs/ch08/slow-reader.py)
- [中性信号构建器](/labs/ch08/make_signals.py)
- [无答案诊断器](/labs/ch08/diagnose.py)
- [盲测入口](/labs/ch08/mystery.sh)
- [稳定断言](/labs/ch08/review.py)
- [v0.3 规则提案](/labs/ch08/baseline-v0.3-proposal.json)
- [状态验收](/labs/ch08/verify.sql)
- [任务入口](/labs/ch08/task.sh)

## 所属位置

- 卷别：[上卷：应用开发](/upper-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第二篇：应用——从 SQL 正确走向稳定交付
- 兼容入口：`/ch08/`、`/volume-1/slow-query-diagnosis/`

## 本章目录

### [8.1 先定义“慢”](01/)

- [8.1.1 延迟分位数、吞吐、并发与错误率](01/#item-8-1-1)
- [8.1.2 单次慢、持续慢与整体退化](01/#item-8-1-2)
- [8.1.3 应用时间、排队时间与数据库时间](01/#item-8-1-3)

### [8.2 从会话到语句定位范围](02/)

- [8.2.1 活跃、等待、阻塞与空闲事务](02/#item-8-2-1)
- [8.2.2 按调用、总时长、均值和尾延迟排序](02/#item-8-2-2)
- [8.2.3 查询指纹、参数与时间窗口](02/#item-8-2-3)

### [8.3 关联日志、指标与计划](03/)

- [8.3.1 日志最小基线与慢语句记录](03/#item-8-3-1)
- [8.3.2 SQL 指标、主机资源与部署事件](03/#item-8-3-2)
- [8.3.3 用同一时间轴排除巧合](03/#item-8-3-3)

### [8.4 建立而不是猜测假设](04/)

- [8.4.1 计划与估算问题](04/#item-8-4-1)
- [8.4.2 锁、I/O、CPU、内存与临时文件](04/#item-8-4-2)
- [8.4.3 客户端取数、网络与连接池排队](04/#item-8-4-3)

### [8.5 设计受控实验](05/)

- [8.5.1 每次只改变一个解释变量](05/#item-8-5-1)
- [8.5.2 冷热缓存、参数与数据规模控制](05/#item-8-5-2)
- [8.5.3 反证、回退与副作用观察](05/#item-8-5-3)

### [8.6 从可观测面板回到原生证据](06/)

- [8.6.1 用指标语义定位时间、实例与查询](06/#item-8-6-1)
- [8.6.2 用 SQL、日志和计划复核面板判断](06/#item-8-6-2)
- [8.6.3 不把截图、颜色或当前点击路径当作知识](06/#item-8-6-3)

### [8.7 实战：三种“慢”只修真正瓶颈](07/)

- [8.7.1 估算错误、锁等待与客户端慢消费](07/#item-8-7-1)
- [8.7.2 随机隐藏一种根因，先独立诊断再揭晓](07/#item-8-7-2)
- [8.7.3 输出证据包、假设树、修复前后对照与复位结果](07/#item-8-7-3)

## 实测摘要

一次 PostgreSQL 18.4 全量验收得到：

```text
estimate:
  generic estimate=100 / actual=90000 / error=900x
  custom  estimate=90000 / actual=90000 / error=1x
lock:
  state=active / wait=Lock/transactionid / blockers=1
client:
  state=active / wait=Client/ClientWrite / blockers=0
mystery:
  diagnosis=client-slow-consumer / reveal matched=true
  wrong guess rejected=true / answer mode=0600
final:
  same seed reproducible=true / remaining workers=0
  relation checksum=f8a7bfae59c6d16cd323abecfefe1014
```

节点类型、cost、buffers、PID 和时间不是 golden。稳定断言是证据关系：generic estimate 严重偏离且 custom 对照改善；Lock wait 必须存在 blocker edge；ClientWrite 必须没有数据库 blocker；错误盲测答案必须失败；所有会话与业务状态最终恢复。

## 章节验收

1. 事件描述包含 UTC 时间窗、样本数、分位数、吞吐、并发、错误率和影响范围；
2. 不平均不同窗口的 p99，不用单次最大值冒充分位数；
3. 能解释端到端慢为什么可能完全发生在 PostgreSQL 之外；
4. 联合读取 state 与 wait，不把普通 idle/ClientRead 当慢查询；
5. 取消会话前验证 PID + backend_start + database + application；
6. 只用 `pg_blocking_pids()`/锁证据确认 blocker，不按最长 SQL 猜；
7. `pg_stat_statements` 排序至少覆盖总预算、均值、调用数和资源；
8. 知道累计统计的 reset/采样边界，不为一次调查全局 reset；
9. 日志含时间、PID/session、用户、数据库、application 与必要 query identity；
10. 参数日志有脱敏、长度、成本与保留策略；
11. 假设写明预测、反证、最小实验与回退条件；
12. 对比实验控制 cache、参数、数据量、并发与重复次数；
13. 面板发现必须能落回 SQL、日志、计划或 exporter 指标语义；
14. 三类 case 均能在不读取 answer artifact 时正确分类；
15. 错误 diagnosis 的 reveal 返回失败；
16. `task.sh all` 通过，answer mode 为 `0600`，worker 为 0，业务 checksum 不变。

下一章 [ch09《巧夺天工：索引设计与效果验证》](/index-design/) 将在诊断已证明访问路径是主要瓶颈后，再讨论该不该建、建什么、怎样验证和怎样安全发布索引。

## 参考资料

- [PostgreSQL 18：Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)
- [PostgreSQL 18：Cumulative Statistics System](https://www.postgresql.org/docs/18/monitoring-stats.html)
- [PostgreSQL 18：pg_stat_statements](https://www.postgresql.org/docs/18/pgstatstatements.html)
- [PostgreSQL 18：Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html)
- [PostgreSQL 18：Using EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html)
- [Pigsty：PostgreSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)

---

[上一章：追本溯源：执行计划与统计信息](/query-plans-statistics/) · [返回上卷导读](/upper-volume/) · [下一章：巧夺天工：索引设计与效果验证](/index-design/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
