---
title: 按任务查找
linkTitle: 按任务查找
weight: 20
type: docs
breadcrumbs: true
comments: false
book_kind: index
---

> 按实际任务查找入口。章节链接始终同时显示编号与功能标题，避免重排后语义丢失。

| 任务 | 首选章节 | 必要前置 |
|---|---|---|
| 设计可靠模式 | [ch03《从业务规则到关系模型》](/logical-data-model/)、[ch04《数据类型、约束与可靠数据表达》](/data-types-constraints/) | [ch01《PostgreSQL 与 Pigsty 全局地图》](/postgresql-pigsty-map/)、[ch02《psql 与可复现工作流》](/psql-workflow/) |
| 查慢 SQL / 设计索引 | [ch07《执行计划与统计信息》](/query-plans-statistics/)、[ch08《慢 SQL 诊断方法论》](/slow-query-diagnosis/)、[ch09《索引设计与效果验证》](/index-design/) | [ch05《查询、事务与锁的核心心智模型》](/query-transaction-locks/) |
| 处理并发错误 | [ch10《并发控制与隔离异常》](/concurrency-isolation/) | [ch05《查询、事务与锁的核心心智模型》](/query-transaction-locks/) |
| 安全改表与发布 | [ch11《模式变更与安全发布》](/schema-change-release/)、[ch12《从数据库契约到后端服务》](/database-to-service/) | [ch06《开发规约与交付基线》](/development-standards/)、[ch07《执行计划与统计信息》](/query-plans-statistics/)、[ch08《慢 SQL 诊断方法论》](/slow-query-diagnosis/)、[ch09《索引设计与效果验证》](/index-design/)、[ch10《并发控制与隔离异常》](/concurrency-isolation/) |
| 选择扩展 | [ch14《内核分支与扩展生态》](/extensions-ecosystem/)、[ch15《全文、模糊与向量检索》](/search/)、[ch16《时序、空间与时空查询》](/spatiotemporal/)、[ch17《分析加速与分布式选型》](/analytics-distributed/)、[ch18《PostgreSQL 数据平台与替代边界》](/data-platform-boundaries/) | [ch07《执行计划与统计信息》](/query-plans-statistics/)、[ch08《慢 SQL 诊断方法论》](/slow-query-diagnosis/)、[ch09《索引设计与效果验证》](/index-design/)、[ch10《并发控制与隔离异常》](/concurrency-isolation/)、[ch11《模式变更与安全发布》](/schema-change-release/)、[ch12《从数据库契约到后端服务》](/database-to-service/) |
| 建设高可用与备份 | [ch19《环境规划与部署基线》](/deployment-baseline/)、[ch20《高可用拓扑与容灾目标》](/high-availability/)、[ch21《备份体系与恢复演练》](/backup-recovery/)、[ch22《服务接入、连接池与路由》](/connection-pooling-routing/) | [ch01《PostgreSQL 与 Pigsty 全局地图》](/postgresql-pigsty-map/)、[ch05《查询、事务与锁的核心心智模型》](/query-transaction-locks/) |
| 建立安全与治理 | [ch23《认证、授权与数据安全》](/authentication-authorization-security/)、[ch24《SLO、SOP 与组织治理》](/slo-sop-governance/)、[ch25《监控体系与可观测诊断》](/observability/) | [ch19《环境规划与部署基线》](/deployment-baseline/)、[ch20《高可用拓扑与容灾目标》](/high-availability/)、[ch21《备份体系与恢复演练》](/backup-recovery/)、[ch22《服务接入、连接池与路由》](/connection-pooling-routing/) |
| 压测、调优与维护 | [ch26《容量规划与压测基线》](/capacity-benchmarking/)、[ch27《参数调优与资源治理》](/configuration-tuning/)、[ch28《VACUUM、冻结与膨胀治理》](/vacuum-freeze-bloat/)、[ch29《逻辑复制、迁移与异构同步》](/logical-replication-migration/)、[ch30《版本升级与回滚策略》](/version-upgrade/) | [ch07《执行计划与统计信息》](/query-plans-statistics/)、[ch08《慢 SQL 诊断方法论》](/slow-query-diagnosis/)、[ch09《索引设计与效果验证》](/index-design/)、[ch10《并发控制与隔离异常》](/concurrency-isolation/)、[ch11《模式变更与安全发布》](/schema-change-release/)、[ch25《监控体系与可观测诊断》](/observability/) |
| 误操作恢复 | [ch31《事件分级、现场保护与应急决策》](/incident-response/)、[ch32《PITR 与误操作恢复》](/pitr/) | [ch21《备份体系与恢复演练》](/backup-recovery/) |
| 主库或 DCS 故障 | [ch31《事件分级、现场保护与应急决策》](/incident-response/)、[ch33《故障切换与集群重建》](/failover-rebuild/) | [ch20《高可用拓扑与容灾目标》](/high-availability/) |
| 连接风暴与资源耗尽 | [ch31《事件分级、现场保护与应急决策》](/incident-response/)、[ch34《过载保护与资源故障判型》](/overload-resource-incidents/) | [ch22《服务接入、连接池与路由》](/connection-pooling-routing/)、[ch25《监控体系与可观测诊断》](/observability/)、[ch26《容量规划与压测基线》](/capacity-benchmarking/)、[ch27《参数调优与资源治理》](/configuration-tuning/)、[ch28《VACUUM、冻结与膨胀治理》](/vacuum-freeze-bloat/) |
| 数据损坏与抢救 | [ch31《事件分级、现场保护与应急决策》](/incident-response/)、[ch35《数据抢救与工程取证》](/data-rescue-forensics/) | [ch21《备份体系与恢复演练》](/backup-recovery/)、[ch28《VACUUM、冻结与膨胀治理》](/vacuum-freeze-bloat/)、[ch30《版本升级与回滚策略》](/version-upgrade/) |
