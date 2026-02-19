---
title: "11. 守正出奇：模式变更与发布策略"
weight: 1100
math: true
breadcrumbs: false
---

> [!Warn] 本章为 AI 生成的头脑风暴草稿目录，尚未编写，请务必注意。

## 章节概述

本章将深入探讨如何使用 Pigsty 部署各种基于 PostgreSQL 的企业级软件。随着开源生态的发展，越来越多的企业软件选择 PostgreSQL 作为其核心数据库。通过 Pigsty 的一站式部署能力，我们可以快速拉起生产级别的应用环境。

## 主要内容大纲

### 11.1 企业软件与 PostgreSQL 生态

#### 11.1.1 为什么企业软件选择 PostgreSQL
- PostgreSQL 的企业级特性：ACID、MVCC、扩展性
- 开源协议的友好性（PostgreSQL License）
- 丰富的扩展生态系统
- 与云原生架构的契合度

#### 11.1.2 Pigsty 的应用部署架构
- 有状态组件 vs 无状态组件的分离
- 基于 Docker Compose 的应用模板
- app.yml 自动化部署流程
- 与高可用 PostgreSQL 集群的集成

#### 11.1.3 部署前的准备工作
- 硬件资源规划
- 网络架构设计
- 安全配置考虑
- 备份恢复策略

### 11.2 AI 工作流平台：Dify

#### 11.2.1 Dify 架构概述
- LLMOps 平台的核心组件
- PostgreSQL 元数据存储
- PGVector 向量数据库集成
- Redis 缓存层设计

#### 11.2.2 使用 Pigsty 部署 Dify
- 配置文件模板详解
- 数据库初始化步骤
- 容器编排配置
- HTTPS 证书配置

#### 11.2.3 生产环境优化
- 连接池配置
- 向量索引优化
- 监控指标设置
- 扩展性考虑

#### 11.2.4 实验：构建企业级 AI 应用
- 创建知识库
- 配置 Workflow
- 集成外部 API
- 性能调优

### 11.3 企业资源规划：Odoo

#### 11.3.1 Odoo ERP 系统介绍
- 模块化架构设计
- PostgreSQL 数据模型
- 多租户支持
- 性能要求分析

#### 11.3.2 Pigsty 一键部署 Odoo
- 数据库权限配置
- 初始化脚本执行
- 模块安装流程
- 反向代理配置

#### 11.3.3 企业级部署最佳实践
- 数据库分区策略
- 备份恢复方案
- 高并发优化
- 安全加固措施

#### 11.3.4 实验：搭建完整 ERP 环境
- 基础模块配置
- 工作流定制
- 报表系统搭建
- 数据迁移实践

### 11.4 代码托管平台：GitLab

#### 11.4.1 GitLab 数据库架构
- PostgreSQL 在 GitLab 中的角色
- Patroni 高可用方案
- PgBouncer 连接池
- Consul 服务发现

#### 11.4.2 使用 Pigsty 部署 GitLab
- 数据库集群配置
- GitLab Omnibus 安装
- 存储后端配置
- CI/CD Runner 集成

#### 11.4.3 性能与扩展性
- 数据库读写分离
- 缓存策略优化
- 大规模部署架构
- 监控告警设置

#### 11.4.4 实验：构建企业代码平台
- 项目组织结构
- CI/CD 流水线
- 代码审查流程
- 安全扫描集成

### 11.5 轻量级 Git 服务：Gitea

#### 11.5.1 Gitea 特性与优势
- 资源占用对比
- PostgreSQL 配置要求
- 安全认证选项
- 迁移工具支持

#### 11.5.2 Pigsty 快速部署 Gitea
- 最小化部署配置
- 数据库连接设置
- SSH 服务配置
- Web 界面定制

#### 11.5.3 生产环境配置
- SSL/TLS 证书配置
- 备份策略制定
- 性能参数调优
- 集成第三方服务

#### 11.5.4 实验：搭建团队 Git 服务
- 用户权限管理
- 仓库镜像同步
- Webhook 配置
- API 使用示例

### 11.6 现代化知识库：Wiki.js

#### 11.6.1 Wiki.js 3.0 架构演进
- PostgreSQL 独占支持的原因
- JSONB 数据存储
- 全文搜索实现
- 实时协作机制

#### 11.6.2 使用 Pigsty 部署 Wiki.js
- 数据库 Schema 创建
- Node.js 环境配置
- 存储引擎选择
- 认证提供商集成

#### 11.6.3 内容管理最佳实践
- 多语言支持配置
- 版本控制策略
- 搜索索引优化
- 媒体文件管理

#### 11.6.4 实验：构建企业知识管理系统
- 页面组织结构
- 权限体系设计
- 内容审核流程
- 数据导入导出

### 11.7 团队协作平台：Mattermost

#### 11.7.1 Mattermost 系统架构
- PostgreSQL 数据模型
- 消息存储策略
- 文件管理方案
- 插件系统设计

#### 11.7.2 Pigsty 部署 Mattermost
- 数据库初始化
- 集群模式配置
- ElasticSearch 集成
- 推送通知服务

#### 11.7.3 企业级功能配置
- SSO 单点登录
- 合规性设置
- 数据保留策略
- 审计日志配置

#### 11.7.4 实验：搭建企业即时通讯系统
- 团队和频道管理
- 机器人开发
- 工作流集成
- 移动端配置

### 11.8 社区论坛：Discourse

#### 11.8.1 Discourse 技术栈
- Ruby on Rails 与 PostgreSQL
- Redis 缓存架构
- Sidekiq 任务队列
- 全文搜索实现

#### 11.8.2 使用 Pigsty 部署 Discourse
- PostgreSQL 扩展配置
- Ruby 环境搭建
- 资源预编译
- CDN 集成配置

#### 11.8.3 社区运营功能
- 用户信任等级
- 内容审核机制
- SEO 优化配置
- 邮件通知系统

#### 11.8.4 实验：建立技术社区论坛
- 分类和标签设计
- 主题定制开发
- 插件安装配置
- 数据分析报表

### 11.9 联邦社交网络：Mastodon

#### 11.9.1 Mastodon 分布式架构
- ActivityPub 协议实现
- PostgreSQL 核心数据
- Redis 队列系统
- 媒体存储方案

#### 11.9.2 Pigsty 部署 Mastodon 实例
- 数据库连接池配置
- Sidekiq 工作进程
- Streaming API 设置
- 联邦网络配置

#### 11.9.3 实例运维管理
- 内容审核策略
- 实例封禁规则
- 存储空间管理
- 性能监控方案

#### 11.9.4 实验：搭建私有社交网络
- 实例初始化
- 用户迁移流程
- 自定义表情包
- 统计分析工具

### 11.10 其他企业应用

#### 11.10.1 低代码平台
- NocoDB：Airtable 开源替代
- Supabase：Firebase 替代方案
- Hasura：GraphQL 引擎

#### 11.10.2 API 网关与中间件
- Kong API Gateway 配置
- PostgREST 自动 API 生成
- FerretDB MongoDB 兼容层

#### 11.10.3 数据分析平台
- Metabase 商业智能
- Apache Superset 数据探索
- Redash 查询可视化

#### 11.10.4 专业应用
- TimescaleDB 时序数据库
- PostGIS 地理信息系统
- Citus 分布式扩展

### 11.11 架构模式与最佳实践

#### 11.11.1 微服务架构模式
- 数据库per服务模式
- Saga 分布式事务
- CQRS 读写分离
- API 组合模式

#### 11.11.2 高可用部署方案
- Patroni + etcd + HAProxy
- PgPool-II 负载均衡
- 流复制配置
- 自动故障转移

#### 11.11.3 性能优化策略
- 连接池优化（PgBouncer）
- 查询性能调优
- 索引策略设计
- 分区表应用

#### 11.11.4 安全加固措施
- SSL/TLS 证书配置
- 认证方法选择
- 行级安全（RLS）
- 审计日志配置

### 11.12 容器编排与自动化

#### 11.12.1 Docker Compose 模板
- 服务依赖管理
- 网络配置
- 卷挂载策略
- 环境变量管理

#### 11.12.2 Kubernetes 部署
- StatefulSet 配置
- PVC 持久化存储
- Service 暴露策略
- Operator 模式

#### 11.12.3 CI/CD 集成
- 自动化测试流程
- 数据库迁移脚本
- 蓝绿部署策略
- 回滚机制设计

#### 11.12.4 监控与告警
- Prometheus 指标采集
- Grafana 仪表盘
- 日志聚合分析
- 告警规则配置

## 动手实验清单

1. **实验 1**：使用 Pigsty 一键部署 Dify AI 平台
2. **实验 2**：搭建多模块 Odoo ERP 系统
3. **实验 3**：构建高可用 GitLab 代码平台
4. **实验 4**：快速部署轻量级 Gitea 服务
5. **实验 5**：创建企业 Wiki.js 知识库
6. **实验 6**：搭建 Mattermost 团队协作平台
7. **实验 7**：建立 Discourse 技术社区
8. **实验 8**：部署 Mastodon 联邦社交实例
9. **实验 9**：配置 Kong API 网关
10. **实验 10**：集成 Supabase 后端服务

## 学习目标

完成本章学习后，读者应该能够：

1. 理解企业软件选择 PostgreSQL 的技术和商业原因
2. 掌握使用 Pigsty 快速部署各类企业应用的方法
3. 了解不同应用的 PostgreSQL 使用模式和优化策略
4. 能够根据业务需求选择合适的开源软件方案
5. 掌握生产环境的部署、监控和维护最佳实践
6. 理解容器化部署和传统部署的权衡
7. 能够设计和实施高可用架构方案
8. 掌握故障排查和性能优化技巧

## 参考文献与资源

### Pigsty 官方资源

1. [Pigsty 官方文档](https://pigsty.io/docs/)
2. [Pigsty GitHub 仓库](https://github.com/pgsty/pigsty)
3. [Pigsty 软件模块文档](https://pigsty.io/docs/software/)
4. [Pigsty Docker 模块](https://pigsty.io/docs/docker/)
5. [Pigsty app.yml 部署指南](https://github.com/pgsty/pigsty/blob/main/app.yml)
6. [v3.3 版本发布：扩展 404，Odoo, Dify, Supabase](https://pigsty.io/blog/releases/v3.3.0/)
7. [使用 PG, PGVector 和 Pigsty 自托管 Dify](https://pigsty.io/blog/pg/dify-setup/)
8. [Dify: AI 工作流和 LLMOps](https://pigsty.io/docs/software/dify/)
9. [Odoo: 企业开源 ERP](https://pigsty.io/docs/software/odoo/)
10. [Pigsty 服务架构](https://pigsty.io/docs/about/service/)

### Dify 相关资源

11. [Dify 官方文档](https://docs.dify.ai/)
12. [Dify PostgreSQL 数据库配置](https://enterprise-docs.dify.ai/en-us/deployment/advanced-configuration/postgresql-database)
13. [Dify 本地源码启动指南](https://docs.dify.ai/en/getting-started/install-self-hosted/local-source-code)
14. [Dify 自托管部署](https://pigsty.io/docs/app/dify/)
15. [Dify 数据库客户端节点](https://marketplace.dify.ai/plugins/spance/db_client_node)
16. [如何部署本地 Dify 实现安全快速的 LLM 代理工作流](https://v4.riino.site/blog/2024-07-21-local-dify-101)
17. [Dify PostgreSQL 示例](https://www.restack.io/p/dify-answer-postgresql-example-cat-ai)
18. [Dify 连接数据库指南](https://www.restack.io/p/dify-answer-connect-to-database-cat-ai)

### Odoo 相关资源

19. [Odoo 18.0 源码安装文档](https://www.odoo.com/documentation/18.0/administration/on_premise/source.html)
20. [如何安装 Odoo ERP 和 CRM 平台](https://www.icdsoft.com/en/kb/view/1044_installing_odoo)
21. [集成 PostgreSQL 与 Odoo ERP 系统](https://www.w3resource.com/PostgreSQL/snippets/integrating-postgresql-with-odoo.php)
22. [Odoo 18.0 设置指南](https://www.odoo.com/documentation/18.0/developer/tutorials/setup_guide.html)
23. [安装 Odoo：平滑实施指南](https://www.cleverence.com/articles/odoo/installing-odoo-a-guide-to-smooth-implementation/)
24. [Odoo 系统配置](https://www.odoo.com/documentation/18.0/administration/on_premise/deploy.html)
25. [使用 Docker 在 Ubuntu 上安装 Odoo](https://www.digitalocean.com/community/tutorials/how-to-install-odoo-with-docker-on-ubuntu)
26. [Odoo 打包安装程序](https://www.odoo.com/documentation/18.0/administration/on_premise/packages.html)

### GitLab 相关资源

27. [GitLab 高可用角色](https://docs.gitlab.com/omnibus/roles/)
28. [GitLab PostgreSQL 扩展配置](https://docs.gitlab.com/administration/postgresql/)
29. [GitLab 数据库设置](https://docs.gitlab.com/omnibus/settings/database/)
30. [GitLab 参考架构](https://docs.gitlab.com/administration/reference_architectures/)
31. [GitLab PostgreSQL 复制和故障转移](https://docs.gitlab.com/ee/administration/postgresql/replication_and_failover.html)
32. [GitLab PostgreSQL 版本信息](https://docs.gitlab.com/administration/package_information/postgresql_versions/)
33. [GitLab 独立 PostgreSQL 数据库设置](https://docs.gitlab.com/charts/advanced/external-db/external-omnibus-psql/)
34. [GitLab 架构概览](https://docs.gitlab.com/ee/development/architecture.html)

### Gitea 相关资源

35. [使用 Gitea 和 PostgreSQL 设置自托管 Git 仓库](https://medium.com/@alkayedayat93/setting-up-a-self-hosted-git-repository-with-gitea-and-postgresql-07bcc5395a3f)
36. [Gitea 数据库准备](https://docs.gitea.com/next/installation/database-prep)
37. [Gitea 安装文档](https://docs.gitea.com/category/installation)
38. [Gitea ArchWiki](https://wiki.archlinux.org/title/Gitea)
39. [如何在 Ubuntu 服务器上设置 Gitea](https://bryangilbert.com/post/devops/how-to-setup-gitea-ubuntu/)
40. [在 Debian 11 上安装 Gitea 与 PostgreSQL](https://www.howtoforge.com/how-to-install-gitea-with-postgresql-on-debian-11/)
41. [Gitea 配置速查表](https://docs.gitea.com/administration/config-cheat-sheet)
42. [在 Ubuntu 18.04 上安装 Gitea 与 Nginx、PostgreSQL](https://luxagraf.net/src/gitea-nginx-postgresql-ubuntu-1804)

### Wiki.js 相关资源

43. [Wiki.js 3.0 - 全面采用 PostgreSQL](https://beta.js.wiki/blog/2021-wiki-js-3-going-full-postgresql)
44. [Wiki.js 官网](https://js.wiki/)
45. [Wiki.js 系统要求](https://docs.requarks.io/install/requirements)
46. [Wiki.js PostgreSQL 配置参考](https://github.com/requarks/wiki/discussions/3426)
47. [Wiki.js PostgreSQL 文档](https://docs.requarks.io/search/postgres)
48. [Wiki.js 配置指南](https://docs.requarks.io/install/config)
49. [在 Ubuntu 20.04 上安装 Wiki.js](https://www.vultr.com/docs/install-wiki-js-with-node-js-postgresql-and-nginx-on-ubuntu-20-04-lts/)
50. [在 Debian 10 上安装 Wiki.js 与 PostgreSQL](https://blog.eldernode.com/install-wiki-js-with-postgresql-on-debian/)
51. [在 Ubuntu 22.04 上安装 Wiki.js](https://www.howtoforge.com/how-to-install-wikijs-on-ubuntu-22-04/)

### Mattermost 相关资源

52. [Mattermost 与 pgEdge 合作提供超高可用性 PostgreSQL](https://mattermost.com/newsroom/press-releases/mattermost-and-pgedge-partner-to-deliver-ultra-high-availability-multi-master-postgresql-for-always-on-always-available-collaboration/)
53. [Mattermost GitHub 仓库](https://github.com/mattermost/mattermost)
54. [从 MySQL 手动迁移到 PostgreSQL](https://docs.mattermost.com/deployment-guide/manual-postgres-migration.html)
55. [Mattermost 协作平台](https://www.vpsserver.com/mattermost/)
56. [从 MySQL 到 PostgreSQL 的迁移指南](https://docs.mattermost.com/deployment-guide/postgres-migration.html)
57. [Mattermost 官网](https://mattermost.com/)
58. [自动化 PostgreSQL 迁移](https://docs.mattermost.com/deploy/postgres-migration-assist-tool.html)
59. [使用 Mattermost 提升团队协作](https://formable.app/mattermost/)

### Discourse 相关资源

60. [在 Ubuntu 18.04 上安装 Discourse（不使用 Docker）](https://www.linuxbabe.com/ubuntu/install-discourse-ubuntu-18-04-server-without-docker)
61. [Discourse database.yml 配置](https://github.com/discourse/discourse/blob/main/config/database.yml)
62. [配置 Discourse 使用独立 PostgreSQL 服务器](https://meta.discourse.org/t/configure-discourse-to-use-a-separate-postgresql-server/46375)
63. [Discourse Rails database.yml 生产配置](https://discuss.rubyonrails.org/t/discourse-rails-database-yml-for-production/76898)
64. [使用 Docker 运行 Discourse 与 PostgreSQL](https://meta.discourse.org/t/running-discourse-with-postgres-running-in-docker/216803)
65. [如何在自己的服务器上托管 Discourse 论坛](https://www.xltoolbox.net/blog/2016/10/how-to-host-a-discourse-forum-on-your-own-server.html)
66. [在 Ubuntu 18.04 上安装 Discourse 论坛](https://www.howtoforge.com/how-to-install-discourse-forum-on-ubuntu-1804/)
67. [Discourse 不使用 Docker 部署](https://bcarlin.net/blog/discourse-without-docker.html)

### Mastodon 相关资源

68. [使用 Mastodon 和 Exoscale 托管自己的社交网络](https://www.exoscale.com/syslog/mastodon/)
69. [Mastodon 维基百科](https://en.wikipedia.org/wiki/Mastodon_(social_network))
70. [Mastodon 的架构](https://softwaremill.com/the-architecture-of-mastodon/)
71. [使用 Instaclustr 创建 Mastodon 服务器](https://www.instaclustr.com/blog/create-a-mastodon-server-with-instaclustr/)
72. [在自管理 VPS 上设置 Mastodon](https://docs.20i.com/virtual-private-servers/how-set-up-mastodon-on-a-self-managed-vps)
73. [PostgreSQL Wiki：社交网络服务生态系统](https://wiki.postgresql.org/wiki/Ecosystem:Social_networking_service_(SNS))
74. [Mastodon GitHub 仓库](https://github.com/mastodon/mastodon)
75. [使用远程 PostgreSQL 数据库设置 Mastodon](https://discourse.joinmastodon.org/t/setup-of-mastodon-with-remote-postgresql-database/1900)
76. [在 Ubuntu 上安装 Mastodon 社区](https://www.scaleway.com/en/docs/tutorials/mastodon-community/)
77. [如何扩展你的 Mastodon 服务器](https://www.digitalocean.com/community/tutorials/how-to-scale-your-mastodon-server)

### PostgreSQL 高可用与性能

78. [PostgreSQL 高可用架构：Patroni HAProxy](https://medium.com/@c.ucanefe/patroni-ha-proxy-feed1292d23f)
79. [使用 Patroni 实现 PostgreSQL 高可用](https://docs.percona.com/postgresql/17/solutions/high-availability.html)
80. [使用 Patroni 和 HAProxy 的高可用 PostgreSQL 集群](https://jfrog.com/community/devops/highly-available-postgresql-cluster-using-patroni-and-haproxy/)
81. [Patroni GitHub 仓库](https://github.com/patroni/patroni)
82. [PostgreSQL 高可用：Patroni 和 Pgpool-II](https://medium.com/@joaovic32/demystifying-high-availability-postgresql-with-patroni-and-pgpool-ii-on-ubuntu-428c91a55b1a)
83. [配置 PostgreSQL HA 与 Patroni 的分步指南](https://bootvar.com/how-to-configure-postgresql-ha-with-patroni/)
84. [使用 Patroni、PGBouncer、Docker、Consul 和 HAProxy 设置高可用 PostgreSQL](https://medium.com/@nicola.vitaly/setting-up-high-availability-postgresql-cluster-using-patroni-pgbouncer-docker-consul-and-95c70445b1b1)
85. [使用 Patroni、etcd、PGBouncer 和 HAProxy 实现 PostgreSQL 高可用](https://theamitdixit.wordpress.com/2024/02/17/achieving-high-availabilityha-in-postgresql-with-patroni-etcd-pgbouncer-and-haproxy/)

### 连接池与优化

86. [PostgreSQL 连接池：PgBouncer](https://scalegrid.io/blog/postgresql-connection-pooling-part-2-pgbouncer/)
87. [使用 PgBouncer 提升性能和减少 PostgreSQL 负载](https://medium.com/@dmitry.romanoff/using-pgbouncer-to-improve-performance-and-reduce-the-load-on-postgresql-b54b78deb425)
88. [PgBouncer 如何解决企业性能瓶颈](https://www.percona.com/blog/pgbouncer-for-postgresql-how-connection-pooling-solves-enterprise-slowdowns/)
89. [使用连接池提升数据库性能](https://stackoverflow.blog/2020/10/14/improve-database-performance-with-connection-pooling/)
90. [高级 PostgreSQL 连接池使用 PgBouncer](https://dzone.com/articles/advanced-postgres-connection-pooling-using-pgbounc)
91. [PgBouncer vs Pgpool-II](https://scalegrid.io/blog/postgresql-connection-pooling-part-4-pgbouncer-vs-pgpool/)
92. [PgBouncer：PostgreSQL 连接池简单指南](https://gxara.medium.com/pgbouncer-a-simple-guide-for-postgresql-connection-pooling-34bb4ad05736)
93. [PgBouncer 连接池类型](https://www.cybertec-postgresql.com/en/pgbouncer-types-of-postgresql-connection-pooling/)
94. [Azure PostgreSQL 连接池最佳实践](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-connection-pooling-best-practices)
95. [PgBouncer 教程：安装、配置和测试](https://www.enterprisedb.com/blog/pgbouncer-tutorial-installing-configuring-and-testing-persistent-postgresql-connection-pooling)

### 备份恢复与 PITR

96. [PostgreSQL 8.1：在线备份和时间点恢复](https://www.postgresql.org/docs/8.1/backup-online.html)
97. [PostgreSQL 时间点恢复（PITR）](https://www.pgedge.com/blog/point-in-time-recovery-pitr-in-postgresql)
98. [PostgreSQL 17：连续归档和 PITR](https://www.postgresql.org/docs/current/continuous-archiving.html)
99. [使用 PITR 的备份和恢复](https://wiki.postgresql.org/images/c/ce/PGCONF-PITR_Mark_Jones_2015-10-28.pdf)
100. [Google Cloud SQL PostgreSQL PITR](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
101. [Azure PostgreSQL 备份和恢复](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore)
102. [PostgreSQL 数据库备份和灾难恢复](https://www.tigerdata.com/blog/database-backups-and-disaster-recovery-in-postgresql-your-questions-answered)
103. [PostgreSQL 企业级环境备份策略](https://www.percona.com/blog/postgresql-backup-strategy-enterprise-grade-environment/)

### 监控与性能调优

104. [使用 Prometheus 和 Grafana 监控 PostgreSQL 完整指南](https://rezakhademix.medium.com/a-complete-guide-to-monitor-postgresql-with-prometheus-and-grafana-5611af229882)
105. [使用 Prometheus 和 Grafana 监控 PostgreSQL](https://www.ashnik.com/monitoring-postgresql-with-prometheus-and-grafana/)
106. [配置 PostgreSQL exporter 生成 Prometheus 指标](https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/enable-prom-metrics-collection/data-stores/postgresql/)
107. [PostgreSQL 教程：使用 Prometheus 和 Grafana 监控](https://www.rockdata.net/tutorial/monitor-with-prometheus-and-grafana/)
108. [在 Kubernetes 上监控 PostgreSQL 集群](https://medium.com/@dinhnguyen1812/monitoring-a-postgresql-cluster-on-kubernetes-with-prometheus-and-grafana-a9a69ec36f53)
109. [PostgreSQL 数据库 Grafana 仪表板](https://grafana.com/grafana/dashboards/9628-postgresql-database/)
110. [PostgreSQL 监控的关键指标](https://www.sysdig.com/blog/postgresql-monitoring)
111. [使用 Prometheus 和 Grafana 监控 PostgreSQL 服务器](https://computingforgeeks.com/monitor-postgresql-with-prometheus-grafana/)
112. [在 Docker 中使用 Grafana 和 Prometheus 监控 PostgreSQL](https://medium.com/@murat.bilal/monitoring-postgresql-with-grafana-and-prometheus-in-docker-7fe6a36ef7b1)

### 性能调优参数

113. [PostgreSQL 数据库参数和配置调优综合指南](https://www.enterprisedb.com/postgres-tutorials/comprehensive-guide-how-tune-database-parameters-and-configuration-postgresql)
114. [PostgreSQL 性能调优最佳实践 2025](https://www.mydbops.com/blog/postgresql-parameter-tuning-best-practices)
115. [PostgreSQL 性能调优：关键参数](https://www.tigerdata.com/learn/postgresql-performance-tuning-key-parameters)
116. [PostgreSQL 性能调优：优化数据库服务器](https://www.enterprisedb.com/postgres-tutorials/introduction-postgresql-performance-tuning-and-optimization)
117. [PostgreSQL 配置参数：性能调优最佳实践](https://dbadataverse.com/tech/postgresql/2025/02/postgresql-configuration-parameters-best-practices-for-performance-tuning)
118. [PostgreSQL 基准测试：通过调优优化数据库性能](https://www.enterprisedb.com/blog/postgresql-performance-optimizing-tuning-database-configurations-parameters-benchmark)
119. [调优 PostgreSQL 性能（最重要的设置）](https://bun.uptrace.dev/postgres/performance-tuning.html)
120. [PostgreSQL 性能调优指南：影响性能的设置](https://www.percona.com/blog/tuning-postgresql-database-parameters-to-optimize-performance/)
121. [调优你的 PostgreSQL 服务器](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)
122. [PostgreSQL 性能调优设置](https://vladmihalcea.com/postgresql-performance-tuning-settings/)

### 安全配置

123. [PostgreSQL 17：使用 SSL 的安全 TCP/IP 连接](https://www.postgresql.org/docs/current/ssl-tcp.html)
124. [为 PostgreSQL 设置 SSL 认证](https://www.cybertec-postgresql.com/en/setting-up-ssl-authentication-for-postgresql/)
125. [配置 SSL/TLS 证书](https://cloud.google.com/sql/docs/postgres/configure-ssl-instance)
126. [配置 PostgreSQL 服务器和客户端使用 SSL 证书认证](https://www.bastionxp.com/blog/configure-postgresql-database-server-client-ssl-certificate-mutual-tls/)
127. [PostgreSQL SSL 认证：分步指南](https://goteleport.com/learn/postgresql-ssl-authentication-guide/)
128. [PostgreSQL Docker 容器的证书认证方案](https://www.crunchydata.com/blog/ssl-certificate-authentication-postgresql-docker-containers)
129. [为 PostgreSQL 数据库创建和安装 SSL 证书](https://luppeng.wordpress.com/2021/08/07/create-and-install-ssl-certificates-for-postgresql-database-running-locally/)
130. [启用和强制 PostgreSQL 连接的 SSL/TLS](https://www.percona.com/blog/enabling-and-enforcing-ssl-tls-for-postgresql-connections/)

### 容器化与编排

131. [使用 Docker Swarm 和 Kubernetes 部署可扩展的 PostgreSQL 集群](https://pankajconnect.medium.com/deploying-scalable-postgresql-clusters-with-docker-swarm-and-kubernetes-8e20d6eef703)
132. [Docker Swarm 容器编排](https://juliensalinas.com/container-orchestration-docker-swarm-nlpcloud/)
133. [使用 Docker Swarm 创建 PostgreSQL 集群的简单方案](https://www.crunchydata.com/blog/an-easy-recipe-for-creating-a-postgresql-cluster-with-docker-swarm)
134. [Mirantis Swarm](https://www.mirantis.com/software/swarm/)
135. [Docker Swarm 如何处理 PostgreSQL 复制](https://forums.docker.com/t/how-does-docker-swarm-handle-database-postgresql-replication/24330)
136. [Portainer：Kubernetes、Docker 和 Podman 容器管理平台](https://www.portainer.io/)
137. [Docker Swarm vs Kubernetes：如何选择容器编排工具](https://circleci.com/blog/docker-swarm-vs-kubernetes/)
138. [部署和编排](https://docs.docker.com/get-started/orchestration/)
139. [2025 年 16 个最有用的容器编排工具](https://spacelift.io/blog/container-orchestration-tools)
140. [Kubernetes vs Docker Swarm：比较容器编排工具](https://www.bmc.com/blogs/kubernetes-vs-docker-swarm/)

### Docker Compose 示例

141. [PostgreSQL Docker 示例](https://docs.docker.com/reference/samples/postgres/)
142. [Docker：如何使用 Docker Compose 安装 PostgreSQL](https://medium.com/@agusmahari/docker-how-to-install-postgresql-using-docker-compose-d646c793f216)
143. [如何使用 PostgreSQL Docker 官方镜像](https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/)
144. [使用 Docker 和 Docker Compose 的 PostgreSQL 分步指南](https://geshan.com.np/blog/2021/12/docker-postgres/)
145. [在 docker-compose.yml 文件中创建 PostgreSQL 数据库](https://stackoverflow.com/questions/75246059/create-a-postgres-database-within-a-docker-compose-yml-file)
146. [compose-postgres GitHub 仓库](https://github.com/khezen/compose-postgres/blob/master/docker-compose.yml)
147. [Docker Awesome Compose](https://github.com/docker/awesome-compose)
148. [使用 Docker 和 Docker Compose 部署 PostgreSQL](https://dev.to/geoff89/how-to-deploy-postgresql-with-docker-and-docker-compose-3lj3)
149. [docker-node-postgres-template](https://github.com/alexeagleson/docker-node-postgres-template/blob/master/docker-compose.yml)
150. [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)

### 企业应用集成模式

151. [微服务模式：微服务架构](https://microservices.io/patterns/microservices.html)
152. [PostgreSQL 在微服务架构中的应用](https://reintech.io/blog/postgresql-microservices-architecture)
153. [微服务模式：数据库per服务](https://microservices.io/patterns/data/database-per-service.html)
154. [使用 Kubernetes、Postgres 和 CloudNativePG 最大化微服务数据库](https://www.gabrielebartolini.it/articles/2024/02/maximizing-microservice-databases-with-kubernetes-postgres-and-cloudnativepg/)
155. [微服务部署架构和模式](https://www.osohq.com/learn/microservices-deployment)
156. [什么是微服务？](https://microservices.io/)
157. [微服务设计模式完整指南](https://www.openlegacy.com/blog/microservices-architecture-patterns/)
158. [微服务架构中的数据库设计](https://www.baeldung.com/cs/microservices-db-design)
159. [数据库per服务模式](https://medium.com/design-microservices-architecture-with-patterns/the-database-per-service-pattern-9d511b882425)
160. [提升可用性的 4 种微服务部署模式](https://www.opslevel.com/resources/4-microservice-deployment-patterns-that-improve-availability)

### 企业级 PostgreSQL 部署

161. [设置和部署 PostgreSQL 数据库服务器](https://medium.com/@deepankaracharyya/set-and-deploy-a-postgresql-database-server-within-minutes-a2c649f249ea)
162. [集成 PostgreSQL 第一部分：应用集成](https://www.enterprisedb.com/blog/integrating-postgresql-part-1-application-integration)
163. [Azure PostgreSQL 文档](https://learn.microsoft.com/en-us/azure/postgresql/single-server/application-best-practices)
164. [PostgreSQL 企业商业应用](https://wiki.postgresql.org/wiki/PostgreSQL_for_Enterprise_Business_Applications)
165. [PostgreSQL 托管：5 种部署选项](https://www.instaclustr.com/education/postgresql/postgres-hosting-5-deployment-options-and-how-to-choose/)
166. [为什么企业选择 PostgreSQL](https://www.percona.com/blog/why-postgresql-is-a-top-choice-for-enterprise-level-databases/)
167. [PostgreSQL 生产部署十大技巧](https://severalnines.com/blog/ten-tips-going-production-postgresql/)
168. [PostgreSQL 官网](https://www.postgresql.org/)
169. [PostgreSQL 开发者：用最佳实践替代猜测](https://www.enterprisedb.com/blog/postgres-developers-replace-best-guesses-best-practices)
170. [Google Cloud SQL PostgreSQL 最佳实践](https://cloud.google.com/sql/docs/postgres/best-practices)

### Supabase 相关资源

171. [Supabase Docker 自托管](https://supabase.com/docs/guides/self-hosting/docker)
172. [Supabase 自托管指南](https://supabase.com/docs/guides/self-hosting)
173. [在 PostgreSQL 上自托管 Supabase](https://pigsty.io/blog/db/supabase/)
174. [使用外部 PostgreSQL 的自托管 Supabase](https://dev.to/arthurkay/self-hosted-supabase-with-external-postgresql-apd)
175. [如何在自己的计算机上自托管 Supabase（完整指南）](https://medium.com/@christopher.mathews/how-to-self-host-supabase-on-your-own-computer-full-guide-cceac9b740ea)
176. [Supabase 架构](https://supabase.com/docs/guides/getting-started/architecture)
177. [Supabase 自托管部署](https://medium.com/@igor.mytyuk/supabase-self-hosted-deploy-475718fe906f)
178. [连接到 Supabase 数据库](https://supabase.com/docs/guides/database/connecting-to-postgres)
179. [为自托管部署创建多个组织和项目](https://github.com/orgs/supabase/discussions/4907)
180. [Supabase：使用 Docker 自托管的分步指南](https://medium.com/@18bmiit080/supabase-a-step-by-step-guide-for-self-hosting-with-docker-20f02f2b6647)

### 其他开源应用

181. [FerretDB GitHub 仓库](https://github.com/FerretDB/FerretDB)
182. [FerretDB 官网](https://www.ferretdb.com/)
183. [如何使用 MongoDB 客户端和 FerretDB 与 Instaclustr PostgreSQL](https://www.instaclustr.com/blog/ferretdb-with-postgresql/)
184. [NoSQL Postgres：使用 FerretDB 为 Supabase 添加 MongoDB 兼容性](https://supabase.com/blog/nosql-mongodb-compatibility-with-ferretdb-and-flydotio)
185. [FerretDB 介绍](https://docs.ferretdb.io/)
186. [FerretDB 2.0：使用 PostgreSQL 的开源 MongoDB](https://thenewstack.io/ferretdb-2-0-open-source-mongodb-alternative-with-postgresql-power/)
187. [使用 PostgreSQL 作为数据库引擎安装 FerretDB](https://dincosman.com/2024/05/14/ferretdb-installation/)
188. [FerretDB 2.0 发布：更快、更兼容的 MongoDB 替代](https://blog.ferretdb.io/ferretdb-releases-v2-faster-more-compatible-mongodb-alternative/)

189. [PostgreSQL 的 6 个最佳无代码工具](https://medium.com/@nocobase/6-best-no-code-tools-for-postgresql-a91423140ad4)
190. [NocoDB Cloud](https://nocodb.com/)
191. [PostgreSQL 和 NocoDB 集成](https://latenode.com/integrations/postgresql/nocodb)
192. [Baserow：无代码开源数据库和应用构建器](https://baserow.io/)
193. [NocoDB 文档](https://docs.nocodb.com/)
194. [NocoDB GitHub 仓库](https://github.com/nocodb/nocodb)
195. [在 DigitalOcean 上开始使用 NocoDB](https://www.digitalocean.com/community/developer-center/getting-started-with-nocodb-on-digitalocean)

196. [Kong 网关设置数据存储](https://docs.konghq.com/gateway/latest/install/post-install/set-up-data-store/)
197. [Kong API 网关安装指南](https://vasista.medium.com/kong-api-gateway-installation-guide-for-beginners-ab6c796b36bf)
198. [Kong API 网关：从零到生产](https://medium.com/swlh/kong-api-gateway-zero-to-production-5b8431495ee)
199. [Kong Gateway Docker 镜像](https://hub.docker.com/r/kong/kong-gateway)
200. [Kong PostgreSQL TLS 配置参考](https://docs.konghq.com/gateway/latest/production/networking/configure-postgres-tls/)

201. [Hasura GraphQL 引擎 GitHub 仓库](https://github.com/hasura/graphql-engine)
202. [如何为基于 PostgreSQL 的应用安装 Hasura GraphQL 引擎](https://www.virtuozzo.com/company/blog/hasura-graphql-postgresql/)
203. [Hasura 生产检查清单](https://hasura.io/docs/2.0/deployment/production-checklist/)
204. [配置 Hasura GraphQL 引擎的不同方法](https://accuweb.cloud/resource/articles/hasura-graphql-engine)
205. [在 PostgreSQL 上创建 GraphQL API（2分钟）](https://hasura.io/graphql/database/postgresql)
206. [Hasura 部署指南](https://hasura.io/docs/2.0/deployment/deployment-guides/index/)

207. [TimescaleDB GitHub 仓库](https://github.com/timescale/timescaledb)
208. [如何在现有 PostgreSQL 数据库上启用 TimescaleDB](https://severalnines.com/blog/how-enable-timescaledb-existing-postgresql-database/)
209. [PostgreSQL 时序数据库插件 TimescaleDB 部署实践](https://alibaba-cloud.medium.com/postgresql-time-series-database-plug-in-timescaledb-deployment-practices-6a07e246eb0d)
210. [使用 TimescaleDB 管理时序数据](https://www.percona.com/blog/managing-time-series-data-using-timescaledb-powered-postgresql/)

### Vonng 博客资源

211. [Vonng 官网](https://vonng.com/)
212. [Vonng 英文博客](https://vonng.com/en/)
213. [数据库在 Kubernetes 中：这是个好主意吗？](https://vonng.com/cn/blog/en/db-in-k8s/)
214. [在 PostgreSQL 上自托管 Supabase](https://blog.vonng.com/en/pg/supabase/)
215. [Pigsty 主页](https://db.vonng.com/)
216. [Vonng - Pigsty 博客](https://blog.vonng.com/en/)
217. [PGSQL x Pigsty：数据库全能王](http://vonng.com/cn/blog/db/pgsql-x-pigsty/)
218. [设计数据密集型应用（第二版）](http://ddia.vonng.com/v2/)
219. [PostgreSQL 专家](https://bk.vonng.com/en/)
220. [PostgreSQL 技术内幕](https://pgint.vonng.com/)

## 总结

本章介绍了如何使用 Pigsty 快速部署各种基于 PostgreSQL 的企业级应用。通过学习这些内容，读者可以了解到：

1. PostgreSQL 作为开源数据库在企业应用中的核心地位
2. Pigsty 如何简化复杂应用的部署流程
3. 各种应用的架构特点和最佳实践
4. 生产环境的高可用、性能优化和安全配置
5. 容器化部署和传统部署的选择考虑

这些知识将帮助读者在实际工作中快速搭建各种企业应用，并确保其稳定、高效地运行。通过动手实验，读者可以深入理解每个应用的部署细节和运维要点，为构建企业级 PostgreSQL 应用生态打下坚实基础。