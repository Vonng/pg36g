---
title: 第 36 章 事故复盘、控制固化与平台演进——举一反三
linkTitle: 36 事故复盘、控制固化与平台演进——举一反三
weight: 460
aliases:
- "/ch36/"
- "/volume-2/postmortem-platform-improvement/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch36
book_number: 36
book_part: part-6
book_status: draft
---

服务恢复解决的是“现在还能不能用”，事故复盘要解决的是“为什么系统允许这条失效链
成立，以及下一次什么会不同”。如果复盘止于一份文档，系统没有发生任何变化；如果
行动止于“代码已经合并”，控制也未必真的有效。

本章把全书最后一个闭环写成：

```text
restore user outcome
  -> stabilize correctness and headroom
  -> preserve what was known when
  -> explain trigger, amplification and failed defenses
  -> convert findings into owned controls
  -> verify effectiveness and expiry
  -> make the safer path a platform default
```

“无责”不是“无因”或“无责任”。它要求不把复杂系统失败压缩成人格评价，同时仍精确
记录谁以什么 role 对哪项控制、截止时间和验证证据负责。

## 学习完成标准

完成本章后，读者应能：

1. 分开用户影响恢复、数据正确性、运行余量与 incident closure；
2. 清点并回收临时降级、应急权限、路由旁路和被暂停的自动化；
3. 为通知、观察窗口、证据保留和正式结案定义可验证条件；
4. 用事件时间、采集时间和知识时间重建 append-only timeline；
5. 区分 trigger、放大机制、failed defense 与潜在失效条件；
6. 从技术、流程、组织和认知四个层面寻找 contributing factors；
7. 写出不归罪个人、又不回避具体动作与决策缺陷的复盘；
8. 区分当时可见事实、当时假设、后来证据与事后解释；
9. 判断某个正确结果来自受控机制，还是仅仅来自运气；
10. 评估日志、指标、trace、审计、时间同步和 retention 的证据质量；
11. 把行动项写成 owner role、期限、控制类型、验证、失效与重验合同；
12. 区分 prevent、detect、mitigate、recover 四类控制；
13. 拒绝“加强意识”“以后注意”和“部署即关闭”等不可验收行动；
14. 把教训回写到 SLI/SLO、runbook、恢复目标、安全假设和 ADR；
15. 用 Pigsty inventory、模板、监控规则、safeguard 与演练承载平台控制；
16. 将局部补丁升级为默认护栏，同时保留 exception、版本和退出路径；
17. 从多个事故识别重复控制主题，但不把教学实验冒充生产缺陷；
18. 产出 90 天路线，并用独立证据而不是 ticket 状态关闭控制。

## 三种关闭不能混为一谈

| 层次 | 关闭条件 | 不能替代它的信号 |
|---|---|---|
| incident | 用户影响、正确性、容量余量与运行路径稳定 | endpoint 偶尔返回 200 |
| postmortem | 影响、时间线、因果、决策、未知项经相关方评审 | 文档创建成功 |
| control action | 指定验证通过，关闭证据被独立接受，重验时间已登记 | PR merged / ticket done |

行动关闭后，控制还可能因版本、流量、拓扑、人员边界或依赖变化而失效。因此控制注册表
需要 `last_verified_at`、`evidence`、`valid_until` 或 `revalidation_days`，而不是
永久绿色的 checkbox。

## 从四类演练提取控制主题

第 32～35 章分别保留了四条恢复路线：

| 章节 | 场景 | 主要决策 | 不能外推 |
|---|---|---|---|
| ch32 | 误写与 PITR | 排除错误 history，合并审计后的合法增量 | sandbox timing 不是生产 RTO |
| ch33 | 主库失效 | 围栏、接纳新权威、对账 unknown、修复 lineage | 受控停进程不是硬件/网络分区 |
| ch34 | flow 与 retention pressure | 先分类，再限流或修复 owner | fixture 阈值不是生产容量线 |
| ch35 | 物理与派生损坏 | 从可信源恢复或重建 derived state | 单字节/元数据注入不是真实介质故障 |

它们反复提示 observation contract、生产门禁、业务验收、精确作用域、unknown outcome、
未知分类停止线和 lineage/authority 七个主题。这里的措辞必须严格：

```text
exercise exposed a control question
!=
production lacks this control
```

只有生产 inventory、流程、配置和演练证据完成评估后，某个主题才能被确认成实际缺口。

## 正式实验

本章的实验是完全离线的 postmortem compiler。它读取四份已冻结、去敏的公开摘要：

- [`ch32/pitr-run.json`](/labs/ch32/pitr-run.json)
- [`ch33/failover-run.json`](/labs/ch33/failover-run.json)
- [`ch34/overload-run.json`](/labs/ch34/overload-run.json)
- [`ch35/rescue-run.json`](/labs/ch35/rescue-run.json)

每个 observed fact 都绑定 source JSON Pointer、expected value、actual value 和
knowledge stage。编译器产出四份事故记录、七个跨事故控制主题、十二项 0～90 天参考
backlog 和覆盖 ch01～ch36 的能力评估合同。

正式 run `91c4464b-89f7-4145-9708-f07256d747ce`：

```text
input evidence files hash-bound     4
incident records                    4
cross-incident themes               7
proposed control actions           12
roadmap phases                      3
capability chapters covered        36
live mutants rejected              36 / 36
production gaps confirmed           0
database / SSH connections          0 / 0
production mutations                0
```

36 个 live mutant 包括篡改源事实、把 sandbox 影响冒充真实用户、删除 action owner、
期限、验证或失效条件、自动批准生产动作、漏掉路线阶段，以及仅因能力地图完整就自动
认证读者。公开结果见 [`closure-run.json`](/labs/ch36/closure-run.json)。

## 本章边界

本章没有：

- 分析任何真实生产事故、个人或客户数据；
- 证明读者所在组织存在七个缺口；
- 创建工单、发送通知、修改 Pigsty inventory 或执行 backlog；
- 把第 32～35 章一次实验计时提升成 SLO/RTO；
- 因为读者完成阅读而自动授予能力认证。

正式结论保持：

```text
production_ch36_gate = pending
roadmap_status        = reference-proposal-requires-local-approval
learner_assessment    = not-assessed
```

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第六篇：出山——按响应目标演练恢复与改进
- 前置：[第 31 章 事件分级、现场保护与应急决策](/incident-response/)、
  [第 32～35 章恢复演练](/pitr/)
- 兼容入口：`/ch36/`、`/volume-2/postmortem-platform-improvement/`

## 本章目录

### [36.1 服务恢复不等于事件结束](01/)

- [36.1.1 恢复用户影响、数据正确性与运行余量](01/#item-36-1-1)
- [36.1.2 清理临时降级、应急权限和旁路配置](01/#item-36-1-2)
- [36.1.3 通知、观察窗口与正式结案条件](01/#item-36-1-3)

### [36.2 从时间线建立因果链](02/)

- [36.2.1 触发条件、放大机制与失效防线](02/#item-36-2-1)
- [36.2.2 技术、流程、组织与认知因素](02/#item-36-2-2)
- [36.2.3 避免单一根因和个人归罪](02/#item-36-2-3)

### [36.3 证据质量与决策复盘](03/)

- [36.3.1 哪些事实当时可见，哪些后来才知道](03/#item-36-3-1)
- [36.3.2 哪些假设被验证，哪些动作靠运气](03/#item-36-3-2)
- [36.3.3 告警、日志和时间同步缺口](03/#item-36-3-3)

### [36.4 把行动项变成控制](04/)

- [36.4.1 所有者、截止时间、验证方法与失效条件](04/#item-36-4-1)
- [36.4.2 自动检查、发布门、容量线与恢复演练](04/#item-36-4-2)
- [36.4.3 不能验证的“加强意识”不是合格行动项](04/#item-36-4-3)

### [36.5 回写 SLO、SOP 与架构 ADR](05/)

- [36.5.1 更新观察契约、告警规则与 runbook](05/#item-36-5-1)
- [36.5.2 修正 RPO/RTO、容量和安全假设](05/#item-36-5-2)
- [36.5.3 将必要变更纳入服务目录与版本路线](05/#item-36-5-3)

### [36.6 将控制固化到平台](06/)

- [36.6.1 配置模板、验证脚本与策略即代码](06/#item-36-6-1)
- [36.6.2 备份、切换、容量和维护的周期演练](06/#item-36-6-2)
- [36.6.3 从单个补丁升级为默认护栏](06/#item-36-6-3)

### [36.7 实战：复盘四类事故并完成全书结业](07/)

- [36.7.1 汇总 ch32–ch35 的证据、决策与用户影响](07/#item-36-7-1)
- [36.7.2 找出跨事故重复出现的控制缺口](07/#item-36-7-2)
- [36.7.3 输出 90 天改进路线、平台 backlog 与复验计划](07/#item-36-7-3)
- [36.7.4 回看从 SQL 到生产的能力地图](07/#item-36-7-4)

## 权威参考

复盘与 SRE：

- [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [Google SRE Workbook: Postmortem Culture](https://sre.google/workbook/postmortem-culture/)
- [Google SRE Workbook: Monitoring](https://sre.google/workbook/monitoring/)
- [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

PostgreSQL：

- [Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)
- [Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html)

Pigsty：

- [Infrastructure as Code](https://pigsty.io/docs/concept/iac/)
- [Monitoring System](https://pigsty.io/docs/concept/monitor/)
- [PGSQL Playbooks and Safeguard](https://pigsty.io/docs/pgsql/playbook/)
- [Restore Operations](https://pigsty.io/docs/pgsql/backup/restore/)

---

[上一章：数据抢救与工程取证——起死回生](/data-rescue-forensics/) · [返回下卷导读](/lower-volume/) · [返回全书导读](/guide/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
