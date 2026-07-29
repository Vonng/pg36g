---
title: PostgreSQL 36 计
linkTitle: 首页
cascade:
  type: docs
breadcrumbs: false
comments: false
---

> 从 SQL 到生产：PostgreSQL 与 Pigsty 实战

本书默认读者已经掌握 Linux 与通用 SQL，以 PostgreSQL 为核心知识对象，以 Pigsty 为统一实验载体、观察窗口和生产参考实现。

## 开始阅读

- [全书导读：读者假设、安全、版本与实验契约](/guide/)
- [第 0 章：准备实验环境（可跳过）](/ch00/)
- [完整目录：卷、章、节、目](/toc/)
- [索引中心：角色、任务、能力、事故与分区](/indexes/)
- [序言：定位、利益披露与命名原则](/preface/)

## [上卷：应用开发](/volume-1/)

从 PostgreSQL 工程认知到应用交付与能力扩展

### 筑基篇

- [ch01 盲人摸象：PostgreSQL 与 Pigsty 全局地图](/volume-1/postgresql-pigsty-map/)
- [ch02 手到擒来：psql 与可复现工作流](/volume-1/psql-workflow/)
- [ch03 正本清源：从业务规则到关系模型](/volume-1/logical-data-model/)
- [ch04 量体裁衣：数据类型、约束与可靠数据表达](/volume-1/data-types-constraints/)
- [ch05 运筹帷幄：查询、事务与锁的核心心智模型](/volume-1/query-transaction-locks/)
- [ch06 立木取信：开发规约与交付基线](/volume-1/development-standards/)

### 应用篇

- [ch07 追本溯源：执行计划与统计信息](/volume-1/query-plans-statistics/)
- [ch08 抽丝剥茧：慢 SQL 诊断方法论](/volume-1/slow-query-diagnosis/)
- [ch09 巧夺天工：索引设计与效果验证](/volume-1/index-design/)
- [ch10 顾此失彼：并发控制与隔离异常](/volume-1/concurrency-isolation/)
- [ch11 守正出奇：模式变更与安全发布](/volume-1/schema-change-release/)
- [ch12 一气呵成：从数据库契约到后端服务](/volume-1/database-to-service/)

### 扩展篇

- [ch13 言出法随：函数、触发器与存储过程](/volume-1/functions-triggers-procedures/)
- [ch14 博采众长：内核分支与扩展生态](/volume-1/extensions-ecosystem/)
- [ch15 见微知著：全文、模糊与向量检索](/volume-1/search/)
- [ch16 经天纬地：时序、空间与时空查询](/volume-1/spatiotemporal/)
- [ch17 合纵连横：分析加速与分布式选型](/volume-1/analytics-distributed/)
- [ch18 万法归宗：PostgreSQL 数据平台与替代边界](/volume-1/data-platform-boundaries/)

## [下卷：运维管理](/volume-2/)

从生产服务规划到日常运营、事故恢复与改进

### 规划篇

- [ch19 开天辟地：环境规划与部署基线](/volume-2/deployment-baseline/)
- [ch20 狡兔三窟：高可用拓扑与容灾目标](/volume-2/high-availability/)
- [ch21 未雨绸缪：备份体系与恢复演练](/volume-2/backup-recovery/)
- [ch22 四通八达：服务接入、连接池与路由](/volume-2/connection-pooling-routing/)
- [ch23 固若金汤：认证、授权与数据安全](/volume-2/authentication-authorization-security/)
- [ch24 纲举目张：SLO、SOP 与组织治理](/volume-2/slo-sop-governance/)

### 运营篇

- [ch25 望闻问切：监控体系与可观测诊断](/volume-2/observability/)
- [ch26 胸有成竹：容量规划与压测基线](/volume-2/capacity-benchmarking/)
- [ch27 精益求精：参数调优与资源治理](/volume-2/configuration-tuning/)
- [ch28 除旧布新：VACUUM、冻结与膨胀治理](/volume-2/vacuum-freeze-bloat/)
- [ch29 移花接木：逻辑复制、迁移与异构同步](/volume-2/logical-replication-migration/)
- [ch30 推陈出新：版本升级与回滚策略](/volume-2/version-upgrade/)

### 出山篇

- [ch31 事件分级、现场保护与应急决策——枕戈待旦](/volume-2/incident-response/)
- [ch32 PITR 与误操作恢复——妙手回春](/volume-2/pitr/)
- [ch33 故障切换与集群重建——力挽狂澜](/volume-2/failover-rebuild/)
- [ch34 过载保护与资源故障判型——李代桃僵](/volume-2/overload-resource-incidents/)
- [ch35 数据抢救与工程取证——起死回生](/volume-2/data-rescue-forensics/)
- [ch36 事故复盘、控制固化与平台演进——举一反三](/volume-2/postmortem-platform-improvement/)

## 脚手架说明

当前站点已经建立全部章、节与目的页面骨架。每个“节”是独立页面，每个“目”都有稳定锚点和一段写作摘要；页面状态统一标记为 `scaffold`，不把摘要冒充已经完成的正文。
