---
title: PostgreSQL 36 计
linkTitle: 首页
description: 从 SQL 到生产：PostgreSQL 与 Pigsty 实战
cascade:
  type: docs
type: home
breadcrumbs: false
comments: false
---

> 从 SQL 到生产：PostgreSQL 与 Pigsty 实战

本书默认读者已经掌握 Linux 与通用 SQL，以 PostgreSQL 为核心知识对象，以 Pigsty 为统一实验载体、观察窗口和生产参考实现。

## 开始阅读

- [全书导读：读者假设、安全、版本与实验契约](/guide/)
- [第 0 章：准备实验环境（可跳过）](/ch00/)
- [完整目录：章、节、目](/toc/)
- [上卷导读与索引：应用开发](/upper-volume/)
- [下卷导读与索引：运维管理](/lower-volume/)
- [索引中心：角色、任务、能力、事故与分区](/indexes/)
- [序言：定位、利益披露与命名原则](/preface/)

## 36 章正文

36 个章节直接作为顶层导航项；“上卷／下卷”各自拥有一个并列的导读索引页，但不形成章节父目录或中间 URL 层级。

### 第一篇：筑基——建立 PostgreSQL 工程认知

- [ch01 盲人摸象：PostgreSQL 与 Pigsty 全局地图](/postgresql-pigsty-map/)
- [ch02 手到擒来：psql 与可复现工作流](/psql-workflow/)
- [ch03 正本清源：从业务规则到关系模型](/logical-data-model/)
- [ch04 量体裁衣：数据类型、约束与可靠数据表达](/data-types-constraints/)
- [ch05 运筹帷幄：查询、事务与锁的核心心智模型](/query-transaction-locks/)
- [ch06 立木取信：开发规约与交付基线](/development-standards/)

### 第二篇：应用——从 SQL 正确走向稳定交付

- [ch07 追本溯源：执行计划与统计信息](/query-plans-statistics/)
- [ch08 抽丝剥茧：慢 SQL 诊断方法论](/slow-query-diagnosis/)
- [ch09 巧夺天工：索引设计与效果验证](/index-design/)
- [ch10 顾此失彼：并发控制与隔离异常](/concurrency-isolation/)
- [ch11 守正出奇：模式变更与安全发布](/schema-change-release/)
- [ch12 一气呵成：从数据库契约到后端服务](/database-to-service/)

### 第三篇：扩展——扩大 PostgreSQL 的能力边界

- [ch13 言出法随：函数、触发器与存储过程](/functions-triggers-procedures/)
- [ch14 博采众长：内核分支与扩展生态](/extensions-ecosystem/)
- [ch15 见微知著：全文、模糊与向量检索](/search/)
- [ch16 经天纬地：时序、空间与时空查询](/spatiotemporal/)
- [ch17 合纵连横：分析加速与分布式选型](/analytics-distributed/)
- [ch18 万法归宗：PostgreSQL 数据平台与替代边界](/data-platform-boundaries/)

### 第四篇：规划——建设可交付的 PostgreSQL 服务

- [ch19 开天辟地：环境规划与部署基线](/deployment-baseline/)
- [ch20 狡兔三窟：高可用拓扑与容灾目标](/high-availability/)
- [ch21 未雨绸缪：备份体系与恢复演练](/backup-recovery/)
- [ch22 四通八达：服务接入、连接池与路由](/connection-pooling-routing/)
- [ch23 固若金汤：认证、授权与数据安全](/authentication-authorization-security/)
- [ch24 纲举目张：SLO、SOP 与组织治理](/slo-sop-governance/)

### 第五篇：运营——用证据驱动日常维护与演进

- [ch25 望闻问切：监控体系与可观测诊断](/observability/)
- [ch26 胸有成竹：容量规划与压测基线](/capacity-benchmarking/)
- [ch27 精益求精：参数调优与资源治理](/configuration-tuning/)
- [ch28 除旧布新：VACUUM、冻结与膨胀治理](/vacuum-freeze-bloat/)
- [ch29 移花接木：逻辑复制、迁移与异构同步](/logical-replication-migration/)
- [ch30 推陈出新：版本升级与回滚策略](/version-upgrade/)

### 第六篇：出山——按响应目标演练恢复与改进

- [ch31 事件分级、现场保护与应急决策——枕戈待旦](/incident-response/)
- [ch32 PITR 与误操作恢复——妙手回春](/pitr/)
- [ch33 故障切换与集群重建——力挽狂澜](/failover-rebuild/)
- [ch34 过载保护与资源故障判型——李代桃僵](/overload-resource-incidents/)
- [ch35 数据抢救与工程取证——起死回生](/data-rescue-forensics/)
- [ch36 事故复盘、控制固化与平台演进——举一反三](/postmortem-platform-improvement/)

## 当前版本

当前版本已经完成 36 个正文章、242 个独立节页与 772 个三级目的完整草稿，并为
ch01–ch36 提供配套实验资产。正文与实验统一使用 PostgreSQL 18.4、Pigsty v4.4.0
基线；涉及其他受支持版本的结论会就地标明适用范围。

页面 front matter 继续保留 `draft`、`reviewed` 与 `final` 状态，用于区分完整写作、
技术复核和出版审校，而不是把目录摘要冒充正文。勘误、版本增量验证与实验边界分别见
[附录 A](/appendices/a/)、[全书导读](/guide/)和[附录 E](/appendices/e/)。
