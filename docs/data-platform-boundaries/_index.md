---
title: 第 18 章 万法归宗：PostgreSQL 数据平台与替代边界
linkTitle: 18 万法归宗：PostgreSQL 数据平台与替代边界
weight: 280
aliases:
- "/ch18/"
- "/volume-1/data-platform-boundaries/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch18
book_number: 18
book_part: part-3
book_status: draft
---

前 17 章分别回答了许多“PostgreSQL 能不能”的问题：

```text
能不能表达可靠的数据模型
能不能守住事务与并发不变量
能不能把数据库能力交付给应用
能不能用函数、触发器和扩展扩大边界
能不能完成检索、时空与分析工作
```

第 18 章换一个问法：

> 即使都能做，哪些能力应当留在 PostgreSQL，哪些只适合试点，哪些应当交给
> 外部系统；又由谁对组合后的整体服务负责？

这是从“数据库产品”走向“数据平台”的分水岭。

数据库不会因为装了更多扩展就自动成为平台；HA、备份、连接池和监控也不会
因为有了部署脚本就自动成为服务。平台至少还要给出：

```text
service objective   对外承诺什么
authority           每类数据由谁定夺
ownership           谁决策、谁值班、谁付成本
isolation           谁能互相影响
lifecycle           如何申请、变更、升级、退出
evidence            哪些结论已经证明
```

本章把上卷的功能证据组合成一份 `1.6-proposal`，同时把所有尚未证明的生产
结论交给下卷 18 个证据门。它不是庆功章，而是一份边界清单。

## 本章完成后

你应当能够：

- 把事务、检索、时空、分析和异步任务拆成独立能力，而不是用一个产品名概括；
- 区分数据/计算、存储、接入、控制与观察平面；
- 解释为什么多个健康组件仍可能交付一个不健康的端到端服务；
- 用延迟、新鲜度、正确性、可用性、RPO/RTO、容量和成本描述组合目标；
- 说明 PostgreSQL 的关系一致性、类型系统、扩展机制和统一查询为何有价值；
- 同时说明通用数据库中的 CPU、内存、I/O、WAL、连接、锁和维护竞争；
- 把“扩展已经安装”与“扩展已经生产准入”分开；
- 为缓存、消息、对象存储、湖仓和外部检索划分逐数据域的权威；
- 为每个派生副本写出新鲜度、顺序、幂等、重建、对账、删除和退出契约；
- 用测量触发器而不是技术潮流决定何时引入专用检索、流处理或分析系统；
- 设计开发、标准 HA、关键 HA 和离线分析四类服务产品；
- 在 schema、database、instance 和 cluster 隔离之间按信任与故障边界选择；
- 把连接、存储、临时文件、语句时间和维护窗口变成可执行配额；
- 说明 Pigsty 4.4 如何映射 PostgreSQL、Patroni、etcd、HAProxy、PgBouncer、
  pgBackRest 与观测能力；
- 分清 Pigsty 开箱能力、环境验收和组织流程；
- 运行一个完全只读的上卷能力审计；
- 读懂服务目录、外置数据契约、架构 ADR 与下卷证据门之间的引用关系；
- 拒绝“无证据宣称 L1 已通过”“缓存成为业务权威”“实验 FDW 准入生产”等
  反例；
- 把 `pg36_shop` 的当前结论准确表达为架构提案，而不是生产完成声明。

## 一张平台地图

```text
应用与运维身份
      |
服务契约：write / read-only / offline / admin
      |
PostgreSQL 权威状态
├── 事务、约束、短原子逻辑
├── pg_trgm 检索：accepted
├── vector 语义检索：pilot
├── PostGIS / btree_gist：conditional
└── 汇总 + offline replica：accepted first step
      |
派生与外置能力
├── cache：只持有可丢弃投影
├── event bus：持有投递与重放日志
├── object storage：持有媒体字节
├── lakehouse：持有带 watermark 的分析投影
└── external search：达到触发条件后才启用
```

图的关键不是方框数量，而是箭头上的合同。只要发生跨系统复制，就必须回答：

```text
authority       冲突时相信谁
freshness       最旧可以多旧
ordering        允许怎样乱序
idempotency     重试如何不重复生效
failure         一侧不可达时怎样退化
reconciliation  如何发现并修复分歧
deletion        删除如何跨副本传播
rebuild         如何从权威重新生成
exit            如何撤掉这个组件
```

这些字段被固化在
[`external-data-contracts.json`](/labs/ch18/external-data-contracts.json)，
不是留给实现阶段再想的“细节”。

## 当前提案，不是当前承诺

第 18 章的服务目录有四个 offering：

| ID | 用途 | 关键边界 |
|---|---|---|
| `pg-dev` | 有期限的开发/测试 | 不承诺 HA |
| `pg-ha-standard` | 默认生产事务服务 | 目标待下卷证明 |
| `pg-ha-critical` | 更强隔离与同步策略候选 | 必须先定义故障域 |
| `pg-analytics-offline` | ETL、慢读、交互分析 | 非权威、非 read-your-writes |

`service_objectives` 中出现的可用性、RPO、RTO 和新鲜度都是 proposal。节点数
不能证明故障域，配置文件不能证明收敛，备份成功不能证明可恢复，仪表盘存在
不能证明告警可行动。

因此蓝图明确写着：

```text
status=architecture-proposal-not-production-approval
postgresql=18.x target
validated_fixture=18.4
pigsty_reference=4.4
pigsty_l1_validation=not-run
lower_volume_gates=18 pending
```

这个诚实程度是架构质量的一部分。

## PostgreSQL 的能力与代价同时成立

PostgreSQL 把关系约束、事务、丰富类型、函数、操作符、索引方法和查询规划器
放在同一个一致性边界中。官方 [Extending SQL](https://www.postgresql.org/docs/18/extend.html)
列出的扩展点包括函数、聚合、数据类型、操作符、索引操作符类和扩展包。第
14–17 章已经证明这套机制可以把检索、向量、空间与远端数据纳入 SQL。

同一事实还有另一面：

```text
一个 shared_buffers
一组 CPU / I/O / worker 资源
一个 WAL 与 checkpoint 压力面
一组连接与后台维护预算
一条升级和恢复链
一个错误配置可能共享的爆炸半径
```

PostgreSQL 18 的
[Resource Consumption](https://www.postgresql.org/docs/18/runtime-config-resource.html)
特别提醒，`work_mem` 是每个 sort/hash 操作的基础上限；一条复杂查询可有
多个操作，同时还有多个会话。因此“通用”不是“无限”，统一也不是“免费”。

本章不在这两个事实中二选一。架构工作正是保留统一带来的收益，同时给资源
竞争、生命周期和失败传播设边界。

## Pigsty 的位置

Pigsty 4.4 的
[Architecture](https://pigsty.io/docs/concept/arch/)
以声明式 inventory 和模块组合交付环境；PGSQL、INFRA、NODE、ETCD 等模块
把 PostgreSQL 与 HA、接入、备份和观察组件连接起来。

本书把它作为参考实现，因为它能让抽象职责落到可读配置：

| 抽象职责 | Pigsty 参考映射 |
|---|---|
| 数据服务 | PostgreSQL cluster / database / role |
| HA 控制 | Patroni + etcd |
| 服务接入 | HAProxy，按需配 PgBouncer / VIP / DNS |
| 恢复 | pgBackRest 与仓库策略 |
| 主机与软件 | NODE / 软件仓库 / inventory |
| 指标与日志 | exporter、VictoriaMetrics/Logs、Grafana、Alertmanager |
| 分析隔离 | `pg_role: offline` 或 `pg_offline_query` |

Pigsty 官方
[Service Access](https://pigsty.io/docs/concept/ha/svc/)
把 service 定义为封装底层拓扑的访问抽象；本书沿用这个语义，不把某个节点
IP 叫作生产服务。

但参考实现不替团队完成：

```text
业务权威划分
SLO 与错误预算审批
威胁模型
容量预测
扩展准入
变更审批
演练与复盘
值班责任
```

这也是为什么
[`pigsty-declaration.example.yml`](/labs/ch18/pigsty-declaration.example.yml)
只能叫 proposal。

## 只读总验收

本章没有 `setup`，也没有 `reset`。它只读前面章节已经保留的 fixture：

```text
ch04 关系模型
ch13 原子数据库逻辑
ch14 扩展生命周期
ch15 搜索质量
ch16 时空语义
ch17 分析与 FDW 边界
```

然后连续抓取两轮：

```text
platform state
extension catalog
schema catalog
role catalog
capability lifecycle
cross-document policy report
negative policy report
```

两轮必须逐字节一致，最终输出：

```text
status=ok
preflight=ch04+ch13+ch14+ch15+ch16+ch17
cycles=2-byte-identical
documents=catalog+contracts+blueprint+18-pending-gates
counterexamples=7-rejected
pigsty_l1=not-run
mutation=none
```

通过只表示“当前开发证据与提案内部一致”，不表示任何生产 SLO 已经实现。

## 本章目录

### [18.1 从数据库产品到能力组合](01/)

- [18.1.1 事务、检索、时空、分析与任务能力](01/#item-18-1-1)
- [18.1.2 计算、存储、接入、控制与观察平面](01/#item-18-1-2)
- [18.1.3 组件组合必须有统一服务目标](01/#item-18-1-3)

### [18.2 PostgreSQL 的强项与代价](02/)

- [18.2.1 关系一致性、可扩展类型与统一查询](02/#item-18-2-1)
- [18.2.2 通用性带来的资源竞争与维护责任](02/#item-18-2-2)
- [18.2.3 扩展能力不自动等于生产就绪](02/#item-18-2-3)

### [18.3 明确替代边界](03/)

- [18.3.1 缓存、消息、对象存储与离线湖仓](03/#item-18-3-1)
- [18.3.2 超大规模检索、流处理与专用分析](03/#item-18-3-2)
- [18.3.3 用数据所有权、时效和一致性决定分工](03/#item-18-3-3)

### [18.4 平台服务目录与多租户](04/)

- [18.4.1 服务等级、规格、版本与扩展套餐](04/#item-18-4-1)
- [18.4.2 数据库、模式、实例和集群隔离](04/#item-18-4-2)
- [18.4.3 成本归属、配额和生命周期](04/#item-18-4-3)

### [18.5 Pigsty 作为参考实现](05/)

- [18.5.1 把 PostgreSQL、HA、备份、接入和观察组合起来](05/#item-18-5-1)
- [18.5.2 哪些能力开箱可用，哪些仍需组织流程](05/#item-18-5-2)
- [18.5.3 不把参考实现冒充唯一架构](05/#item-18-5-3)

### [18.6 实战：设计 `pg36_shop` 生产蓝图](06/)

- [18.6.1 选择保留在 PostgreSQL 内的能力](06/#item-18-6-1)
- [18.6.2 选择外置组件及其数据契约](06/#item-18-6-2)
- [18.6.3 输出服务目录草案、架构 ADR 与下卷验收问题](06/#item-18-6-3)

## 写作与验收提示

- 本章实验合同：
  [`lab-contract.md`](/labs/ch18/lab-contract.md)；
- 服务目录：
  [`service-catalog.json`](/labs/ch18/service-catalog.json)；
- 外置数据契约：
  [`external-data-contracts.json`](/labs/ch18/external-data-contracts.json)；
- 生产蓝图提案：
  [`baseline-v1.6-proposal.json`](/labs/ch18/baseline-v1.6-proposal.json)；
- 下卷证据门：
  [`lower-volume-gates.json`](/labs/ch18/lower-volume-gates.json)；
- 架构决定：
  [`architecture-adr.md`](/labs/ch18/architecture-adr.md)；
- 可执行入口：
  [`task.sh`](/labs/ch18/task.sh)。

下一章从第一个 pending gate 开始：不谈抽象生产级，而是建立
[部署基线与环境验收](/deployment-baseline/)。

---

[上一章：合纵连横：分析加速与分布式选型](/analytics-distributed/) · [返回上卷导读](/upper-volume/) · [下一章：开天辟地：环境规划与部署基线](/deployment-baseline/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
