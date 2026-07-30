---
title: 上卷：应用开发
linkTitle: 上卷：应用开发
weight: 100
aliases:
- "/volume-1/"
- "/dev/"
type: docs
breadcrumbs: true
comments: false
book_kind: volume-overview
book_number: 1
book_status: draft
---

> **本卷导读**：上卷面向应用开发者与数据库工程实践者，沿着“认识系统—可靠建模—正确查询—性能与并发—安全交付—能力扩展”的路径，建立从 PostgreSQL 原理到 Pigsty 实验闭环的完整开发能力。

## 本卷定位

从 PostgreSQL 工程认知到应用交付与能力扩展

本页是位于顶层导航中的导读与索引页，不是章节父目录。下面各章仍与本页并列，使用独立的顶层 URL；读者既可以按本卷路径顺序学习，也可以直接进入任意章节。

## 本卷索引

### 第一篇：筑基——建立 PostgreSQL 工程认知

#### [ch01 盲人摸象：PostgreSQL 与 Pigsty 全局地图](/postgresql-pigsty-map/)

回答“我连到了什么、数据对象在哪里、一次查询经过什么、Pigsty 又管理了什么”，并固化后续章节共同使用的实验基线。

- [1.1 从连接串识别操作落点](/postgresql-pigsty-map/01/)
- [1.2 PostgreSQL 对象与术语坐标](/postgresql-pigsty-map/02/)
- [1.3 一条查询经过了什么](/postgresql-pigsty-map/03/)
- [1.4 从数据库实例到数据库服务](/postgresql-pigsty-map/04/)
- [1.5 Pigsty 的资源模型](/postgresql-pigsty-map/05/)
- [1.6 最小 psql 生存卡](/postgresql-pigsty-map/06/)
- [1.7 实战：建立 `pg36_shop` 地图与实验基线](/postgresql-pigsty-map/07/)

#### [ch02 手到擒来：psql 与可复现工作流](/psql-workflow/)

掌握后续 34 章反复使用的最小工具链，把临时手工操作变成可审查、可验证、可重跑的任务。

- [2.1 可靠连接与上下文保护](/psql-workflow/01/)
- [2.2 用 psql 探索与取证](/psql-workflow/02/)
- [2.3 编写可靠 SQL 脚本](/psql-workflow/03/)
- [2.4 输入、输出与确定性数据](/psql-workflow/04/)
- [2.5 最小 pgbench 工作负载](/psql-workflow/05/)
- [2.6 最小逻辑备份闭环](/psql-workflow/06/)
- [2.7 实战：把人工操作变成可重跑任务](/psql-workflow/07/)

#### [ch03 正本清源：从业务规则到关系模型](/logical-data-model/)

先表达业务事实、不变量与所有权，再把逻辑模型 v0 跑进真实数据库；本章模式是过渡版本，可靠物理模式在 ch04 闭合。

- [3.1 从业务语言提取数据库事实](/logical-data-model/01/)
- [3.2 标识、主键与业务键](/logical-data-model/02/)
- [3.3 关系与引用完整性](/logical-data-model/03/)
- [3.4 模式、所有权与对象边界](/logical-data-model/04/)
- [3.5 规范化与有意识的冗余](/logical-data-model/05/)
- [3.6 实战：建立逻辑模型 v0](/logical-data-model/06/)

#### [ch04 量体裁衣：数据类型、约束与可靠数据表达](/data-types-constraints/)

利用 PostgreSQL 类型系统、约束与分区决策，把 ch03 的逻辑模型逐项落成可靠物理模式。

- [4.1 金额、文本与时间](/data-types-constraints/01/)
- [4.2 标识、状态与半结构化数据](/data-types-constraints/02/)
- [4.3 NULL、默认值与生成值](/data-types-constraints/03/)
- [4.4 用约束表达不变量](/data-types-constraints/04/)
- [4.5 类型与约束的物理代价](/data-types-constraints/05/)
- [4.6 分区决策门](/data-types-constraints/06/)
- [4.7 实战：把逻辑模型落成可靠物理模式](/data-types-constraints/07/)

#### [ch05 运筹帷幄：查询、事务与锁的核心心智模型](/query-transaction-locks/)

建立执行计划、并发控制和故障诊断共同依赖的原理地图，不在本章穷举后续专题。

- [5.1 SQL 从文本到结果](/query-transaction-locks/01/)
- [5.2 MVCC 与可见性](/query-transaction-locks/02/)
- [5.3 事务边界与失败语义](/query-transaction-locks/03/)
- [5.4 锁与等待](/query-transaction-locks/04/)
- [5.5 隔离现象与后续路线](/query-transaction-locks/05/)
- [5.6 实战：观察一笔订单事务](/query-transaction-locks/06/)

#### [ch06 立木取信：开发规约与交付基线](/development-standards/)

不提前宣判“最佳实践”，而是建立“候选规则—证据—适用范围—例外—验证”的规约生成方法，产出 baseline v0.1。

- [6.1 规约不是口号](/development-standards/01/)
- [6.2 连接与会话候选规则](/development-standards/02/)
- [6.3 模式与 DDL 候选规则](/development-standards/03/)
- [6.4 查询与事务候选规则](/development-standards/04/)
- [6.5 交付物与质量门](/development-standards/05/)
- [6.6 将规约接入统一实验环境](/development-standards/06/)
- [6.7 实战：发布规约 baseline v0.1](/development-standards/07/)

### 第二篇：应用——从 SQL 正确走向稳定交付

#### [ch07 追本溯源：执行计划与统计信息](/query-plans-statistics/)

学会读计划、验证估算、解释计划变化，并建立分区裁剪和自动计划采样的正确边界。

- [7.1 优化器如何选择路径](/query-plans-statistics/01/)
- [7.2 正确使用 EXPLAIN](/query-plans-statistics/02/)
- [7.3 统计信息与估算偏差](/query-plans-statistics/03/)
- [7.4 分区裁剪的两种时机](/query-plans-statistics/04/)
- [7.5 参数、缓存计划与计划漂移](/query-plans-statistics/05/)
- [7.6 建立计划证据基线](/query-plans-statistics/06/)
- [7.7 实战：解释订单查询的计划变化](/query-plans-statistics/07/)

#### [ch08 抽丝剥茧：慢 SQL 诊断方法论](/slow-query-diagnosis/)

从“用户说慢”出发，建立从范围界定、证据收集、假设排序到受控验证的诊断闭环。本章同时作为全书方法型样章。

- [8.1 先定义“慢”](/slow-query-diagnosis/01/)
- [8.2 从会话到语句定位范围](/slow-query-diagnosis/02/)
- [8.3 关联日志、指标与计划](/slow-query-diagnosis/03/)
- [8.4 建立而不是猜测假设](/slow-query-diagnosis/04/)
- [8.5 设计受控实验](/slow-query-diagnosis/05/)
- [8.6 从可观测面板回到原生证据](/slow-query-diagnosis/06/)
- [8.7 实战：三种“慢”只修真正瓶颈](/slow-query-diagnosis/07/)

#### [ch09 巧夺天工：索引设计与效果验证](/index-design/)

从访问模式而不是字段直觉设计索引，并用读取收益、写入代价与维护成本共同验收。

- [9.1 索引方法与操作符类](/index-design/01/)
- [9.2 从谓词、连接与排序推导索引](/index-design/02/)
- [9.3 表达式、部分与覆盖索引](/index-design/03/)
- [9.4 索引也有写入和生命周期成本](/index-design/04/)
- [9.5 验证而不是“加完就快”](/index-design/05/)
- [9.6 实战：为订单、库存与搜索入口设计索引](/index-design/06/)

#### [ch10 顾此失彼：并发控制与隔离异常](/concurrency-isolation/)

在明确隔离级别和业务不变量的前提下重现并发异常，选择锁、条件更新、重试与幂等策略。

- [10.1 隔离级别与可观察现象](/concurrency-isolation/01/)
- [10.2 Lost update 不是一句口号](/concurrency-isolation/02/)
- [10.3 悲观锁与锁队列](/concurrency-isolation/03/)
- [10.4 乐观控制、重试与幂等](/concurrency-isolation/04/)
- [10.5 咨询锁与跨行协调](/concurrency-isolation/05/)
- [10.6 观察与诊断并发](/concurrency-isolation/06/)
- [10.7 实战：库存扣减与支付幂等](/concurrency-isolation/07/)

#### [ch11 守正出奇：模式变更与安全发布](/schema-change-release/)

先判断锁、重写、扫描和兼容性，再设计可观察、可中止、可回退的模式发布；完成分区能力的第三个触点。

- [11.1 识别 DDL 的四类风险](/schema-change-release/01/)
- [11.2 Expand–Migrate–Contract](/schema-change-release/02/)
- [11.3 索引与约束的在线化路径](/schema-change-release/03/)
- [11.4 在线分区化](/schema-change-release/04/)
- [11.5 数据回填与流量切换](/schema-change-release/05/)
- [11.6 发布窗口中的平台观察](/schema-change-release/06/)
- [11.7 实战：无中断演进订单模式](/schema-change-release/07/)

#### [ch12 一气呵成：从数据库契约到后端服务](/database-to-service/)

把前十一章收束成一个可运行、可观测、可部署的最小服务；后续章节不再长期维护同一套 Go 代码。

- [12.1 数据库契约与应用边界](/database-to-service/01/)
- [12.2 为服务设计查询接口](/database-to-service/02/)
- [12.3 Go 服务中的连接与事务](/database-to-service/03/)
- [12.4 会话状态与连接池陷阱](/database-to-service/04/)
- [12.5 服务级可观测性](/database-to-service/05/)
- [12.6 部署与接入 `pg36_shop`](/database-to-service/06/)
- [12.7 实战：交付应用闭环与规约 v1.0](/database-to-service/07/)

### 第三篇：扩展——扩大 PostgreSQL 的能力边界

#### [ch13 言出法随：函数、触发器与存储过程](/functions-triggers-procedures/)

判断逻辑应该位于 SQL、数据库函数、触发器还是应用中，并能测试、观测和安全发布数据库端逻辑。

- [13.1 先决定逻辑放在哪里](/functions-triggers-procedures/01/)
- [13.2 SQL 与 PL/pgSQL 函数](/functions-triggers-procedures/02/)
- [13.3 触发器与约束触发器](/functions-triggers-procedures/03/)
- [13.4 过程、任务与事务控制](/functions-triggers-procedures/04/)
- [13.5 安全、测试与观测](/functions-triggers-procedures/05/)
- [13.6 实战：为订单状态建立数据库端护栏](/functions-triggers-procedures/06/)

#### [ch14 博采众长：内核分支与扩展生态](/extensions-ecosystem/)

不从“能安装”推导“该使用”，建立扩展发现、选型、供应链、升级与退出的统一 ADR。

- [14.1 PostgreSQL 扩展机制](/extensions-ecosystem/01/)
- [14.2 内核、发行版与托管服务](/extensions-ecosystem/02/)
- [14.3 扩展选型的六个问题](/extensions-ecosystem/03/)
- [14.4 生命周期与升级耦合](/extensions-ecosystem/04/)
- [14.5 用 Pigsty 管理扩展可用性](/extensions-ecosystem/05/)
- [14.6 建立可复用扩展 ADR](/extensions-ecosystem/06/)
- [14.7 实战：评审三个候选扩展](/extensions-ecosystem/07/)

#### [ch15 见微知著：全文、模糊与向量检索](/search/)

从检索质量与业务语义出发，完成全文、模糊、向量和混合检索的最小可复现 PoC，并知道生产代价。

- [15.1 先定义检索任务与评估集](/search/01/)
- [15.2 PostgreSQL 全文检索](/search/02/)
- [15.3 模糊匹配与拼写容错](/search/03/)
- [15.4 可复现的向量检索](/search/04/)
- [15.5 混合检索与排序验证](/search/05/)
- [15.6 扩展部署与运行代价](/search/06/)
- [15.7 实战：`pg36_shop` 商品混合检索 PoC](/search/07/)

#### [ch16 经天纬地：时序、空间与时空查询](/spatiotemporal/)

分别建立时间与空间数据的正确模型，最终用时空联合查询证明两者为何值得在同一章出现。

- [16.1 时间语义先于时序扩展](/spatiotemporal/01/)
- [16.2 时序表与时间分区](/spatiotemporal/02/)
- [16.3 空间类型与坐标参考](/spatiotemporal/03/)
- [16.4 空间谓词与索引](/spatiotemporal/04/)
- [16.5 时空联合查询是本章收束目标](/spatiotemporal/05/)
- [16.6 时空扩展的交付与观察](/spatiotemporal/06/)
- [16.7 实战：配送事件的时空 PoC](/spatiotemporal/07/)

#### [ch17 合纵连横：分析加速与分布式选型](/analytics-distributed/)

先用证据证明单机边界，再比较单机分析加速与分布式方案，完成最小 PoC；不预演下卷的复制、路由和多集群运维。

- [17.1 先证明单机边界](/analytics-distributed/01/)
- [17.2 单机分析能力](/analytics-distributed/02/)
- [17.3 何时需要分布式](/analytics-distributed/03/)
- [17.4 比较分布式候选](/analytics-distributed/04/)
- [17.5 部署最小分布式 PoC](/analytics-distributed/05/)
- [17.6 实战：从单机证据到选型 ADR](/analytics-distributed/06/)

#### [ch18 万法归宗：PostgreSQL 数据平台与替代边界](/data-platform-boundaries/)

把上卷能力组合成一张数据平台地图，同时明确 PostgreSQL 不应该承担的工作，为下卷的服务建设建立边界。

- [18.1 从数据库产品到能力组合](/data-platform-boundaries/01/)
- [18.2 PostgreSQL 的强项与代价](/data-platform-boundaries/02/)
- [18.3 明确替代边界](/data-platform-boundaries/03/)
- [18.4 平台服务目录与多租户](/data-platform-boundaries/04/)
- [18.5 Pigsty 作为参考实现](/data-platform-boundaries/05/)
- [18.6 实战：设计 `pg36_shop` 生产蓝图](/data-platform-boundaries/06/)

## 前后衔接

- 开始前：[全书导读](/guide/) · [第 0 章（可跳过）](/ch00/)
- 完成本卷后：[下卷：运维管理](/lower-volume/)
