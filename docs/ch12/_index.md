---
title: "12. 一气呵成：从数据库到后端服务"
weight: 1200
math: true
breadcrumbs: false
---

> [!Warn] 本章为 AI 生成的头脑风暴草稿目录，尚未编写，请务必注意。

## 章节概述

本章将深入探讨如何使用 Pigsty 和 PostgreSQL 搭建生产级的 Supabase 后端全家桶。从单机部署到高可用集群，从基础配置到性能优化，带你掌握自建 BaaS (Backend as a Service) 平台的完整流程。通过实战案例，你将学会如何开发一个包含用户认证、实时数据同步、对象存储的完整应用。

## 核心主题大纲

### 第一部分：从单机到全栈 - PostgreSQL 生产落地之路

#### 1.1 为什么选择自建 Supabase
- Firebase 的开源替代方案
- 数据主权和成本控制
- 定制化和扩展性优势
- 避免供应商锁定

#### 1.2 Supabase 架构全景
- PostgreSQL 核心数据库
- GoTrue 认证服务
- Realtime 实时订阅
- PostgREST API 网关
- Storage 对象存储
- Edge Functions 边缘函数
- Kong API 网关

#### 1.3 Pigsty 与 Supabase 的完美结合
- 为什么 Pigsty 是最佳选择
- 420+ PostgreSQL 扩展支持
- 生产级高可用架构
- 完整的监控可观测性

### 第二部分：快速起步 - 一键部署 Supabase

#### 2.1 环境准备
- 系统要求和硬件配置
- 网络规划和域名准备
- 安全密钥生成

#### 2.2 使用 Pigsty 部署 Supabase
```bash
curl -fsSL https://repo.pigsty.io/get | bash
cd ~/pigsty
./configure -c app/supa    # 使用 supabase 配置模板
vi pigsty.yml              # 编辑域名、密码、密钥
./install.yml              # 安装 pigsty
./docker.yml               # 安装 docker compose 组件
./app.yml                  # 启动 supabase 无状态组件
```

#### 2.3 Docker Compose 部署方案
- 官方 Docker 部署流程
- 配置文件详解
- 服务编排和依赖关系

#### 2.4 验证和访问
- Supabase Studio 管理界面
- 数据库连接测试
- API 端点验证

### 第三部分：PostgreSQL 生产配置最佳实践

#### 3.1 数据库初始化和用户管理
- 数据库结构设计
- 用户权限体系
- Schema 规划

#### 3.2 性能优化参数调整
- 内存配置优化
- 连接池配置
- 查询优化器参数
- Autovacuum 调优

#### 3.3 安全加固
- SSL/TLS 配置
- pg_hba.conf 访问控制
- Row Level Security (RLS) 策略
- 审计日志配置

#### 3.4 备份恢复策略
- pgBackRest 配置
- PITR 时间点恢复
- 定期备份计划
- 灾难恢复演练

### 第四部分：高可用架构设计与实现

#### 4.1 多节点 PostgreSQL 集群
- Patroni 高可用管理
- 流复制配置
- 同步提交模式
- 故障切换策略

#### 4.2 负载均衡和连接池
- HAProxy 负载均衡
- PgBouncer vs Supavisor
- 连接池模式选择
- 读写分离配置

#### 4.3 MinIO 高可用对象存储
- 单节点 vs 多节点部署
- 纠删码配置
- 多站点复制
- S3 兼容性配置

#### 4.4 监控和告警体系
- Prometheus + Grafana 监控栈
- 关键指标监控
- 告警规则配置
- 日志聚合分析

### 第五部分：Supabase 核心组件深度解析

#### 5.1 Auth (GoTrue) 认证系统
- JWT 令牌机制
- OAuth 社交登录集成
- 多因素认证 (MFA)
- 用户管理和权限

#### 5.2 Realtime 实时订阅
- WebSocket 连接管理
- PostgreSQL 逻辑复制
- Channel 订阅机制
- Presence 在线状态

#### 5.3 Storage 对象存储服务
- S3 协议兼容
- 文件上传策略
- CDN 加速配置
- 访问控制策略

#### 5.4 PostgREST API 自动生成
- RESTful API 设计
- GraphQL 支持 (pg_graphql)
- API 安全和限流
- 自定义函数和存储过程

#### 5.5 Edge Functions 边缘函数
- Deno 运行时环境
- 函数部署和管理
- 环境变量和密钥
- 性能优化技巧

### 第六部分：扩展功能与集成

#### 6.1 向量数据库功能 (pgvector)
- 嵌入向量存储
- 相似度搜索
- AI 应用集成
- 索引优化策略

#### 6.2 时序数据处理 (TimescaleDB)
- 超表设计
- 连续聚合
- 数据保留策略
- 性能优化

#### 6.3 任务调度 (pg_cron)
- 定时任务配置
- 维护作业管理
- 监控和日志

#### 6.4 外部数据源集成 (FDW)
- postgres_fdw 配置
- 跨库查询优化
- 数据同步策略

### 第七部分：实战项目 - 构建完整应用

#### 7.1 项目架构设计
- 需求分析
- 数据模型设计
- API 接口设计
- 前端技术选型

#### 7.2 用户认证系统实现
- 注册和登录流程
- 密码重置功能
- 社交登录集成
- 权限管理实现

#### 7.3 实时阅读量统计功能
- 数据表设计
- 实时订阅实现
- 前端实时更新
- 性能优化策略

#### 7.4 文件上传和管理
- 存储桶配置
- 上传策略实现
- 图片处理和优化
- CDN 集成

#### 7.5 部署和运维
- CI/CD 流程配置
- 监控告警设置
- 日志分析
- 性能调优

### 第八部分：进阶主题

#### 8.1 多租户架构
- Schema 隔离策略
- RLS 多租户实现
- 资源隔离和限制
- 计费和配额管理

#### 8.2 数据迁移策略
- 从云服务迁移
- pg_dump/pg_restore
- 逻辑复制迁移
- 零停机迁移方案

#### 8.3 安全合规
- GDPR 合规实践
- 数据加密策略
- 审计和合规报告
- 漏洞扫描和修复

#### 8.4 性能优化进阶
- 查询优化技巧
- 索引策略优化
- 分区表设计
- 缓存策略实现

## 动手实验设计

### 实验 1：快速部署 Supabase
- 使用 Pigsty 一键部署
- 验证各组件运行状态
- 创建第一个项目

### 实验 2：配置高可用 PostgreSQL
- 部署三节点集群
- 测试故障切换
- 配置读写分离

### 实验 3：实现用户认证
- 集成 Auth 组件
- 实现注册登录
- 配置 OAuth 登录

### 实验 4：开发实时功能
- 创建实时订阅
- 实现在线状态
- 广播消息功能

### 实验 5：对象存储实战
- 配置存储桶
- 实现文件上传
- 设置访问策略

### 实验 6：监控和告警
- 配置 Grafana 仪表盘
- 设置告警规则
- 分析性能瓶颈

### 实验 7：备份恢复演练
- 执行全量备份
- 测试时间点恢复
- 灾难恢复演练

### 实验 8：性能压测
- 使用 pgbench 压测
- 分析慢查询
- 优化数据库性能

## 初学者常见问题

1. **如何选择部署方式？**
   - 开发环境：Docker Compose
   - 生产环境：Pigsty + 高可用集群
   - 云原生：Kubernetes + CloudNativePG

2. **需要多少服务器资源？**
   - 最小配置：4核8G单机
   - 推荐配置：8核16G × 3节点
   - 大规模：根据负载扩展

3. **如何保证数据安全？**
   - 启用 SSL/TLS 加密
   - 配置 RLS 策略
   - 定期备份和演练
   - 监控异常访问

4. **性能优化从哪里开始？**
   - 监控慢查询
   - 优化索引设计
   - 调整连接池
   - 配置缓存策略

5. **如何处理高并发？**
   - 使用连接池
   - 读写分离
   - 缓存热点数据
   - 水平扩展

6. **备份策略如何制定？**
   - 日增量备份
   - 周全量备份
   - 异地灾备
   - 定期恢复测试

7. **如何监控系统健康？**
   - 配置 Prometheus 监控
   - 设置关键指标告警
   - 日志聚合分析
   - 定期巡检

8. **迁移现有系统注意什么？**
   - 评估数据量和复杂度
   - 制定迁移计划
   - 测试环境验证
   - 灰度切换策略

## 参考资料与延伸阅读

### Pigsty 官方资源
1. [Pigsty 官方文档](https://pigsty.io/docs/)
2. [Self-Hosting Supabase on PostgreSQL - Pigsty Blog](https://pigsty.io/blog/db/supabase/)
3. [Pigsty PostgreSQL 扩展目录](https://pgext.cloud/)
4. [Pigsty 监控系统文档](https://pigsty.io/docs/pgsql/monitor/)
5. [Pigsty 备份恢复 PITR 指南](https://pigsty.io/docs/pgsql/pitr/)
6. [Pigsty v3.4 发布说明](https://pigsty.io/blog/releases/v3.4.0/)
7. [Pigsty v3.3 发布说明](https://pigsty.io/blog/releases/v3.3.0/)
8. [Pigsty v3.2 发布说明](https://en.pigsty.cc/blog/releases/v3.2.0/)
9. [Pigsty v3.1 发布说明](https://pigsty.io/blog/releases/v3.1.0/)
10. [Pigsty v3.0 扩展爆炸式增长](https://pigsty.io/blog/releases/v3.0.0/)
11. [Pigsty 管理手册](https://pigsty.io/docs/pgsql/admin/)
12. [Pigsty Playbook 文档](https://pigsty.io/docs/setup/playbook/)
13. [Pigsty 精简安装指南](https://pigsty.io/docs/setup/slim/)
14. [Pigsty 生产级 PostgreSQL 介绍](https://pigsty.io/blog/pg/pigsty-intro/)
15. [Pigsty 价值主张](https://pigsty.io/about/values/)

### Supabase 官方文档
16. [Supabase 自托管文档](https://supabase.com/docs/guides/self-hosting)
17. [使用 Docker 自托管 Supabase](https://supabase.com/docs/guides/self-hosting/docker)
18. [Supabase Auth 文档](https://supabase.com/docs/guides/auth)
19. [Supabase Realtime 文档](https://supabase.com/docs/guides/realtime)
20. [Supabase Storage 文档](https://supabase.com/storage)
21. [Supabase Edge Functions 文档](https://supabase.com/docs/guides/functions)
22. [Supabase REST API 文档](https://supabase.com/docs/guides/api)
23. [Supabase 本地开发指南](https://supabase.com/docs/guides/local-development)
24. [Supabase CLI 使用指南](https://supabase.com/docs/guides/local-development/cli/getting-started)
25. [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
26. [Supabase 数据库连接指南](https://supabase.com/docs/guides/database/connecting-to-postgres)
27. [Supabase S3 兼容存储](https://supabase.com/blog/s3-compatible-storage)
28. [Supabase Edge Runtime 自托管](https://supabase.com/blog/edge-runtime-self-hosted-deno-functions)
29. [Supabase v1.0 发布说明](https://supabase.com/blog/supavisor-postgres-connection-pooler)
30. [Supabase 动态 JavaScript 执行](https://supabase.com/blog/supabase-dynamic-functions)

### PostgreSQL 核心技术
31. [PostgreSQL 官方文档](https://www.postgresql.org/docs/)
32. [PostgreSQL SSL/TLS 配置](https://www.postgresql.org/docs/current/ssl-tcp.html)
33. [PostgreSQL 持续归档和 PITR](https://www.postgresql.org/docs/current/continuous-archiving.html)
34. [PostgreSQL 高可用和复制](https://www.postgresql.org/docs/current/high-availability.html)
35. [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
36. [PostgreSQL 统计收集系统](https://www.postgresql.org/docs/current/monitoring-stats.html)
37. [PostgreSQL Autovacuum 配置](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html)
38. [PostgreSQL pg_dump 文档](https://www.postgresql.org/docs/current/app-pgdump.html)
39. [PostgreSQL postgres_fdw](https://www.postgresql.org/docs/current/postgres-fdw.html)
40. [PostgreSQL Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)

### PostgreSQL 扩展生态
41. [pgvector - 向量数据库扩展](https://github.com/pgvector/pgvector)
42. [pg_cron - 任务调度扩展](https://github.com/citusdata/pg_cron)
43. [pg_graphql - GraphQL 支持](https://github.com/supabase/pg_graphql)
44. [pg_stat_monitor - 查询性能监控](https://github.com/percona/pg_stat_monitor)
45. [pg_stat_statements 文档](https://www.postgresql.org/docs/current/pgstatstatements.html)
46. [PostgREST - REST API 生成器](https://postgrest.org/)
47. [TimescaleDB vs pg_partman](https://www.timescale.com/learn/pg_partman-vs-hypertables-for-postgres-partitioning)
48. [Foreign Data Wrappers Wiki](https://wiki.postgresql.org/wiki/Foreign_data_wrappers)
49. [CloudNativePG Operator](https://github.com/cloudnative-pg/cloudnative-pg)
50. [CloudNativePG 官网](https://cloudnative-pg.io/)

### 高可用与性能优化
51. [PostgreSQL 高可用策略指南](https://www.pgedge.com/blog/postgresql-high-availability-strategies-tools-best-practice)
52. [PostgreSQL 安全加固最佳实践](https://goteleport.com/blog/securing-postgres-postgresql/)
53. [启用和强制 PostgreSQL SSL/TLS](https://www.percona.com/blog/enabling-and-enforcing-ssl-tls-for-postgresql-connections/)
54. [PostgreSQL 数据库加固指南](https://www.mydbops.com/blog/postgresql-security-hardening)
55. [如何保护 PostgreSQL 安全](https://www.enterprisedb.com/blog/how-to-secure-postgresql-security-hardening-best-practices-checklist-tips-encryption-authentication-vulnerabilities)
56. [PostgreSQL Autovacuum 调优](https://www.percona.com/blog/tuning-autovacuum-in-postgresql-and-autovacuum-internals/)
57. [Autovacuum 调优基础](https://www.enterprisedb.com/blog/autovacuum-tuning-basics)
58. [PostgreSQL VACUUM 最佳实践](https://www.enterprisedb.com/blog/postgresql-vacuum-and-analyze-best-practice-tips)
59. [PostgreSQL 物理备份指南](https://stormatics.tech/blogs/postgresql-physical-backups-using-pg_basebackup-a-comprehensive-guide)
60. [PostgreSQL PITR 恢复](https://www.pgedge.com/blog/point-in-time-recovery-pitr-in-postgresql)

### 连接池与负载均衡
61. [Supavisor - 可扩展连接池](https://supabase.com/blog/supavisor-1-million)
62. [PgBouncer 使用指南](https://jpcamara.com/2023/04/12/pgbouncer-is-useful.html)
63. [PgBouncer 官网](https://www.pgbouncer.org/)
64. [PgBouncer 企业级应用](https://www.percona.com/blog/pgbouncer-for-postgresql-how-connection-pooling-solves-enterprise-slowdowns/)
65. [Supavisor vs PgBouncer 对比](https://www.restack.io/docs/supabase-knowledge-supabase-pgbouncer-guide)
66. [配置 Prisma 使用 PgBouncer](https://www.prisma.io/docs/orm/prisma-client/setup-and-configuration/databases-connections/pgbouncer)
67. [PostgreSQL 连接池方案对比](https://medium.com/btech-engineering/minio-high-availability-solutions-for-cluster-object-storage-ac4650521ff8)

### MinIO 对象存储
68. [MinIO 官网](https://www.min.io)
69. [MinIO GitHub 仓库](https://github.com/minio/minio)
70. [MinIO 高可用解决方案](https://medium.com/btech-engineering/minio-high-availability-solutions-for-cluster-object-storage-ac4650521ff8)
71. [MinIO 云原生集成](https://www.min.io/product/integrations)
72. [MinIO 下载页面](https://www.min.io/download)
73. [MinIO VMware 集成](https://min.io/solutions/vmware)
74. [MinIO 可用性和弹性](https://min.io/docs/minio/kubernetes/upstream/operations/concepts/availability-and-resiliency.html)
75. [MinIO 通知配置](https://min.io/docs/minio/linux/administration/monitoring/bucket-notifications.html)
76. [MinIO Webhook 通知](https://min.io/docs/minio/linux/reference/minio-server/settings/notifications/webhook-service.html)
77. [设置 MinIO 独立模式](https://www.digitalocean.com/community/tutorials/how-to-set-up-minio-object-storage-server-in-standalone-mode-on-ubuntu-20-04)

### 监控与可观测性
78. [使用 Prometheus 和 Grafana 监控 PostgreSQL](https://rezakhademix.medium.com/a-complete-guide-to-monitor-postgresql-with-prometheus-and-grafana-5611af229882)
79. [PostgreSQL 监控关键指标](https://www.sysdig.com/blog/postgresql-monitoring)
80. [PostgreSQL 监控实战](https://www.ashnik.com/monitoring-postgresql-with-prometheus-and-grafana/)
81. [使用 postgres_exporter 监控](https://fatdba.com/2021/03/24/how-to-monitor-your-postgresql-database-using-grafana-prometheus-postgres_exporter/)
82. [Grafana PostgreSQL 监控方案](https://grafana.com/solutions/postgresql/monitor/)
83. [配置 PostgreSQL exporter](https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/enable-prom-metrics-collection/data-stores/postgresql/)
84. [pg_stat_all_tables 监控](https://www.enterprisedb.com/blog/effective-postgresql-monitoring-utilizing-pg-stat-all-tables-and-indexes-postgresql-16)
85. [pg_stat_activity 实时监控](https://medium.com/@jramcloud1/monitoring-active-queries-in-postgresql-real-time-performance-diagnostics-using-pg-stat-activity-cd707a42aee7)
86. [pg_stat_statements 性能监控](https://blog.datasentinel.io/post/pg_stats_statements/)
87. [pg_stat_statements 综合指南](https://stormatics.tech/blogs/enhancing-postgresql-performance-monitoring-a-comprehensive-guide-to-pg_stat_statements)

### 实战教程与案例
88. [Supabase 自托管完整指南](https://medium.com/@christopher.mathews/how-to-self-host-supabase-on-your-own-computer-full-guide-cceac9b740ea)
89. [使用 Docker Compose 部署 Supabase](https://minhng.info/docker/supabase-docker-compose.html)
90. [Supabase Docker 使用指南](https://bootstrapped.app/guide/how-to-use-supabase-with-docker)
91. [Linode 上自托管 Supabase](https://www.linode.com/docs/guides/installing-supabase/)
92. [外部 PostgreSQL 配置 Supabase](https://dev.to/arthurkay/self-hosted-supabase-with-external-postgresql-apd)
93. [PostgreSQL 跨库查询实战](https://medium.com/@borntocode/how-to-run-a-postgres-cross-database-query-using-the-postgres-foreign-data-wrapper-postgres-fdw-7291db0e6e49)
94. [使用 pglogical 零停机迁移](https://jstaf.github.io/posts/pglogical/)
95. [PostgreSQL 增量备份和恢复](https://pgdash.io/blog/postgres-incremental-backup-recovery.html)
96. [使用 pg_basebackup 实现 PITR](https://medium.com/@dickson.gathima/pitr-in-postgresql-using-pg-basebackup-and-wal-6b5c4a7273bb)
97. [PostgreSQL WAL 归档实战](https://www.highgo.ca/2020/10/01/postgresql-wal-archiving-and-point-in-time-recovery/)

### Auth 认证系统
98. [Supabase Auth GitHub 仓库](https://github.com/supabase/auth)
99. [Supabase Auth 架构文档](https://supabase.com/docs/guides/auth/architecture)
100. [pgjwt 扩展文档](https://supabase.com/docs/guides/database/extensions/pgjwt)
101. [JWT 签名密钥介绍](https://supabase.com/blog/jwt-signing-keys)
102. [GoTrue Auth Server 文档](https://zone-www-dot-9obe9a1tk-supabase.vercel.app/docs/gotrue/server/about)
103. [Spring Boot JWT 认证集成](https://dev.to/tschuehly/simpler-jwt-authentication-for-spring-boot-using-gotrue-and-supabase-1goo)
104. [Supabase 自托管 Auth 参考](https://supabase.com/docs/reference/self-hosting-auth/introduction)
105. [掌握 Supabase RLS](https://dev.to/asheeshh/mastering-supabase-rls-row-level-security-as-a-beginner-5175)
106. [RLS 策略测试指南](https://blair-devmode.medium.com/testing-row-level-security-rls-policies-in-postgresql-with-pgtap-a-supabase-example-b435c1852602)
107. [Supabase API 安全](https://supabase.com/docs/guides/api/securing-your-api)

### Realtime 实时功能
108. [Supabase Realtime GitHub](https://github.com/supabase/realtime)
109. [Realtime 协议文档](https://supabase.com/docs/guides/realtime/protocol)
110. [Realtime 架构说明](https://supabase.com/docs/guides/realtime/architecture)
111. [Realtime WebSocket 认证](https://medium.com/@kyberneees/authenticate-realtime-pub-sub-websocket-clients-with-supabase-ed538a5eb47d)
112. [Supabase Realtime 产品页](https://supabase.com/realtime)
113. [自托管 Realtime 文档](https://supabase.com/docs/reference/self-hosting-realtime/introduction)
114. [realtime_client Dart 包](https://pub.dev/packages/realtime_client)
115. [Supabase RealTime 集成](https://docs.lowcoder.cloud/lowcoder-documentation/connect-your-data/data-sources-in-lowcoder/sql-databases/supabase/supabase-realtime)

### Storage 存储服务
116. [Supabase Storage GitHub](https://github.com/supabase/storage)
117. [Storage 访问控制](https://supabase.com/docs/guides/storage/security/access-control)
118. [Storage 产品介绍](https://supabase.com/blog/supabase-storage)
119. [S3 兼容性文档](https://supabase.com/docs/guides/storage/s3/compatibility)
120. [S3 认证配置](https://supabase.com/docs/guides/storage/s3/authentication)
121. [自托管 Storage 文档](https://supabase.com/docs/reference/self-hosting-storage/introduction)
122. [AWS S3 Wrapper 扩展](https://supabase.com/docs/guides/database/extensions/wrappers/s3)
123. [S3 兼容性功能](https://supabase.com/features/s3-compatibility)

### Edge Functions 边缘函数
124. [Supabase Edge Functions 产品页](https://supabase.com/edge-functions)
125. [Edge Functions 快速入门](https://supabase.com/docs/guides/functions/quickstart)
126. [Edge Functions 已发布](https://supabase.com/blog/supabase-edge-functions)
127. [Deno Edge Functions 功能](https://supabase.com/features/deno-edge-functions)
128. [Edge Functions 完整指南](https://blog.logrocket.com/using-edge-functions-supabase-complete-guide/)
129. [测试 Edge Functions](https://blog.mansueli.com/testing-supabase-edge-functions-with-deno-test)
130. [关于 Edge Functions 和 Deno](https://blog.starmorph.com/blog/about-supabase-edge-functions)

### API 开发
131. [pg_graphql 使用指南](https://supabase.com/blog/pg-graphql)
132. [pg_graphql 工作原理](https://supabase.com/blog/how-pg-graphql-works)
133. [pg_graphql 文档站](https://supabase.github.io/pg_graphql/)
134. [PostgREST 自动生成 REST API](https://supabase.com/features/auto-generated-rest-api)
135. [SQL 转 REST API 翻译器](https://supabase.com/docs/guides/api/sql-to-rest)
136. [Drizzle ORM RLS 支持](https://orm.drizzle.team/docs/rls)

### 数据库迁移
137. [AWS pg_dump 迁移指南](https://docs.aws.amazon.com/dms/latest/sbs/chap-manageddatabases.postgresql-rds-postgresql-full-load-pd_dump.html)
138. [PostgreSQL 迁移性能对比](https://docs.aws.amazon.com/dms/latest/sbs/chap-manageddatabases.postgresql-rds-postgresql-performance-comparison.html)
139. [pg_dump 和 pg_restore 教程](https://docs.vultr.com/how-to-backup-and-restore-postgresql-databases-using-pgdump-and-pgrestore)
140. [使用 pg_dumpall 升级](https://www.crunchydata.com/blog/performing-a-major-postgresql-upgrade-with-pg_dumpall)
141. [多主机环境 pg_dump 使用](https://www.enterprisedb.com/postgres-tutorials/how-use-pgdump-and-pgrestore-multi-host-enviorment)
142. [PostgreSQL FDW 理解](https://www.crunchydata.com/blog/understanding-postgres-fdw)
143. [FDW vs dblink 对比](https://www.percona.com/blog/foreign-data-wrappers-in-postgresql-databases-postgres_fdw-dblink/)
144. [FDW 探索指南](https://dev.to/k1hara/exploring-postgresql-foreign-data-wrappers-fdw-3l37)
145. [AWS RDS FDW 支持](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.foreign-data-wrappers.html)

### Kubernetes 部署
146. [CloudNativePG 快速入门](https://cloudnative-pg.io/documentation/current/quickstart/)
147. [GKE 部署 PostgreSQL](https://cloud.google.com/kubernetes-engine/docs/tutorials/stateful-workloads/cloudnativepg)
148. [Glasskube 部署 PostgreSQL](https://glasskube.dev/products/package-manager/guides/deploy-postgres-kubernetes/)
149. [CloudNativePG 文档](https://cloudnative-pg.io/docs/)
150. [CloudNativePG 初体验](https://www.enterprisedb.com/blog/Trying-Out-CloudNative-PG-Novice-Kubernetes-World)
151. [Kubernetes 上的 PostgreSQL](https://www.cloudraft.io/blog/postgresql-on-kubernetes)
152. [CloudNativePG 深入解析](https://medium.com/@smayya/postgresql-on-kubernetes-a-deep-dive-with-cloudnativepg-cnpg-59a3ea1fee63)
153. [Google Cloud HA 架构](https://cloud.google.com/architecture/architectures-high-availability-postgresql-clusters-compute-engine)
154. [Linode HA 方案对比](https://www.linode.com/docs/guides/comparison-of-high-availability-postgresql-solutions/)
155. [Severalnines 部署指南](https://severalnines.com/blog/how-deploy-postgresql-high-availability/)

### 中文资源
156. [PostgreSQL 中文教程 W3CSchool](https://www.w3cschool.cn/postgresql13_1/)
157. [PostgreSQL 16.2 中文文档](https://postgresql.mosong.cc/guide/)
158. [PostgreSQL 正体中文手册](https://docs.postgresql.tw/)
159. [PostgreSQL 中文社区 GitHub](https://github.com/postgres-cn/pgdoc-cn)
160. [腾讯云 PostgreSQL 主从架构](https://github.com/tencentyun/qcloud-documents/blob/master/product/计算与网络/云服务器/最佳实践/搭建%20PostgreSQL%20主从架构.md)
161. [JuiceFS PostgreSQL 最佳实践](https://juicefs.com/docs/community/postgresql_best_practices/)
162. [PostgREST 中文文档](https://postgrest.postgresql.ac.cn/en/v12/tutorials/tut0.html)

### 博客文章
163. [Vonng 的 PostgreSQL 博客](https://vonng.com/pg)
164. [Self-Hosting Supabase - Vonng](https://blog.vonng.com/en/pg/supabase/)
165. [PostgreSQL 36计](http://pg36g.vonng.com/)
166. [PostgreSQL 技术内幕](https://pgint.vonng.com/)
167. [PostgreSQL：最成功的数据库](https://vonng.com/cn/blog/db/pg-is-no1/)
168. [PostgreSQL 到底有多强？](https://vonng.com/cn/blog/db/pg-performence/)
169. [PGSQL x Pigsty: 数据库全能王](http://vonng.com/cn/blog/db/pgsql-x-pigsty/)
170. [AI时代的数据库与DBA将何去何从](https://vonng.com/cn/blog/db/)
171. [从PG'断供'看软件供应链中的信任问题](https://vonng.com/cn/blog/)
172. [PostgreSQL主宰数据库世界，而谁来吞噬PG？](https://vonng.com/cn/blog/)

### 性能优化专题
173. [PostgreSQL 分区表设计](https://www.percona.com/blog/postgresql-partitioning-made-easy-using-pg_partman-timebased/)
174. [5分钟学会 VACUUM 调优](https://pganalyze.com/blog/5mins-postgres-tuning-vacuum-autovacuum)
175. [VACUUM 性能优化](https://www.percona.com/blog/postgresql-vacuuming-to-optimize-database-performance-and-reclaim-space/)
176. [Autovacuum 重要性](https://www.percona.com/blog/importance-of-postgresql-vacuum-tuning-and-custom-scheduled-vacuum-job/)
177. [Azure Autovacuum 调优](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-autovacuum-tuning)
178. [pgvector 教程 - TigerData](https://www.tigerdata.com/blog/postgresql-as-a-vector-database-using-pgvector)
179. [OpenAI 嵌入存储](https://supabase.com/blog/openai-embeddings-postgres-vector)
180. [pgvector DataCamp 教程](https://www.datacamp.com/tutorial/pgvector-tutorial)
181. [pgvector 企业应用](https://www.enterprisedb.com/blog/what-is-pgvector)
182. [向量相似度搜索深入](https://severalnines.com/blog/vector-similarity-search-with-postgresqls-pgvector-a-deep-dive/)
183. [pgvector 入门和扩展](https://www.yugabyte.com/blog/postgresql-pgvector-getting-started/)
184. [AI 搜索和 RAG 实现](https://medium.com/@richardhightower/building-ai-powered-search-and-rag-with-postgresql-and-vector-embeddings-09af314dc2ff)
185. [PostgreSQL 作为向量数据库](https://airbyte.com/data-engineering-resources/postgresql-as-a-vector-database)

### 安全与合规
186. [Azure PostgreSQL SSL/TLS](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-networking-ssl-tls)
187. [设置 PostgreSQL SSL 认证](https://www.cybertec-postgresql.com/en/setting-up-ssl-authentication-for-postgresql/)
188. [AccuWeb SSL/TLS 加密](https://accuweb.cloud/resource/articles/postgres-ssl-addon)
189. [AWS RDS SSL 使用](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
190. [Azure 可靠性和高可用](https://learn.microsoft.com/en-us/azure/reliability/reliability-postgresql-flexible-server)
191. [Production-Grade 检查清单](https://stormatics.tech/blogs/checklist-is-your-postgresql-deployment-production-grade)
192. [HA 生产级指南](https://stormatics.tech/blogs/postgresql-production-grade-high-availability)

### 容器化部署
193. [Supabase Docker Compose 配置](https://github.com/supabase/supabase/blob/master/docker/docker-compose.yml)
194. [PostgreSQL TimescaleDB Docker](https://github.com/spitzenidee/postgresql_timescaledb)
195. [Docker 容器中使用 pg_cron](https://stackoverflow.com/questions/61582682/installing-and-using-pg-cron-extension-on-postgres-running-inside-of-docker-cont)
196. [CloudNativePG 备份恢复](https://cloudnative-pg.io/documentation/1.19/backup_recovery/)
197. [Kubernetes PostgreSQL 监控](https://medium.com/@dinhnguyen1812/monitoring-a-postgresql-cluster-on-kubernetes-with-prometheus-and-grafana-a9a69ec36f53)

### 扩展开发
198. [AWS pg_cron 使用指南](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL_pg_cron.html)
199. [pg_cron 定时任务](https://www.w3resource.com/PostgreSQL/snippets/postgresql-pg-cron.php)
200. [pg_cron 实战教程](https://medium.com/@tihomir.manushev/cron-jobs-with-postgresql-and-the-pg-cron-extension-3b808c7a326e)
201. [Neon pg_cron 文档](https://neon.com/docs/extensions/pg_cron)
202. [Scaleway pg_cron 设置](https://www.scaleway.com/en/docs/managed-databases-for-postgresql-and-mysql/api-cli/using-pgcron/)
203. [system_stats 扩展](https://www.enterprisedb.com/blog/monitoring-postgresql-database-system-activities-performance-system-stats-extension)
204. [pg_stat_monitor 文档](https://docs.percona.com/pg-stat-monitor/)
205. [Percona pg_stat_monitor](https://docs.percona.com/postgresql/14/pg-stat-monitor.html)

### 工具与生态
206. [Pigsty GitHub (英文)](https://github.com/pgsty/pigsty)
207. [Pigsty 中文站](http://www.pigsty.cc/)
208. [Pigsty 作为数据库 HashiCorp](https://medium.com/@techcelerated/pigsty-hashicorp-for-database-66cfc51ca698)
209. [LakeSoul PostgreSQL 集群部署](https://lakesoul-io.github.io/docs/Deployment/Postgres-Cluster)
210. [PostgreSQL v3.4 MySQL 兼容性](https://www.postgresql.org/about/news/pigsty-v34-released-pg-rds-with-mysql-compatibility-3052/)
211. [PostgreSQL v3.3 404 扩展](https://www.postgresql.org/about/news/pigsty-v33-release-with-404-postgresql-extensions-3023/)

### 云服务对比
212. [Firebase SDK 最佳实践](https://firebase.google.com/docs/web/best-practices)
213. [Lovable Supabase 集成](https://docs.lovable.dev/integrations/supabase)
214. [Supabase 数据库概览](https://supabase.com/docs/guides/database/overview)
215. [Supabase 官网](https://supabase.com/)
216. [云到自托管迁移](https://supabase.com/docs/guides/troubleshooting/transferring-from-cloud-to-self-host-in-supabase-2oWNvW)

### 监控工具
217. [PostgreSQL 性能监控](https://the-pi-guy.com/blog/monitoring_postgresql_performance_using_prometheus_and_grafana/)
218. [ComputingForGeeks 监控指南](https://computingforgeeks.com/monitor-postgresql-with-prometheus-grafana/)
219. [Redrock PostgreSQL 监控教程](https://www.rockdata.net/tutorial/monitor-with-prometheus-and-grafana/)

## 总结

本章通过深入探讨 Supabase 和 PostgreSQL 的结合，展示了如何构建一个功能完整、性能优异、安全可靠的后端服务平台。从单机部署到高可用集群，从基础配置到性能优化，你将掌握自建 BaaS 平台的完整技能栈。通过动手实验和实战项目，你不仅能理解各个组件的工作原理，更能在实际项目中灵活运用这些技术，打造属于自己的后端服务全家桶。