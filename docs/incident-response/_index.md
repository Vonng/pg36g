---
title: 第 31 章 事件分级、现场保护与应急决策——枕戈待旦
linkTitle: 31 事件分级、现场保护与应急决策——枕戈待旦
weight: 410
aliases:
- "/ch31/"
- "/volume-2/incident-response/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch31
book_number: 31
book_part: part-6
book_status: draft
---

前十二章已经建立部署、HA、备份、安全、可观测、容量、调优、维护、迁移与升级能力。
系统真正出事时，这些能力不会自动拼成一次正确响应：告警只呈现某个观察面的症状，
自动化可能继续改变拓扑，人在压力下又容易把第一个解释当成根因。

本章是第 32～35 章的共同控制平面。它不提前穷举所有故障，而是先回答四个问题：

```text
现在影响了谁，数据与恢复能力是否仍安全？
哪些状态仍在变化，哪些自动化需要精确暂停？
已有证据把问题路由到哪类恢复目标？
下一步动作由谁执行，何时停止，怎样证明结果？
```

事故早期最稀缺的通常不是命令，而是**可信状态与可逆选择**。好的响应不以“最快猜到
根因”为目标，而以更快降低用户影响、数据风险和不确定性，同时保留恢复路径为目标。

## 学习完成标准

完成本章后，读者应能：

1. 从用户影响、数据风险、范围、变化速度和可恢复性分级事件；
2. 把“恢复数据、恢复拓扑、释放压力、保护完整性”写成明确响应目标；
3. 区分严重度与技术判型，不让首发告警直接授权重启、提升或删除；
4. 有选择地控制 Patroni、调度器、路由与保留任务，而不是笼统“暂停一切”；
5. 采集带 UTC、拓扑、版本、system identifier、timeline、LSN 与来源散列的最小证据；
6. 按 PITR、HA、过载和完整性四条路线进入第 32～35 章；
7. 用“事实—假设—动作—预期—停止线—回退—结果”记录每次决策；
8. 在单人和团队两种模式下完成前十五分钟响应与可读交接；
9. 识别必须引入业务、存储、安全、法务或厂商的升级条件；
10. 组织一次不触碰生产的盲抽桌面演练，并区分工具通过与人员胜任。

## 一张图看懂事故控制面

```text
detect symptom
  -> declare incident and start UTC timeline
      -> quantify impact / data risk / scope / trend / recoverability
          -> preserve writer identity / WAL / backup / evidence
              -> collect independent layers
                  -> choose PITR / HA / OVERLOAD / INTEGRITY
                      -> authorize one bounded action
                          -> verify actual result
                              -> communicate and hand off
```

若新证据推翻当前路线，应回到 triage；若动作越过了写入、timeline 或不可逆边界，应更新
回退定义。严重度可以升降，技术路线也可以改变，但每次改变都必须留下事实和时间。

## 本章目录

### [31.1 事件分级与响应目标](01/)

- [31.1.1 用户影响、数据风险、范围与持续时间](01/#item-31-1-1)
- [31.1.2 恢复数据、恢复拓扑、释放流量压力、抢救完整性](01/#item-31-1-2)
- [31.1.3 严重度决定节奏，不替代技术判型](01/#item-31-1-3)

### [31.2 第一原则：保护现场与可恢复性](02/)

- [31.2.1 暂停自动化、危险变更与证据覆盖](02/#item-31-2-1)
- [31.2.2 记录时间、拓扑、版本、告警与最近变更](02/#item-31-2-2)
- [31.2.3 先克隆、隔离或只读，再做破坏性尝试](02/#item-31-2-3)

### [31.3 从症状路由而不是猜根因](03/)

- [31.3.1 误删误改与恢复目标 → ch32《PITR 与误操作恢复》](03/#item-31-3-1)
- [31.3.2 主节点、复制或 DCS 异常 → ch33《故障切换与集群重建》](03/#item-31-3-2)
- [31.3.3 连接、延迟、CPU、内存、I/O 或磁盘表象 → ch34《过载保护与资源故障判型》](03/#item-31-3-3)
- [31.3.4 checksum、索引、排序或逻辑不一致 → ch35《数据抢救与工程取证》](03/#item-31-3-4)

### [31.4 决策、沟通与变更纪律](04/)

- [31.4.1 事实、假设、动作、预期与停止条件](04/#item-31-4-1)
- [31.4.2 单一指挥、记录员、执行者与业务接口](04/#item-31-4-2)
- [31.4.3 高风险动作的复核、审批与回退](04/#item-31-4-3)

### [31.5 单人值守与团队响应](05/)

- [31.5.1 单人时先稳定、记录，再逐级升级](05/#item-31-5-1)
- [31.5.2 团队时避免多人同时改同一系统](05/#item-31-5-2)
- [31.5.3 何时必须请求业务、存储、安全或厂商协助](05/#item-31-5-3)

### [31.6 实战：盲抽症状的桌面演练](06/)

- [31.6.1 随机症状、误导性首发告警与缺失信息](06/#item-31-6-1)
- [31.6.2 分别按单人和团队模式完成前十五分钟](06/#item-31-6-2)
- [31.6.3 在 Pigsty L3 输出时间线、决策日志、证据包与路由选择](06/#item-31-6-3)

## 写作与验收提示

本章提供八个盲抽场景，每条后续技术路线各两个。正式参考 run 在 Pigsty `FULL/L3`
监控环境中对 `pg-test` 做 `L0-read-only` 采集，再离线完成一份 solo 与一份 team
响应：

```text
PostgreSQL                         18.4
Patroni topology                   1 primary + 2 replicas
timeline                           11
pgBackRest status / backups        0 / 6
drawn routes                       INTEGRITY + PITR
online mutation                    none
real incident injected             false
dangerous actions executed         0
```

验证器拒绝了 31 个声明反例和 18 个现场证据变异，并绑定 12 个实验源文件。公开摘要见
[`incident-run.json`](/labs/ch31/incident-run.json)，完整边界见
[`lab-contract.md`](/labs/ch31/lab-contract.md)。

这次通过只证明只读采集、盲包、响应合同和校验器可执行；参考响应由程序生成，**不代表
任何真人通过了能力考核**，更没有实施 failover、恢复备份或处理真实事故。
`production_ch31_gate` 保持 `pending`。

---

[上一章：推陈出新：版本升级与回滚策略](/version-upgrade/) · [返回下卷导读](/lower-volume/) · [下一章：PITR 与误操作恢复——妙手回春](/pitr/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
