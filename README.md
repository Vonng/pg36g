# PostgreSQL 36 计

[![Website: pg36g](https://img.shields.io/badge/在线阅读-pg36g.vonng.com-slategray?style=flat)](https://pg36g.vonng.com)

> 从 SQL 到生产：PostgreSQL 与 Pigsty 实战

**作者**：[冯若航（Vonng）](https://vonng.com)，Pigsty 作者与维护者。

![PostgreSQL 36 计](static/logo.png)

## 这本书解决什么问题

本书面向已经掌握 Linux 与通用 SQL、但尚未系统掌握 PostgreSQL 的读者。它以
PostgreSQL 为核心知识对象，以 Pigsty 为统一实验载体、观察窗口和生产参考实现，
把应用开发、平台建设、日常运营、故障恢复与复盘改进连接成一条可验证的学习路径。

当前仓库包含 36 个正文章、242 个独立节页、772 个三级目，以及 ch01–ch36 的
配套实验资产。正文使用 PostgreSQL 18.4、Pigsty v4.4.0 作为复现基线；版本差异、
实验拓扑、风险等级和不能外推的结论会在页面中明确标注。

## 阅读入口

- [全书导读](https://pg36g.vonng.com/guide/)：读者假设、安全、版本与实验契约
- [第 0 章](https://pg36g.vonng.com/ch00/)：准备实验环境；已有环境的读者可跳过
- [完整目录](https://pg36g.vonng.com/toc/)：36 章、242 节、772 目
- [上卷导读](https://pg36g.vonng.com/upper-volume/)：应用开发
- [下卷导读](https://pg36g.vonng.com/lower-volume/)：运维管理
- [索引中心](https://pg36g.vonng.com/indexes/)：按角色、任务、事故与能力查找

36 个章节在站点中直接作为顶层导航项；“上卷／下卷”是并列的导读与索引页，
不形成章节父目录或中间 URL 层级。

## 36 章目录

### [上卷：应用开发](https://pg36g.vonng.com/upper-volume/)

#### 第一篇：筑基——建立 PostgreSQL 工程认知

1. [盲人摸象：PostgreSQL 与 Pigsty 全局地图](https://pg36g.vonng.com/postgresql-pigsty-map/)
2. [手到擒来：psql 与可复现工作流](https://pg36g.vonng.com/psql-workflow/)
3. [正本清源：从业务规则到关系模型](https://pg36g.vonng.com/logical-data-model/)
4. [量体裁衣：数据类型、约束与可靠数据表达](https://pg36g.vonng.com/data-types-constraints/)
5. [运筹帷幄：查询、事务与锁的核心心智模型](https://pg36g.vonng.com/query-transaction-locks/)
6. [立木取信：开发规约与交付基线](https://pg36g.vonng.com/development-standards/)

#### 第二篇：应用——从 SQL 正确走向稳定交付

7. [追本溯源：执行计划与统计信息](https://pg36g.vonng.com/query-plans-statistics/)
8. [抽丝剥茧：慢 SQL 诊断方法论](https://pg36g.vonng.com/slow-query-diagnosis/)
9. [巧夺天工：索引设计与效果验证](https://pg36g.vonng.com/index-design/)
10. [顾此失彼：并发控制与隔离异常](https://pg36g.vonng.com/concurrency-isolation/)
11. [守正出奇：模式变更与安全发布](https://pg36g.vonng.com/schema-change-release/)
12. [一气呵成：从数据库契约到后端服务](https://pg36g.vonng.com/database-to-service/)

#### 第三篇：扩展——扩大 PostgreSQL 的能力边界

13. [言出法随：函数、触发器与存储过程](https://pg36g.vonng.com/functions-triggers-procedures/)
14. [博采众长：内核分支与扩展生态](https://pg36g.vonng.com/extensions-ecosystem/)
15. [见微知著：全文、模糊与向量检索](https://pg36g.vonng.com/search/)
16. [经天纬地：时序、空间与时空查询](https://pg36g.vonng.com/spatiotemporal/)
17. [合纵连横：分析加速与分布式选型](https://pg36g.vonng.com/analytics-distributed/)
18. [万法归宗：PostgreSQL 数据平台与替代边界](https://pg36g.vonng.com/data-platform-boundaries/)

### [下卷：运维管理](https://pg36g.vonng.com/lower-volume/)

#### 第四篇：规划——建设可交付的 PostgreSQL 服务

19. [开天辟地：环境规划与部署基线](https://pg36g.vonng.com/deployment-baseline/)
20. [狡兔三窟：高可用拓扑与容灾目标](https://pg36g.vonng.com/high-availability/)
21. [未雨绸缪：备份体系与恢复演练](https://pg36g.vonng.com/backup-recovery/)
22. [四通八达：服务接入、连接池与路由](https://pg36g.vonng.com/connection-pooling-routing/)
23. [固若金汤：认证、授权与数据安全](https://pg36g.vonng.com/authentication-authorization-security/)
24. [纲举目张：SLO、SOP 与组织治理](https://pg36g.vonng.com/slo-sop-governance/)

#### 第五篇：运营——用证据驱动日常维护与演进

25. [望闻问切：监控体系与可观测诊断](https://pg36g.vonng.com/observability/)
26. [胸有成竹：容量规划与压测基线](https://pg36g.vonng.com/capacity-benchmarking/)
27. [精益求精：参数调优与资源治理](https://pg36g.vonng.com/configuration-tuning/)
28. [除旧布新：VACUUM、冻结与膨胀治理](https://pg36g.vonng.com/vacuum-freeze-bloat/)
29. [移花接木：逻辑复制、迁移与异构同步](https://pg36g.vonng.com/logical-replication-migration/)
30. [推陈出新：版本升级与回滚策略](https://pg36g.vonng.com/version-upgrade/)

#### 第六篇：出山——按响应目标演练恢复与改进

31. [事件分级、现场保护与应急决策——枕戈待旦](https://pg36g.vonng.com/incident-response/)
32. [PITR 与误操作恢复——妙手回春](https://pg36g.vonng.com/pitr/)
33. [故障切换与集群重建——力挽狂澜](https://pg36g.vonng.com/failover-rebuild/)
34. [过载保护与资源故障判型——李代桃僵](https://pg36g.vonng.com/overload-resource-incidents/)
35. [数据抢救与工程取证——起死回生](https://pg36g.vonng.com/data-rescue-forensics/)
36. [事故复盘、控制固化与平台演进——举一反三](https://pg36g.vonng.com/postmortem-platform-improvement/)

## 本地验证

```bash
make check-book
make build
```

`check-book` 会核对章节元数据、目录与索引覆盖、相邻节导航、历史 URL 别名、
内部链接和 Hugo 构建。实验中的生产 gate、凭据和破坏性动作不会因为站点构建通过
而自动获得批准；请始终遵守各章写明的目标、拓扑、风险和停止条件。

## 许可证

[![License: CC BY-NC-SA 4.0](https://img.shields.io/github/license/Vonng/pg36g?logo=opensourceinitiative&logoColor=green&color=slategray)](https://github.com/Vonng/pg36g/blob/main/LICENSE)

本项目采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可。
