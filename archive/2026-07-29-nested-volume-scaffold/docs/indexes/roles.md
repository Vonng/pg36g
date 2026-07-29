---
title: 按角色阅读
linkTitle: 按角色阅读
weight: 10
type: docs
breadcrumbs: true
comments: false
book_kind: index
---

> 角色路线用于系统阅读；跨章跳读前仍应检查前置依赖。

## 应用开发者

- [ch01《PostgreSQL 与 Pigsty 全局地图》](/volume-1/postgresql-pigsty-map/) 至 [ch18《PostgreSQL 数据平台与替代边界》](/volume-1/data-platform-boundaries/)
- 生产接入补读：[ch22《服务接入、连接池与路由》](/volume-2/connection-pooling-routing/)、[ch23《认证、授权与数据安全》](/volume-2/authentication-authorization-security/)、[ch25《监控体系与可观测诊断》](/volume-2/observability/)

## DBA / SRE

- 基础：[ch01《PostgreSQL 与 Pigsty 全局地图》](/volume-1/postgresql-pigsty-map/)、[ch02《psql 与可复现工作流》](/volume-1/psql-workflow/)、[ch05《查询、事务与锁的核心心智模型》](/volume-1/query-transaction-locks/) 至 [ch10《并发控制与隔离异常》](/volume-1/concurrency-isolation/)
- 主线：[ch19《环境规划与部署基线》](/volume-2/deployment-baseline/) 至 [ch36《事故复盘、控制固化与平台演进》](/volume-2/postmortem-platform-improvement/)

## 架构师与平台工程师

- [ch01《PostgreSQL 与 Pigsty 全局地图》](/volume-1/postgresql-pigsty-map/)、[ch06《开发规约与交付基线》](/volume-1/development-standards/)、[ch12《从数据库契约到后端服务》](/volume-1/database-to-service/)、[ch14《内核分支与扩展生态》](/volume-1/extensions-ecosystem/)
- [ch17《分析加速与分布式选型》](/volume-1/analytics-distributed/) 至 [ch24《SLO、SOP 与组织治理》](/volume-2/slo-sop-governance/)，最后阅读 [ch36《事故复盘、控制固化与平台演进》](/volume-2/postmortem-platform-improvement/)

## 事故处置

- 先读 [ch31《事件分级、现场保护与应急决策》](/volume-2/incident-response/)，再按[事故症状索引](/indexes/incidents/)进入 ch32–ch35。
- 不建议脱离备份、高可用和维护前置知识直接照抄事故命令。
