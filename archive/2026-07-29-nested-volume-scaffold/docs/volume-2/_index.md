---
title: 下卷：运维管理
linkTitle: 下卷：运维管理
weight: 20
aliases:
- "/ops/"
- "/dba/"
type: docs
breadcrumbs: true
comments: false
book_kind: volume
book_number: 2
---

> 从生产服务规划到日常运营、事故恢复与改进

## 第四篇：规划——建设可交付的 PostgreSQL 服务

### [19 开天辟地：环境规划与部署基线](deployment-baseline/)

从工作负载、服务目标和责任边界出发，规划并验收 L2 生产仿真环境，而不是从一份默认配置开始。

- [19.1 先写服务需求](deployment-baseline/01/) `平台`
- [19.2 计算、内存、存储与网络](deployment-baseline/02/) `平台`
- [19.3 操作系统与主机基线](deployment-baseline/03/) `平台`
- [19.4 版本与数据库初始化契约](deployment-baseline/04/) `PG`
- [19.5 拓扑、命名与故障域](deployment-baseline/05/) `平台`
- [19.6 用声明式清单交付两个服务单元](deployment-baseline/06/) `Pigsty`
- [19.7 实战：L2 部署验收](deployment-baseline/07/) `平台`

### [20 狡兔三窟：高可用拓扑与容灾目标](high-availability/)

把复制、选主、故障域和业务 RPO/RTO 连接起来，通过一次可重复的切换演练证明高可用。本章同时作为全书架构型样章。

- [20.1 从失败模型设计高可用](high-availability/01/) `平台`
- [20.2 物理流复制](high-availability/02/) `PG`
- [20.3 同步策略与提交语义](high-availability/03/) `PG`
- [20.4 选主、DCS 与防脑裂](high-availability/04/) `平台`
- [20.5 切换、故障转移与重加入](high-availability/05/) `平台`
- [20.6 交付并观察 HA 集群](high-availability/06/) `Pigsty`
- [20.7 实战：一次有证据的计划切换](high-availability/07/) `平台`

### [21 未雨绸缪：备份体系与恢复演练](backup-recovery/)

从恢复目标反推备份、WAL 归档、保留和异地策略，并用隔离恢复证明备份可用。

- [21.1 从恢复场景设计备份](backup-recovery/01/) `平台`
- [21.2 物理备份与 WAL 连续性](backup-recovery/02/) `PG`
- [21.3 备份仓库与保留策略](backup-recovery/03/) `平台`
- [21.4 恢复流程与验证](backup-recovery/04/) `PG`
- [21.5 用 pgBackRest 交付备份策略](backup-recovery/05/) `Pigsty`
- [21.6 实战：完成一次隔离恢复演练](backup-recovery/06/) `平台`

### [22 四通八达：服务接入、连接池与路由](connection-pooling-routing/)

让客户端连接到“具有明确语义的服务”，而不是某台机器；掌握连接预算、池化模式、读写路由与失效行为。

- [22.1 服务端点的语义](connection-pooling-routing/01/) `平台`
- [22.2 连接的服务端成本](connection-pooling-routing/02/) `PG`
- [22.3 PgBouncer 池化模式](connection-pooling-routing/03/) `平台`
- [22.4 路由与故障切换](connection-pooling-routing/04/) `平台`
- [22.5 连接预算与过载边界](connection-pooling-routing/05/) `平台`
- [22.6 Pigsty 服务接入层](connection-pooling-routing/06/) `Pigsty`
- [22.7 实战：写入、只读与管理三类接入](connection-pooling-routing/07/) `平台`

### [23 固若金汤：认证、授权与数据安全](authentication-authorization-security/)

从威胁模型出发建立身份、最小权限、传输保护、行级安全与审计；把连接池会话语义纳入安全设计。

- [23.1 威胁模型与信任边界](authentication-authorization-security/01/) `平台`
- [23.2 认证与连接准入](authentication-authorization-security/02/) `PG`
- [23.3 角色与最小权限](authentication-authorization-security/03/) `PG`
- [23.4 行级安全与连接池上下文](authentication-authorization-security/04/) `PG`
- [23.5 密钥、审计与敏感信息](authentication-authorization-security/05/) `平台`
- [23.6 Pigsty 安全基线](authentication-authorization-security/06/) `Pigsty`
- [23.7 实战：隔离两个租户](authentication-authorization-security/07/) `平台`

### [24 纲举目张：SLO、SOP 与组织治理](slo-sop-governance/)

在建设告警之前定义“什么算服务正常、谁负责、证据在哪里、发生变化如何处置”，产出 ch25 的观察与告警契约。

- [24.1 服务目录与责任模型](slo-sop-governance/01/) `平台`
- [24.2 SLI、SLO 与错误预算](slo-sop-governance/02/) `平台`
- [24.3 SOP、Runbook 与变更治理](slo-sop-governance/03/) `平台`
- [24.4 观察与告警契约](slo-sop-governance/04/) `平台`
- [24.5 证据、审计与合规](slo-sop-governance/05/) `平台`
- [24.6 实战：把 `pg36_shop` 纳入服务治理](slo-sop-governance/06/) `Pigsty`

## 第五篇：运营——用证据驱动日常维护与演进

### [25 望闻问切：监控体系与可观测诊断](observability/)

实现 ch24 的观察契约，把指标、日志、SQL 统计和告警连接为可行动的诊断系统，而不是堆叠面板。

- [25.1 从问题选择可观测信号](observability/01/) `平台`
- [25.2 PostgreSQL 核心运行信号](observability/02/) `PG`
- [25.3 SQL 可观测基线](observability/03/) `PG`
- [25.4 把观察契约变成告警](observability/04/) `平台`
- [25.5 Pigsty 可观测体系](observability/05/) `Pigsty`
- [25.6 从告警到诊断包](observability/06/) `平台`
- [25.7 实战：实现并演练观察契约](observability/07/) `平台`

### [26 胸有成竹：容量规划与压测基线](capacity-benchmarking/)

用可复现工作负载测量资源需求、噪声与余量，形成容量模型；不把一次 pgbench 数字包装成普适性能。

- [26.1 从需求建立容量模型](capacity-benchmarking/01/) `平台`
- [26.2 设计代表性工作负载](capacity-benchmarking/02/) `PG`
- [26.3 建立可信实验](capacity-benchmarking/03/) `平台`
- [26.4 找到饱和点与瓶颈](capacity-benchmarking/04/) `平台`
- [26.5 从测量推导容量与成本](capacity-benchmarking/05/) `平台`
- [26.6 实战：`pg36_shop` 容量基线](capacity-benchmarking/06/) `Pigsty`

### [27 精益求精：参数调优与资源治理](configuration-tuning/)

以已证实的瓶颈为起点，理解参数的资源机制、作用域和变更风险；拒绝无上下文的“万能参数模板”。

- [27.1 调优是一套实验方法](configuration-tuning/01/) `平台`
- [27.2 内存预算](configuration-tuning/02/) `PG`
- [27.3 WAL、检查点与写入平滑](configuration-tuning/03/) `PG`
- [27.4 规划器、并行与连接参数](configuration-tuning/04/) `PG`
- [27.5 参数作用域与变更方式](configuration-tuning/05/) `平台`
- [27.6 模板参数与集群变更](configuration-tuning/06/) `Pigsty`
- [27.7 实战：只调一个已证实的瓶颈](configuration-tuning/07/) `平台`

### [28 除旧布新：VACUUM、冻结与膨胀治理](vacuum-freeze-bloat/)

把 MVCC 留下的空间债、事务年龄和索引完整性变成可预测的维护工作，并完成分区生命周期触点。

- [28.1 死元组与可见性](vacuum-freeze-bloat/01/) `PG`
- [28.2 autovacuum 的触发与资源](vacuum-freeze-bloat/02/) `PG`
- [28.3 冻结、XID 与保留者](vacuum-freeze-bloat/03/) `PG`
- [28.4 膨胀与重建](vacuum-freeze-bloat/04/) `PG`
- [28.5 分区生命周期](vacuum-freeze-bloat/05/) `PG`
- [28.6 `amcheck` 与例行完整性检查](vacuum-freeze-bloat/06/) `PG`
- [28.7 实战：建立维护节奏](vacuum-freeze-bloat/07/) `Pigsty`

### [29 移花接木：逻辑复制、迁移与异构同步](logical-replication-migration/)

理解逻辑复制、CDC 和数据搬迁的状态机，用校验与可回退切换完成迁移，而不是把“数据能流动”误当成迁移成功。

- [29.1 逻辑复制原语](logical-replication-migration/01/) `PG`
- [29.2 CDC 与复制槽治理](logical-replication-migration/02/) `PG`
- [29.3 批量装载与数据校验](logical-replication-migration/03/) `PG`
- [29.4 在线迁移状态机](logical-replication-migration/04/) `平台`
- [29.5 异构同步的语义损失](logical-replication-migration/05/) `平台`
- [29.6 多集群迁移环境](logical-replication-migration/06/) `Pigsty`
- [29.7 实战：迁移 `pg36_shop`](logical-replication-migration/07/) `平台`

### [30 推陈出新：版本升级与回滚策略](version-upgrade/)

把升级视为应用、数据库、扩展、排序规则和平台共同参与的迁移项目，通过彩排决定前滚或回退。

- [30.1 先识别变化类型](version-upgrade/01/) `平台`
- [30.2 三类大版本升级路径](version-upgrade/02/) `PG`
- [30.3 扩展与依赖升级](version-upgrade/03/) `PG`
- [30.4 locale、collation 与索引风险](version-upgrade/04/) `PG`
- [30.5 升级前检查与业务验证](version-upgrade/05/) `PG`
- [30.6 用隔离环境完成升级彩排](version-upgrade/06/) `Pigsty`
- [30.7 实战：前滚、回退与发布决策](version-upgrade/07/) `平台`

## 第六篇：出山——按响应目标演练恢复与改进

### [31 事件分级、现场保护与应急决策——枕戈待旦](incident-response/)

建立所有事故共用的指挥、保护、取证、变更与升级框架；兼顾单人值守和团队协同，并学会怀疑第一个症状。

- [31.1 事件分级与响应目标](incident-response/01/) `平台`
- [31.2 第一原则：保护现场与可恢复性](incident-response/02/) `平台`
- [31.3 从症状路由而不是猜根因](incident-response/03/) `平台`
- [31.4 决策、沟通与变更纪律](incident-response/04/) `平台`
- [31.5 单人值守与团队响应](incident-response/05/) `平台`
- [31.6 实战：盲抽症状的桌面演练](incident-response/06/) `平台`

### [32 PITR 与误操作恢复——妙手回春](pitr/)

在隔离环境中确定恢复目标、执行 PITR、验证业务正确性并安全回切。本章同时作为全书事故型样章。

- [32.1 先界定误操作](pitr/01/) `平台`
- [32.2 恢复目标与时间线](pitr/02/) `PG`
- [32.3 隔离恢复策略](pitr/03/) `平台`
- [32.4 执行恢复并观察进度](pitr/04/) `Pigsty`
- [32.5 数据验证与安全回切](pitr/05/) `PG`
- [32.6 实战：随机恢复目标演练](pitr/06/) `平台`

### [33 故障切换与集群重建——力挽狂澜](failover-rebuild/)

区分数据库、复制、网络与 DCS 故障，选择切换或重建路径，避免脑裂和错误时间线。

- [33.1 先识别失败域](failover-rebuild/01/) `平台`
- [33.2 复制状态与时间线证据](failover-rebuild/02/) `PG`
- [33.3 自动故障转移的保护条件](failover-rebuild/03/) `平台`
- [33.4 DCS 故障的安全处理](failover-rebuild/04/) `平台`
- [33.5 旧主重加入与集群重建](failover-rebuild/05/) `PG`
- [33.6 切换与重建 runbook](failover-rebuild/06/) `Pigsty`
- [33.7 实战：主库故障与 DCS 干扰](failover-rebuild/07/) `平台`

### [34 过载保护与资源故障判型——李代桃僵](overload-resource-incidents/)

从资源症状进入，第一步区分流量型与保留型；只对流量型执行限流、取消、摘流和降级，对保留型实施安全保护并路由到正确章节。

- [34.1 第一动作：流量型还是保留型](overload-resource-incidents/01/) `平台`
- [34.2 连接风暴与排队失控](overload-resource-incidents/02/) `平台`
- [34.3 失控查询、锁与事务](overload-resource-incidents/03/) `PG`
- [34.4 CPU、内存、I/O 与 OOM](overload-resource-incidents/04/) `平台`
- [34.5 流量型止血动作](overload-resource-incidents/05/) `平台`
- [34.6 保留型故障的安全路由](overload-resource-incidents/06/) `PG`
- [34.7 平台级流量控制与证据](overload-resource-incidents/07/) `Pigsty`
- [34.8 实战：同一症状、两种成因](overload-resource-incidents/08/) `平台`

### [35 数据抢救与工程取证——起死回生](data-rescue-forensics/)

面对页、索引、排序规则或逻辑不一致时先保护原始证据，再区分检测、修复、抽取与重建；不把危险技巧包装成常规运维。

- [35.1 现场保护与操作边界](data-rescue-forensics/01/) `平台`
- [35.2 先分类再抢救](data-rescue-forensics/02/) `PG`
- [35.3 页与 checksum 证据](data-rescue-forensics/03/) `PG`
- [35.4 索引、collation 与 `amcheck`](data-rescue-forensics/04/) `PG`
- [35.5 抽取、跳过与重建策略](data-rescue-forensics/05/) `PG`
- [35.6 工程取证与业务验证](data-rescue-forensics/06/) `平台`
- [35.7 实战：在克隆环境分类并恢复](data-rescue-forensics/07/) `平台`

### [36 事故复盘、控制固化与平台演进——举一反三](postmortem-platform-improvement/)

把一次恢复变成长期能力：解释因果链、修复控制缺口、验证改进，并为下一轮架构和版本演进建立优先级。

- [36.1 服务恢复不等于事件结束](postmortem-platform-improvement/01/) `平台`
- [36.2 从时间线建立因果链](postmortem-platform-improvement/02/) `平台`
- [36.3 证据质量与决策复盘](postmortem-platform-improvement/03/) `平台`
- [36.4 把行动项变成控制](postmortem-platform-improvement/04/) `平台`
- [36.5 回写 SLO、SOP 与架构 ADR](postmortem-platform-improvement/05/) `平台`
- [36.6 将控制固化到平台](postmortem-platform-improvement/06/) `Pigsty`
- [36.7 实战：复盘四类事故并完成全书结业](postmortem-platform-improvement/07/) `平台`
