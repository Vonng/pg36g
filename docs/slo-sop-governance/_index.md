---
title: 第 24 章 纲举目张：SLO、SOP 与组织治理
linkTitle: 24 纲举目张：SLO、SOP 与组织治理
weight: 340
aliases:
- "/ch24/"
- "/volume-2/slo-sop-governance/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch24
book_number: 24
book_part: part-4
book_status: draft
---

数据库平台最危险的状态，不是“什么都没有”，而是看起来什么都有：

```text
三节点
有备份
有监控
有告警
有值班群
有操作文档
```

却没人能回答：

```text
用户究竟获得什么服务？
什么事件才算成功？
一个实例宕机是否已经影响用户？
数据错了一行，能否被 99.9% 的平均值原谅？
计划维护为什么可以从报表中消失？
告警响起后的第一个安全动作是什么？
谁能批准切换，谁能执行，谁负责停止？
“备份成功”以外，恢复过吗？
哪份证据证明这次操作的目标、输入与结果？
```

本章把这些问题组织成一条可执行的治理链：

```text
用户旅程
  -> 服务目录与责任人
      -> SLI / SLO / 控制目标
          -> 错误预算与变更政策
              -> 观察与告警契约
                  -> SOP / Runbook / Drill / Change Plan
                      -> 权限、停止线与回退
                          -> 证据、审计与保留
                              -> 自动验证与对抗性反例
```

治理不是在 PostgreSQL 外面增加一层审批表。它的任务是把“正常”“异常”
和“谁有权改变什么”变成可计算、可否证、可追责的服务合同。

## 本章目标

完成本章后，你应当能够：

1. 区分数据库实例、集群、入口、应用和用户服务；
2. 为服务、数据、平台与安全隐私分别指定 accountable owner；
3. 用义务而不是“金银铜”标签定义服务等级；
4. 画出依赖、失效语义、值班与升级路径；
5. 解释为什么 `postgres_up = 1` 不是业务可用性；
6. 把 SLI 写成 `good events / eligible events`；
7. 区分 SLI、SLO、SLA、错误预算和控制目标；
8. 为可用性、延迟、新鲜度选择靠近用户的测量点；
9. 把正确性和恢复就绪从可平均的错误预算中分离；
10. 计算事件预算、等价时间预算和 burn rate；
11. 设计滚动窗口、低流量策略与不可追溯篡改的排除项；
12. 用错误预算真实约束发布节奏，而不是装饰仪表盘；
13. 区分 SOP、故障 Runbook、恢复演练和单次 Change Plan；
14. 把变更拆成申请、评审、执行、验证、回退或前滚与关单；
15. 为 L2/L3 高风险动作设计独立批准、精确目标和停止线；
16. 解释双人控制、延迟确认与 break-glass 的不同作用；
17. 为每个 SLI 固定数据源、查询、维度与缺失语义；
18. 区分页型症状、诊断原因和容量工单；
19. 使用 multiwindow、multi-burn-rate 作为可调起点；
20. 让每个 page 绑定用户影响、所有者、Runbook 和首个安全动作；
21. 监控监控系统自身，而不把“没有数据”解释为健康；
22. 为配置、变更、访问、恢复、SLO 与事件建立证据目录；
23. 区分普通日志、审计记录、决策证据与合规结论；
24. 用哈希、时间、身份、最小化和保留政策建立证据链；
25. 自动检查治理不变量，并用反例证明检查真正会失败；
26. 对一个环境给出“合同通过、生产待决”的诚实结论。

## 本章不做什么

本章不会把组织设计冒充 PostgreSQL 参数调优，也不会：

- 承诺一个普适的 99.99%；
- 用书中的角色标识代替真实值班表；
- 把沙箱一次成功切换称为生产 RTO；
- 把备份任务退出码称为恢复证明；
- 把现成组件指标直接拼成业务 SLO；
- 发布真实告警、发送真实 page；
- 以“合规”为名收集密码、密钥或完整客户行；
- 让审批替代技术停止线；
- 让自动化替代业务和风险授权。

`pg36_shop` 在本章仍是 synthetic teaching service。数值是可计算的政策输入，
不是与真实业务 owner 谈判后的生产承诺。

## 前置与后续

本章收束第 19–23 章已经获得的事实：

- [第 19 章 部署基线](/deployment-baseline/)：四机 Pigsty v4.4.0 /
  PostgreSQL 18 沙箱，以及六项明确例外；
- [第 20 章 高可用](/high-availability/)：计划切换、write gap、
  timeline 和未知写结果；
- [第 21 章 备份体系与恢复演练](/backup-recovery/)：命名恢复点、WAL 覆盖、
  隔离恢复与应用校验；
- [第 22 章 服务接入](/connection-pooling-routing/)：入口、池化、
  排队、路由与 planned role change；
- [第 23 章 数据安全](/authentication-authorization-security/)：
  TLS、角色、RLS、轮换、审计缺口与 transaction-pool 状态。

这些章节证明了机制，但机制不会自动成为服务承诺。例如：

```text
ch20 observed write gap       != production RTO
ch21 one successful restore   != ongoing recoverability
ch22 pool capacity sample     != production concurrency limit
ch23 RLS mechanism passes     != organization has approved data policy
```

下一章 [第 25 章 监控体系与可观测诊断](/observability/) 将实现本章输出的
指标和规则。先定语义、后写查询，是两章之间最重要的边界。

## 一张图看完整合同

```text
service card
  service / data / platform / security owner
  user journeys / dependency / tier obligations
  escalation / known gaps
        |
        v
SLO policy
  eligible event / good event / measurement point
  target / rolling window / exclusion
  error-budget consequence
        |
        v
observation contract
  source / query / labels / missing semantics / fallback
        |
        +------------------------+
        |                        |
        v                        v
symptom & integrity alerts       component telemetry
page / ticket / runbook          PG / pool / host / control plane
        |                        |
        +------------+-----------+
                     v
SOP / runbook / drill / change plan
  authority / target / stop line / verify / rollback-or-roll-forward
                     |
                     v
evidence manifest
  source / collector / time / target / hash / decision / retention
```

任何断点都会制造假治理：

| 断点 | 表面现象 | 真正风险 |
|---|---|---|
| 无服务卡 | 大量组件指标 | 不知道为谁服务、谁决策 |
| 无 SLI 语义 | 有阈值 | 不知道分子、分母和缺失意味着什么 |
| 无预算政策 | 有 SLO 图 | 可靠性结果不影响发布决策 |
| 无动作合同 | 有 page | 值班只能临场猜测 |
| 无停止线 | 有 SOP | 文档只会推动动作，不能阻止事故 |
| 无验证 | 命令成功 | 状态是否正确仍未知 |
| 无证据边界 | 日志很多 | 不能证明目标、授权与结果，还可能泄密 |

## 五种容易混淆的对象

### 服务目录项

描述“谁向谁提供什么能力，以及依赖、等级和责任”。它不是机器清单。

### SLI

一个实际测量值。例如：

$$
\text{availability SLI}
=
\frac{\text{good eligible order attempts}}
{\text{all eligible order attempts}}
$$

### SLO

对某个窗口内 SLI 的目标。例如“滚动 28 天内至少 99.9%”。它不是法律赔偿
条款；后者通常属于 SLA。

### 控制目标

不适合用平均错误率淡化的要求。例如“没有未解释的账实不符”与“90 天内有
一次通过的隔离恢复”。一次数据串租不能因为本月另有一千万次正确读取而变得
可以接受。

### 错误预算政策

当可靠性好或差时，组织具体改变什么。没有后果的错误预算只是 KPI：

```text
healthy      -> 正常评审节奏
watch        -> 减少并行高风险变更
constrained  -> 暂停非必要高风险发布，例外需共同批准
exhausted    -> 冻结非紧急高风险变更，优先修复可靠性
```

## 本章采用的目标

本章服务卡定义五个目标：

| ID | 类型 | 目标 |
|---|---|---|
| `SLO-AVAILABILITY` | ratio SLO | 被接纳的下单尝试得到可核对的成功结果 |
| `SLO-LATENCY` | ratio SLO | 被接纳的下单尝试在 250 ms 内完成 |
| `SLO-FRESHNESS` | ratio SLO | 带已知 commit token 的读取在 5 s 内可见 |
| `CTRL-CORRECTNESS` | control | 无未解释的重复、串租、金额或状态错误 |
| `CTRL-RESTORE-READINESS` | control | 90 天内有通过的隔离恢复证据 |

它们有意不使用：

```text
PostgreSQL process is running
Patroni reports one leader
HAProxy backend is UP
replica replay timestamp looks recent
backup job exited zero
```

这些都是有价值的组件事实，但只能解释服务为什么好或坏，不能单独回答用户
是否获得了正确服务。

## 可计算的错误预算

可用性目标为 99.9%，滚动窗口为 28 天：

$$
\text{allowed bad ratio} = 1 - 0.999 = 0.001
$$

若窗口内有 10,000,000 个 eligible events：

$$
\text{event budget}
= 10{,}000{,}000 \times 0.001
= 10{,}000
$$

若为了直觉把比例换算成连续时间：

$$
28 \times 24 \times 60 \times 0.001
= 40.32\text{ minutes}
$$

40.32 分钟只是等价解释。request-based SLO 的实际预算仍是事件，不应把一
小时的低流量故障与一小时的流量高峰当成同一件事。

burn rate 定义为：

$$
\text{burn rate}
=
\frac{\text{observed bad-event ratio}}
{1-\text{SLO target}}
$$

对 99.9% 目标，14.4 倍 burn 对应 1.44% bad ratio。Google SRE Workbook
给出的 multiwindow 起点是：

| route | 长窗 | 短窗 | burn | 约消耗预算 |
|---|---:|---:|---:|---:|
| page | 1 h | 5 min | 14.4x | 1 h 内 2% |
| page | 6 h | 30 min | 6x | 6 h 内 5% |
| ticket | 3 d | 6 h | 1x | 3 d 内 10% |

这是起点，不是常数。实际规则必须按流量、后果和 notification cost 调整。
原始推导见 Google SRE Workbook 的
[Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)。

## 观察与告警的边界

Pigsty v4.4 提供：

```text
VictoriaMetrics       time-series ingestion / storage / query
VictoriaLogs          structured log storage / query
VMAlert               rule evaluation
Alertmanager          grouping / inhibition / routing / notification
Grafana               dashboards and investigation entry
```

PostgreSQL、PgBouncer、HAProxy、Patroni 和主机事实通过 `cls`、`ins`、`ip`
等身份维度关联。当前实现说明以 Pigsty
[Monitoring System](https://pigsty.io/docs/concept/monitor/) 与
[PGSQL Monitoring](https://pigsty.io/docs/pgsql/monitor/) 为准。

但平台不能凭空产生业务语义。第 25 章还需要实现：

```text
pg36_shop_request_outcomes_total
pg36_shop_request_duration_seconds
pg36_shop_commit_visibility_probes_total
pg36_shop_reconciliation_mismatches
pg36_shop_restore_evidence_age_seconds
```

这些名称是本书的应用合同，不是 Pigsty 当前内置指标。将来改名可以，改变
eligible/good/missing 语义则必须重新评审 SLO。

## 四类操作文档

| 文档 | 何时使用 | 核心区别 |
|---|---|---|
| SOP | 可重复的日常动作 | 已知输入、稳定步骤、例行验证 |
| Incident Runbook | 症状已经发生 | 先保安全、边诊断边决策 |
| Recovery Drill | 证明恢复路径 | 隔离、预设验收、保留计时与结果 |
| Change Plan | 一次具体变更 | 精确目标、窗口、版本、批准与回退 |

“切主 SOP”这个名称可能掩盖两种完全不同的动作：

```text
planned switchover
  current leader healthy
  authority and candidate known
  client gap can be measured

unplanned failover
  failure and write authority may be ambiguous
  fencing comes before promotion
  unknown outcomes must be reconciled
```

不能因为两者最终都出现“新主库”，就复用同一套前提和停止线。

## 高风险动作的基本不变量

本章把动作分成 L0–L3：

| 等级 | 典型动作 | 基本要求 |
|---|---|---|
| L0 | 只读观察、验证证据 | 精确目标，不改变远端状态 |
| L1 | 有界、可逆、低影响变更 | 预览、验证、回退 |
| L2 | 权限、模式、池或运行态变更 | 独立批准、停止线、证据 |
| L3 | 删除、恢复、拓扑和大影响动作 | 双人控制、延迟确认、强制门禁 |

L2/L3 使用不同的 requester、approver 与 executor。双人控制并不是两个人
盯着同一条未核对的命令按回车；合格的独立批准人必须检查：

- 目标是否精确；
- 影响半径是否可信；
- 前置事实是否新鲜；
- 动作是否与已批准 artifact hash 一致；
- stop condition 是否机器可判定；
- 回退/前滚是否真的可执行；
- 未知结果是否会被错误重试。

[NIST SP 800-53 Rev. 5.1](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
的变更访问限制包含 dual authorization。它是风险控制的参考，不意味着每个
组织必须机械照搬同一审批流。

## 正式实验

本章提供一套纯 L0 实验：

- [服务卡](/labs/ch24/service-card.json)
- [SLO 与错误预算政策](/labs/ch24/slo-policy.json)
- [观察契约](/labs/ch24/observation-contract.json)
- [告警候选](/labs/ch24/alert-candidates.json)
- [SOP 目录](/labs/ch24/sop-catalog.json)
- [变更政策](/labs/ch24/change-policy.json)
- [证据保留政策](/labs/ch24/evidence-retention.json)
- [治理 ADR](/labs/ch24/governance-adr.md)
- [依赖图](/labs/ch24/dependency-map.mmd)
- [实验合同](/labs/ch24/lab-contract.md)
- [正式运行摘要](/labs/ch24/governance-run.json)

正式运行：

```text
run id          34909737-527a-460c-927c-d9d71c93aa13
captured        2026-07-29T21:57:40.539Z
target          pg36-l2-vagrant/pg-test
mode            read-only
mutation        none
service owners  4 functions
objectives      3 ratio + 2 control
alerts          7 accepted + 1 actionless rejected
SOPs            4
evidence types  6
counterexamples 20 rejected
upstream runs   ch20–ch23, bound by run id and SHA-256
production      pending
```

重新执行第 19 章只读 gate 后，四台主机与四个 PostgreSQL member 仍通过
`accepted-with-exceptions`；六项沙箱例外没有被隐藏。

形式化验证故意尝试：

- 宣称 production SLO；
- 删除 platform owner；
- 把 process alive 当服务健康；
- 把目标改成 100%；
- 排除计划维护；
- 把缺失数据当健康；
- 让 exhausted budget 没有后果；
- 给指标加入未约束客户标识；
- 接受没有动作的 page；
- 让 cause/capacity 直接 page；
- 把 backup exit 0 当恢复证明；
- 让一人自批自执行；
- 让 break-glass 跳过目标与证据；
- 允许 evidence 保存 secret；
- 伪造上游 restore run id；
- 把一次沙箱切换称为生产证明。

二十个变体全部被拒绝。实验没有部署告警，也没有联系真实值班人。

## 本章目录

### [24.1 服务目录与责任模型](01/)

- [24.1.1 服务所有者、数据所有者与平台所有者](01/#item-24-1-1)
- [24.1.2 等级、规格、依赖、值班与升级路径](01/#item-24-1-2)
- [24.1.3 实例健康不等于业务服务健康](01/#item-24-1-3)

### [24.2 SLI、SLO 与错误预算](02/)

- [24.2.1 可用性、延迟、正确性与数据新鲜度](02/#item-24-2-1)
- [24.2.2 测量点、统计窗口与排除条件](02/#item-24-2-2)
- [24.2.3 错误预算如何约束变更速度](02/#item-24-2-3)

### [24.3 SOP、Runbook 与变更治理](03/)

- [24.3.1 日常操作、故障处置与恢复演练](03/#item-24-3-1)
- [24.3.2 申请、评审、执行、验证与回退](03/#item-24-3-2)
- [24.3.3 高风险动作的双人或延迟确认](03/#item-24-3-3)

### [24.4 观察与告警契约](04/)

- [24.4.1 每个 SLI 的数据源、查询、维度和缺失语义](04/#item-24-4-1)
- [24.4.2 告警必须绑定用户影响、首个安全动作和所有者](04/#item-24-4-2)
- [24.4.3 症状告警、原因告警与容量预测分开](04/#item-24-4-3)
- [24.4.4 产出供 ch25 实现的告警规则清单](04/#item-24-4-4)

### [24.5 证据、审计与合规](05/)

- [24.5.1 配置、变更、访问和恢复证据](05/#item-24-5-1)
- [24.5.2 保留、不可抵赖与隐私边界](05/#item-24-5-2)
- [24.5.3 用自动检查减少人工表格](05/#item-24-5-3)

### [24.6 实战：把 `pg36_shop` 纳入服务治理](06/)

- [24.6.1 发布服务卡、SLO、责任人与升级路径](06/#item-24-6-1)
- [24.6.2 为备份、切换、权限和发布建立 SOP](06/#item-24-6-2)
- [24.6.3 输出观察契约，并拒绝没有动作的告警候选](06/#item-24-6-3)

## 权威资料

- Google SRE Workbook：
  [Implementing SLOs](https://sre.google/workbook/implementing-slos/)、
  [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- Prometheus：
  [Alerting practices](https://prometheus.io/docs/practices/alerting/)、
  [Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- PostgreSQL 18：
  [Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)
- Pigsty v4：
  [Monitoring System](https://pigsty.io/docs/concept/monitor/)、
  [PGSQL Monitoring](https://pigsty.io/docs/pgsql/monitor/)
- NIST：
  [SP 800-53 Rev. 5.1](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)

这些资料提供方法和组件事实；`pg36_shop` 的服务语义、阈值和治理政策仍由
本章合同负责。

## 章末验收

不要用“文档已经发布”验收本章。应当能回答：

- [ ] 能否从一次用户动作追到 eligible/good 事件定义？
- [ ] 能否指出这个定义在哪个测量点实现？
- [ ] 没有数据时，系统是 unknown、failed 还是有独立 fallback？
- [ ] 正确性错误是否会被平均比例掩盖？
- [ ] 计划维护是否仍反映在用户体验中？
- [ ] 错误预算状态是否改变变更权限和速度？
- [ ] 每个 page 是否有 owner、runbook、第一安全动作和恢复验证？
- [ ] cause metric 是否只用于诊断，而不会重复 page？
- [ ] capacity 是否形成有期限的 owned ticket？
- [ ] 高风险动作能否被同一身份申请、批准和执行？
- [ ] break-glass 是否仍绑定目标、时限、证据和轮换？
- [ ] backup success 之外，是否有隔离恢复与应用验收？
- [ ] evidence 是否能证明 source、target、time、collector 和 hash？
- [ ] evidence 是否明确不保存 secret 与不必要的个人数据？
- [ ] 能否运行反例并看到 validator 真实拒绝？
- [ ] 是否清楚哪些结论仍然 `production pending`？

如果这些问题没有答案，再多告警、审批单和仪表盘也只是组织噪声。

---

[上一章：固若金汤：认证、授权与数据安全](/authentication-authorization-security/) · [返回下卷导读](/lower-volume/) · [下一章：望闻问切：监控体系与可观测诊断](/observability/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
