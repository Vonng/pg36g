---
title: 第 25 章 望闻问切：监控体系与可观测诊断
linkTitle: 25 望闻问切：监控体系与可观测诊断
weight: 350
aliases:
- "/ch25/"
- "/volume-2/observability/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch25
book_number: 25
book_part: part-5
book_status: draft
---

“有监控”很容易，“知道发生了什么”很难。

一个看起来成熟的平台可能同时拥有：

```text
26 个 PostgreSQL 仪表盘
3,000 多种指标名
数百条记录规则
几十条告警规则
集中日志
追踪后端
值班通知
```

事故发生时却仍然只能说：

```text
CPU 高了
连接多了
复制慢了
面板红了
```

这些句子描述了现象，没有回答五个决定性问题：

1. 用户旅程是否真的失败、变慢、读旧或产生错误结果？
2. 这是首发症状、伴随现象，还是已经被证据支持的机制？
3. 观察数据是零、尚未刷新、被重置、被采样，还是根本缺失？
4. 哪个 owner 应采取什么**首个安全动作**？
5. 什么证据能够证明恢复，而不是仅仅“面板变绿”？

第 24 章先定义了服务、SLI、SLO、控制目标、缺失语义和告警治理。本章做下一步：

```text
observation contract
  -> 指标、日志、事件和追踪
      -> PostgreSQL 原生统计与 SQL 基线
          -> Pigsty 采集、存储、规则、面板和通知
              -> 可行动告警
                  -> 有界诊断包
                      -> 合成规则与离线路由演练
                          -> 覆盖表、盲区与生产门禁
```

这条链的重点不是“多收集一些数据”，而是让每个结论都能说明：

```text
question       想回答什么
source         哪个系统产生事实
semantics      值、窗口、标签、reset 和缺失是什么意思
cost           采集、查询和保留会付出什么代价
action         谁可以做什么
verification   怎样证明结论与恢复
boundary       什么仍然不知道
```

## 本章目标

完成本章后，你应当能够：

1. 从用户、入口、数据库和主机四层组织观察问题；
2. 区分症状信号、原因信号、控制信号与监控系统自身信号；
3. 说明指标、日志、事件和追踪各自适合回答什么；
4. 为 label cardinality、采样、保留和查询成本建立预算；
5. 把“没有数据”区分为无流量、采集故障、查询错误、延迟与真实零值；
6. 正确读取 `pg_stat_activity`、`pg_locks` 与 wait event；
7. 使用 `pg_stat_database`、`pg_stat_io`、`pg_stat_wal`、
   `pg_stat_checkpointer` 和 `pg_stat_archiver`；
8. 解释累计计数、瞬时状态、估算值和进度视图的不同时间语义；
9. 区分 WAL distance、时间 lag 与 commit-correlated freshness；
10. 观察 autovacuum、冻结年龄、dead tuple、对象增长和维护进度；
11. 正确解释 `pg_stat_statements` 的聚合键、reset、deallocation 与权限；
12. 解释为什么 normalized query text 仍不能随意进入证据；
13. 为慢语句、锁等待、临时文件和错误日志设置有界政策；
14. 评估 `auto_explain` 的 `ANALYZE`、timing、采样和参数泄露成本；
15. 把第 24 章 SLO 合同变成 multiwindow、multi-burn-rate 规则；
16. 区分 page、ticket、diagnostic 与 proposed test route；
17. 为 alert 的 `for`、分组、抑制、恢复和缺失语义写测试；
18. 防止 fast burn、slow burn 与预算工单形成重复风暴；
19. 防止 metamonitoring 抑制独立用户症状或正确性告警；
20. 理解 Pigsty v4 的 VictoriaMetrics、VictoriaLogs、VictoriaTraces、
    VMAlert、Alertmanager、Grafana、pg_exporter 与 Vector；
21. 用 `cls`、`ins`、`ip`、database 与 queryid 在不同粒度间下钻；
22. 从仪表盘回到 PostgreSQL SQL、日志和主机事实复核；
23. 自动保存有界、私密、可复验的诊断包；
24. 区分首发症状、相关现象、候选机制与根因；
25. 限制诊断查询的 timeout、并发、结果量和权限；
26. 用隔离时间序列验证 pending、firing、recovery 与 missing；
27. 用空 receiver 离线验证路由，不触碰真实 pager；
28. 输出覆盖矩阵，诚实标出尚未实现的应用 SLI；
29. 对当前沙箱给出“机制通过、生产待决”的可审计结论。

## 本章不做什么

本章不是一个“复制几十条 PromQL 就上线”的规则包，也不会：

- 把当前沙箱阈值包装成所有生产环境的通用答案；
- 修改在线 VMAlert、Alertmanager、Grafana 或 PostgreSQL；
- 向在线 Alertmanager 提交合成告警；
- 接入 webhook、邮件、短信、Slack 或真实 pager；
- 运行 `EXPLAIN ANALYZE`、压测、统计 reset 或数据库故障注入；
- 导出 query text、bind value、日志正文、client address 或凭据；
- 用 `pg_up=1` 证明订单服务可用；
- 用 `pg_lag=0` 证明 read-your-writes；
- 用 `failed_count>0` 直接证明归档仍在失败；
- 用“当前无告警”证明通知链可达；
- 用一次仪表盘相关性宣布 root cause；
- 声称 `pg36_shop` 已经具有真实应用埋点。

实验使用 `pg36_shop` 这一 synthetic teaching service。应用层五种信号仍是刻意
保留的缺口：

```text
request outcome counter
request duration histogram
commit-correlated freshness probe
domain reconciliation gauge
restore-evidence age gauge
```

缺口不是失败的写作，而是本章必须保留的事实。如果没有应用事件，平台不能从
数据库组件指标“推算”出一个看似完整的用户 SLO。

## 从监控到可观测诊断

### 监控回答已知问题

监控通常从一个已知条件出发：

```text
if bad_ratio_1h > threshold
and bad_ratio_5m > threshold
for 2m
then page
```

它适合稳定、可计算、可自动执行的问题：

- SLO 是否快速燃烧；
- exporter 是否持续不可达；
- 规则是否持续报错；
- 恢复证据是否超过政策期限；
- 容量预测是否进入评审窗口。

### 可观测诊断解释未知状态

诊断从“不知道为什么”出发，需要沿不同证据层缩小假设：

```text
user latency burn
  -> entry queue or rejection?
      -> pool saturation or connection churn?
          -> PostgreSQL active wait or lock?
              -> queryid cost or plan drift?
                  -> storage, WAL, checkpoint, vacuum or host constraint?
```

可观测性不是一个产品名，也不是“拥有 logs + metrics + traces”自动获得的属性。
它要求系统输出足够的、语义明确的证据，让操作者能区分多个竞争解释。

### 诊断不等于根因

本章采用四层语言：

| 层次 | 可以说什么 | 例子 |
|---|---|---|
| 首发症状 | 最早被可靠观察到的服务偏离 | availability fast burn 先触发 |
| 伴随现象 | 与症状同窗出现 | pool queue、lock wait 同时升高 |
| 候选机制 | 现象与某机制一致 | 长事务可能阻止 vacuum 推进 |
| 根因证据 | 机制被复现/独立证实，反例被排除，修复验证闭环 | 释放特定锁后等待消失且合成路径恢复 |

“两条线一起升高”最多是相关性。要升级为根因，至少需要：

```text
mechanism
independent corroboration or reproduction
falsification attempts
repair verification
```

## 四层问题，而不是四套孤岛面板

本章把信号按问题分为四层：

| 层 | 主要问题 | 首选事实 |
|---|---|---|
| 用户 | 旅程是否成功、及时、正确、足够新鲜 | eligible events、合成探针、domain reconciliation |
| 入口 | 请求在哪排队、被路由、重试或拒绝 | 应用 edge、HAProxy、PgBouncer |
| 数据库 | PG 状态能否解释症状 | activity、locks、I/O、WAL、maintenance、queryid |
| 主机 | 资源或基础设施是否构成约束 | CPU、memory、disk、network、clock |

从下往上推断很危险：

```text
CPU 90%
  therefore users are slow          # 不成立

one replica is down
  therefore service is unavailable  # 不成立

pg_up == 1
  therefore orders are correct       # 不成立
```

从上往下诊断更稳健：

```text
user symptom is real
  -> locate affected operation and path
  -> correlate entry and database evidence
  -> test competing mechanisms
  -> choose the least harmful action
  -> verify user and control signals
```

正确性与恢复就绪又是特殊控制：

```text
one unexplained cross-tenant row
  cannot be averaged away

old or missing restore evidence
  cannot be replaced by backup job success
```

## 四种信号，各有边界

| 信号 | 擅长 | 不擅长 | 必须声明 |
|---|---|---|---|
| metric | 趋势、比率、聚合、规则 | 高维上下文、单请求故事 | type、unit、label、reset、missing |
| log | 离散事件、错误上下文、状态迁移 | 完整总体比率、无界扫描 | schema、采样、脱敏、保留 |
| event | 发布、切换、配置和所有权时间线 | 单独证明因果 | actor、target、result、clock |
| trace | 单次跨组件路径 | 未采样总体、长期预算 | sample、baggage、PII、correlation |

四者不是竞争关系：

```text
metric detects
event bounds the change window
trace follows one affected request
log explains a discrete failure
SQL verifies PostgreSQL state
```

同样，也不应强迫每个问题都使用四种信号。一个能够由累计计数精确回答的问题，
不需要先扫描全部日志；一个需要参数上下文的问题，也不应把 error text 做成
metric label。

## 时间语义比数值更重要

观察数据至少有五种时间性质：

| 类型 | 示例 | 典型陷阱 |
|---|---|---|
| 当前状态 | `pg_stat_activity.state` | 一次采样漏掉短暂事件 |
| 累计计数 | `pg_stat_database.xact_commit` | 把总数当速率、忽略 reset |
| 滚动窗口 | `rate(counter[5m])` | 窗口过短、采样不足 |
| 估算值 | `n_dead_tup` | 当成精确 bloat |
| 当前进度 | `pg_stat_progress_vacuum` | 没有行不等于从未运行 |

还要处理采集链延迟：

```text
database state time
  -> exporter scrape time
      -> storage ingestion time
          -> rule evaluation time
              -> route grouping delay
                  -> receiver delivery time
```

如果数据源有意延迟 30 秒，而规则在“当前时刻”查询，最新样本可能尚未可见。
VMAlert 支持 evaluation delay；正确值取决于实际采集和存储延迟，不能机械照抄。

## 本章的规则分层

实验生成 18 条记录规则和 13 条告警规则。它们分成三类：

### 第 24 章已经接受的七条

| 告警 | 路由 | 目的 |
|---|---|---|
| `PG36ShopAvailabilityFastBurn` | page | 1h + 5m，14.4x |
| `PG36ShopAvailabilitySlowBurn` | page | 6h + 30m，6x |
| `PG36ShopAvailabilityBudgetTicket` | ticket | 3d + 6h，1x |
| `PG36ShopFreshnessFastBurn` | page | commit-correlated freshness |
| `PG36ShopCorrectnessMismatch` | page | 不允许平均稀释的正确性 |
| `PG36ShopCapacityHorizon` | ticket | 经评审预测才进入工作队列 |
| `PG36MonitoringPathBroken` | page | 观察或通知路径不可证明工作 |

### 仍待治理接受的六条

```text
latency burn
restore evidence stale
active archive risk
long transaction horizon
freeze-age horizon
expected traffic but SLI missing
```

它们有完整规则和测试，但统一标记：

```yaml
route: test
severity: candidate
governance_status: proposed-not-accepted
```

“代码写好了”不等于“组织接受了 page/ticket 政策”。这个显式不一致检查很重要：
第 24 章定义了 latency SLO，却没有接受 latency alert candidate。本章没有暗中
补齐生产政策，而是把它暴露为待决项。

### 诊断记录

复制距离、长事务、freeze age、dead tuples、exporter 状态、VMAlert rule error
和 notification failure 首先是诊断或控制输入。它们不会因为“容易写阈值”就
自动变成 page。

## 当前沙箱的真实快照

正式实验公共摘要：
[`observability-run.json`](/labs/ch25/observability-run.json)。

采集时间为 `2026-07-29T22:48:21Z`。快照只代表该时刻：

| 项目 | 观察值 |
|---|---:|
| Pigsty | v4.4.0 |
| PostgreSQL | 18.4 |
| pg_exporter | v1.4.0 |
| VictoriaMetrics | v1.148.0 |
| VictoriaLogs | v1.52.0 |
| VictoriaTraces | v0.9.4 |
| Alertmanager | 0.33.1 |
| VictoriaMetrics series | 44,842 |
| live VMAlert groups | 17 |
| live alert rules | 50 |
| live recording rules | 698 |
| live rule errors | 0 |
| current VMAlert alerts | 0 |
| `pg_up` / `pg_exporter_up` instances | 4 / 4 |
| `pg36_shop_*` application SLI series | 0 |

目标身份通过三层交叉确认：

```text
host            pg-test-1
Patroni scope   pg-test
PostgreSQL      cluster_name=pg-test
role            primary
replication     pg-test-2 + pg-test-3, async streaming
observed WAL gap 0 + 0 bytes
```

`0 bytes` 是当时的发送—回放距离，不是 read-your-writes 证明。

`pg_stat_statements` 快照：

```text
extension version      1.12
schema                 monitor
rows                   194
calls                  122,303
query text exported    false
stats reset            retained
```

归档快照有一个关键反例：

```text
failed_count           21
last failure           18:57:58Z
last successful archive 22:27:54Z
```

如果规则只是：

```promql
pg_archiver_failed_count > 0
```

它会在系统已经恢复后永久报警，直到统计被重置。候选规则因此同时检查：

```text
15m 内出现新失败
AND 最近成功归档已经停滞
```

再回到 pgBackRest 与恢复证据复核。累计 counter、当前故障和恢复就绪是三个
不同结论。

## 实验为什么分成在线与隔离两部分

### 在线只读基线

在线部分只做：

- HTTP health/API/metrics 读取；
- VictoriaMetrics 即时查询；
- 通过元节点进入真实 `pg-test-1`；
- 带 `statement_timeout=5s`、`lock_timeout=500ms` 的只读 SQL；
- 聚合 activity、locks、I/O、WAL、checkpointer、archiver、
  replication 和 `pg_stat_statements`；
- 记录版本、reset、freshness 与缺口。

不会 reset、reload、写表、运行计划、制造负载或读取 query text。

### 隔离规则与路由

规则文件上传到沙箱元节点的：

```text
/tmp/pg36-ch25.XXXXXXXX
```

随后：

1. `vmalert -dryRun` 检查规则语法；
2. `vmalert-tool` 启动 loopback-only VictoriaMetrics；
3. 注入合成时间序列；
4. 验证 normal、pending、firing、recovery 和 missing；
5. `amtool check-config` 检查 Alertmanager 配置；
6. 用八组标签离线解析到空 receiver；
7. 用五个用例验证抑制边界；
8. 清理临时目录并确认目录不存在。

它不会接触在线 VMAlert 或在线 Alertmanager。

## 本章目录

### [25.1 从问题选择可观测信号](01/)

- [25.1.1 用户体验、服务入口、数据库与主机四层](01/#item-25-1-1)
- [25.1.2 指标、日志、事件和追踪各回答什么](01/#item-25-1-2)
- [25.1.3 标签基数、采样、保留与缺失数据](01/#item-25-1-3)

### [25.2 PostgreSQL 核心运行信号](02/)

- [25.2.1 会话、事务、等待与锁](02/#item-25-2-1)
- [25.2.2 缓冲、I/O、WAL、检查点与复制](02/#item-25-2-2)
- [25.2.3 vacuum、冻结、膨胀与对象增长](02/#item-25-2-3)

### [25.3 SQL 可观测基线](03/)

- [25.3.1 `pg_stat_statements` 的统计口径与重置](03/#item-25-3-1)
- [25.3.2 慢语句、锁等待、临时文件与错误日志](03/#item-25-3-2)
- [25.3.3 `auto_explain` 的采样、嵌套语句与开销](03/#item-25-3-3)
- [25.3.4 日志不得泄漏密码、令牌和敏感参数](03/#item-25-3-4)

### [25.4 把观察契约变成告警](04/)

- [25.4.1 SLO 燃烧率与用户影响](04/#item-25-4-1)
- [25.4.2 阈值、持续时间、去抖、抑制与分组](04/#item-25-4-2)
- [25.4.3 每条告警绑定所有者、证据和首个安全动作](04/#item-25-4-3)
- [25.4.4 用演练验证告警，而不是等生产事故](04/#item-25-4-4)

### [25.5 Pigsty 可观测体系](05/)

- [25.5.1 采集、存储、规则、面板与通知链](05/#item-25-5-1)
- [25.5.2 以指标语义定位集群、实例、数据库和查询](05/#item-25-5-2)
- [25.5.3 面板结论回到 SQL、日志与主机事实复核](05/#item-25-5-3)

### [25.6 从告警到诊断包](06/)

- [25.6.1 自动保存时间窗、拓扑、变更与关键查询](06/#item-25-6-1)
- [25.6.2 区分首发症状、伴随现象与根因证据](06/#item-25-6-2)
- [25.6.3 证据采集本身的负载和权限边界](06/#item-25-6-3)

### [25.7 实战：实现并演练观察契约](07/)

- [25.7.1 为延迟、错误、复制、备份和资源建立规则](07/#item-25-7-1)
- [25.7.2 注入可控症状，验证触发、路由、抑制和恢复](07/#item-25-7-2)
- [25.7.3 输出告警覆盖表、盲区与 ch31 的诊断入口](07/#item-25-7-3)

## 官方资料

本章技术语义优先回到原始文档：

- [PostgreSQL 18 Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)
- [PostgreSQL 18 Cumulative Statistics](https://www.postgresql.org/docs/18/monitoring-stats.html)
- [PostgreSQL 18 `pg_stat_statements`](https://www.postgresql.org/docs/18/pgstatstatements.html)
- [PostgreSQL 18 `auto_explain`](https://www.postgresql.org/docs/18/auto-explain.html)
- [PostgreSQL 18 Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html)
- [PostgreSQL 18 Routine Vacuuming](https://www.postgresql.org/docs/18/routine-vacuuming.html)
- [Pigsty PostgreSQL Monitoring](https://pigsty.io/docs/pgsql/monitor/)
- [Pigsty PostgreSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)
- [Pigsty pg_exporter](https://pigsty.io/docs/pg_exporter/)
- [VictoriaMetrics VMAlert](https://docs.victoriametrics.com/victoriametrics/vmalert/)
- [VictoriaMetrics vmalert-tool](https://docs.victoriametrics.com/victoriametrics/vmalert-tool/)
- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus Unit Testing Rules](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)

下一章 [第 26 章 容量规划与压测基线](/capacity-benchmarking/) 会在这些观察
语义之上建立需求模型、容量水位和可比较基线；[第 28 章 VACUUM、冻结与膨胀治理](/vacuum-freeze-bloat/)
再深入维护信号。第 31 章把本章的诊断包作为故障排查入口，处理慢查询、锁、
连接、复制与磁盘等具体事件。

---

[上一章：纲举目张：SLO、SOP 与组织治理](/slo-sop-governance/) · [返回下卷导读](/lower-volume/) · [下一章：胸有成竹：容量规划与压测基线](/capacity-benchmarking/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
