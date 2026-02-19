---
title: "7. 追本溯源：执行计划与统计信息"
weight: 700
math: true
breadcrumbs: false
---

> [!Warn] 本章为 AI 生成的头脑风暴草稿目录，尚未编写，请务必注意。

## 章节大纲

### 一、监控基础概念
#### 1.1 为什么需要监控
- 预防性维护：及时发现性能瓶颈，防止系统崩溃
- 资源优化：了解资源使用情况，优化硬件和软件配置
- 业务连续性：确保数据库高性能支持更多并发用户
- 问题诊断：快速定位和解决数据库问题
- 容量规划：基于历史数据预测未来需求

#### 1.2 监控的层次架构
- 基础设施层：CPU、内存、磁盘、网络
- 操作系统层：进程、文件系统、内核参数
- 数据库层：连接、事务、锁、查询
- 应用层：业务指标、用户体验

#### 1.3 黄金监控指标
- 错误率（Errors）：数据库错误和失败率
- 延迟（Latency）：查询响应时间
- 吞吐量（Throughput）：QPS、TPS
- 饱和度（Saturation）：资源使用率

### 二、PostgreSQL 内置监控体系
#### 2.1 累积统计系统（Cumulative Statistics System）
- pg_stat_database：数据库级统计
- pg_stat_user_tables：表级统计
- pg_stat_user_indexes：索引使用统计
- pg_stat_bgwriter：后台写进程统计
- pg_stat_archiver：归档进程统计
- pg_stat_replication：复制统计

#### 2.2 动态统计视图
- pg_stat_activity：当前活动会话
- pg_locks：锁信息
- pg_stat_progress_*：进度监控视图

#### 2.3 pg_stat_statements 扩展
- 安装和配置
- 查询性能统计
- Top SQL 分析
- 查询优化建议

### 三、监控工具生态系统
#### 3.1 命令行工具
- pg_top：类似 top 的 PostgreSQL 监控工具
- pg_activity：类似 htop 的活动监控
- pgcenter：综合监控工具
- pgBadger：日志分析工具

#### 3.2 开源监控方案
- Prometheus + Grafana 监控栈
  - postgres_exporter 配置
  - 预构建仪表板
  - 告警规则设置
- pgwatch2：自包含监控解决方案
- pgMonitor：Crunchy Data 监控套件
- Zabbix/Nagios/Icinga 集成

#### 3.3 商业监控产品
- pganalyze：SaaS 监控与调优
- pgDash：综合监控仪表板
- DataDog/New Relic/Dynatrace APM
- 云厂商监控（AWS CloudWatch、Azure Monitor、GCP Monitoring）

#### 3.4 专用监控工具
- pgAudit：审计日志
- pgHero：性能洞察
- PoWA：工作负载分析器

### 四、关键指标详解
#### 4.1 连接和会话监控
- 活动连接数与最大连接数
- 连接池监控（PgBouncer/Pgpool-II）
- 空闲会话与长事务
- 等待事件分析

#### 4.2 查询性能监控
- 慢查询识别与分析
- 查询计划监控
- 缓存命中率
- 临时文件使用

#### 4.3 存储和I/O监控
- 表膨胀（Bloat）监控
- VACUUM 和 AUTOVACUUM 监控
- WAL 生成速率
- 磁盘I/O性能

#### 4.4 复制和高可用监控
- 复制延迟
- 复制槽状态
- 恢复冲突
- 故障切换就绪状态

### 五、监控最佳实践
#### 5.1 指标采集策略
- 采集频率设置
- 数据保留策略
- 采样与聚合

#### 5.2 告警设计
- 分级告警策略
- 动态阈值 vs 静态阈值
- 告警降噪与聚合
- 告警路由与升级

#### 5.3 可视化设计
- 仪表板层次结构
- 关键指标展示
- 钻取式分析
- 实时与历史数据对比

### 六、容器和云原生监控
#### 6.1 Kubernetes 环境监控
- Operator 监控集成
- Service Mesh 观测性
- Pod 和容器指标

#### 6.2 OpenTelemetry 集成
- 分布式追踪
- 指标、日志、追踪统一
- 跨服务关联分析

#### 6.3 云平台集成
- AWS RDS 监控
- Azure Database for PostgreSQL
- Google Cloud SQL

### 七、高级监控主题
#### 7.1 实时变更数据捕获（CDC）
- Debezium 集成
- 实时数据流监控
- 事件驱动架构

#### 7.2 日志管理与分析
- ELK Stack 集成
- 结构化日志
- 日志聚合与搜索

#### 7.3 性能基线与趋势分析
- 建立性能基线
- 异常检测
- 容量预测

### 八、动手实验
#### 实验1：搭建 Prometheus + Grafana 监控系统
- 安装配置 postgres_exporter
- 导入仪表板模板
- 配置告警规则

#### 实验2：使用 pg_stat_statements 分析慢查询
- 识别 Top SQL
- 分析执行计划
- 优化建议实施

#### 实验3：配置审计日志
- 安装 pgAudit
- 配置审计策略
- 日志分析与合规报告

#### 实验4：容器环境监控
- Docker 环境监控配置
- Kubernetes Operator 监控
- 分布式追踪实践

## 参考资料

### 官方文档
1. [PostgreSQL: Documentation - Chapter 27. Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html)
2. [PostgreSQL: Documentation - The Cumulative Statistics System](https://www.postgresql.org/docs/current/monitoring-stats.html)
3. [PostgreSQL: Documentation - pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
4. [PostgreSQL: Documentation - VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html)
5. [PostgreSQL: Documentation - Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
6. [PostgreSQL: Documentation - Automatic Vacuuming](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html)
7. [PostgreSQL Wiki - Monitoring](https://wiki.postgresql.org/wiki/Monitoring)
8. [PostgreSQL Wiki - Performance Analysis Tools](https://wiki.postgresql.org/wiki/Performance_Analysis_Tools)

### Vonng.com 博客文章
9. [pg_stat_statements 宏观查询优化](http://vonng.com/cn/blog/db/pgss/)
10. [PostgreSQL 到底有多强？](https://vonng.com/cn/blog/db/pg-performence/)
11. [Cloudflare是如何用15个PG集群支持55M QPS](https://vonng.com/cn/blog/db/pg-scalability/)
12. [PostgreSQL规约（PG16）](https://vonng.com/cn/blog/db/pg-convention/)
13. [PostgreSQL：最成功的数据库](https://vonng.com/cn/blog/db/pg-is-no1/)
14. [为什么PostgreSQL前途无量？](http://vonng.com/cn/blog/db/pg-is-great/)
15. [Pigsty Documentation](https://vonng.com/)
16. [PGSQL x Pigsty: 数据库全能王](http://vonng.com/cn/blog/db/pgsql-x-pigsty/)

### 监控工具和项目
17. [prometheus-community/postgres_exporter](https://github.com/prometheus-community/postgres_exporter)
18. [lesovsky/pgscv - Multi-purpose monitoring agent](https://github.com/lesovsky/pgscv)
19. [pgsty/pg_exporter - Advanced PostgreSQL Metrics Exporter](https://github.com/pgsty/pg_exporter)
20. [CrunchyData/pgmonitor - PostgreSQL Monitoring Resources](https://github.com/CrunchyData/pgmonitor)
21. [coroot/coroot-pg-agent - Query performance statistics](https://github.com/coroot/coroot-pg-agent)
22. [cybertec-postgresql/pgwatch2 - PostgreSQL metrics monitor](https://github.com/cybertec-postgresql/pgwatch2)
23. [dalibo/pg_activity - Top like application for PostgreSQL](https://github.com/dalibo/pg_activity)
24. [darold/pgbadger - PostgreSQL Log Analyzer](https://github.com/darold/pgbadger)
25. [daamien/PostgreSQL-Dashboard - Real-time monitoring screen](https://github.com/daamien/PostgreSQL-Dashboard)
26. [percona/pg_stat_monitor - Query Performance Monitoring](https://github.com/percona/pg_stat_monitor)

### 监控最佳实践
27. [PostgreSQL Monitoring: Key Metrics, Best Practices & Top Tools - Middleware](https://middleware.io/blog/postgresql-monitoring/)
28. [PostgreSQL Monitoring: A Complete Guide - TheDBAdmin](https://thedbadmin.com/blog/postgresql-monitoring)
29. [Top 10 PostgreSQL Monitoring Tools Guide - SigNoz](https://signoz.io/comparisons/postgresql-monitoring-tools/)
30. [PostgreSQL Monitoring Tools - Better Stack](https://betterstack.com/community/comparisons/postgresql-monitoring-tools/)
31. [PostgreSQL monitoring & alerting: Best practices - DrDroid](https://drdroid.io/engineering-tools/postgresql-monitoring-alerting-best-practices)
32. [How to Improve PostgreSQL Monitoring with PMM - Percona](https://learn.percona.com/how-to-improve-postgresql-monitoring-and-observability-with-pmm)
33. [5 Ways to Monitor Your PostgreSQL Database - TigerData](https://www.tigerdata.com/learn/5-ways-to-monitor-your-postgresql-database)
34. [Collecting metrics with PostgreSQL monitoring tools - Datadog](https://www.datadoghq.com/blog/postgresql-monitoring-tools/)

### Prometheus 和 Grafana
35. [Complete Guide To Monitor PostgreSQL With Prometheus and Grafana - Medium](https://rezakhademix.medium.com/a-complete-guide-to-monitor-postgresql-with-prometheus-and-grafana-5611af229882)
36. [PostgreSQL Tutorial: Monitoring with Prometheus and Grafana - Redrock](https://www.rockdata.net/tutorial/monitor-with-prometheus-and-grafana/)
37. [Monitoring PostgreSQL With Prometheus And Grafana - Ashnik](https://www.ashnik.com/monitoring-postgresql-with-prometheus-and-grafana/)
38. [Monitor PostgreSQL with Prometheus and Grafana on Ubuntu - HowtoForge](https://www.howtoforge.com/how-to-monitor-postgresql-with-prometheus-and-grafana/)
39. [Monitor PostgreSQL Server With Prometheus and Grafana - ComputingForGeeks](https://computingforgeeks.com/monitor-postgresql-with-prometheus-grafana/)
40. [Configure PostgreSQL exporter for Prometheus - Grafana Cloud](https://grafana.com/docs/grafana-cloud/monitor-applications/asserts/enable-prom-metrics-collection/data-stores/postgresql/)
41. [Monitoring PostgreSQL on Kubernetes with Prometheus & Grafana - Medium](https://medium.com/@dinhnguyen1812/monitoring-a-postgresql-cluster-on-kubernetes-with-prometheus-and-grafana-a9a69ec36f53)
42. [PostgreSQL monitoring made easy - Grafana Labs](https://grafana.com/solutions/postgresql/monitor/)

### pg_stat_statements 和性能分析
43. [pg_stat_monitor Documentation - Percona](https://docs.percona.com/pg-stat-monitor/)
44. [Monitoring PostgreSQL Performance with pg_stat_statements - DataSentinel](https://blog.datasentinel.io/post/pg_stats_statements/)
45. [PostgreSQL Performance Tuning with pg_stat_statements - Medium](https://medium.com/@amareswer/postgresql-performance-tuning-with-pg-stat-statements-5f849c3d49ab)
46. [Enhancing PostgreSQL Performance Monitoring with pg_stat_statements - Stormatics](https://stormatics.tech/blogs/enhancing-postgresql-performance-monitoring-a-comprehensive-guide-to-pg_stat_statements)

### 审计和安全监控
47. [PostgreSQL Audit Extension - PGAudit](https://www.pgaudit.org/)
48. [Audit for PostgreSQL using pgAudit - Google Cloud](https://cloud.google.com/sql/docs/postgres/pg-audit)
49. [Auditing PostgreSQL Using PgAudit - ScaleGrid](https://scalegrid.io/blog/auditing-postgresql-using-pgaudit/)
50. [What Is Audit Logging in PostgreSQL - TigerData](https://www.tigerdata.com/learn/what-is-audit-logging-and-how-to-enable-it-in-postgresql)
51. [Using pgAudit to log database activity - AWS RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.pgaudit.html)
52. [3 Postgres Audit Methods: How to Choose - Satori](https://satoricyber.com/postgres-security/postgres-audit/)
53. [PostgreSQL Insider - Detecting database security threats](https://www.postgresql.fastware.com/postgresql-insider-sec-threat)

### VACUUM 和 Autovacuum
54. [PostgreSQL VACUUM Guide and Best Practices - EDB](https://www.enterprisedb.com/blog/postgresql-vacuum-and-analyze-best-practice-tips)
55. [Visualizing & Tuning Postgres Autovacuum - pganalyze](https://pganalyze.com/blog/visualizing-and-tuning-postgres-autovacuum)
56. [Vacuuming and analyzing tables automatically - AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/postgresql-maintenance-rds-aurora/autovacuum.html)
57. [PostgreSQL VACUUM, AUTOVACUUM and ANALYZE Processes - MSSQLTips](https://www.mssqltips.com/sqlservertip/8150/postgresql-vacuum-autovacuum-analyze-processes/)
58. [Essential Guide to the PostgreSQL VACUUM Command - Percona](https://www.percona.com/blog/postgresql-vacuuming-to-optimize-database-performance-and-reclaim-space/)
59. [Autovacuum tuning - Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-autovacuum-tuning)

### 告警和阈值设置
60. [PostgreSQL Alerts & Rules - ScaleGrid](https://help.scalegrid.io/docs/postgresql-alerts-rules)
61. [Best practices for alerting on metrics - Azure](https://azure.microsoft.com/en-us/blog/best-practices-for-alerting-on-metrics-with-azure-database-for-postgresql-monitoring/)
62. [Postgres performance monitoring: Best practices - ManageEngine](https://blogs.manageengine.com/application-performance-2/appmanager/2024/04/19/postgres-performance-monitoring-best-practices-and-key-metrics.html)
63. [Configure alerts - Azure Database for PostgreSQL](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-alert-on-metrics)
64. [Everything You Need to Know to Start Monitoring Postgres - Last9](https://last9.io/blog/monitoring-postgres/)
65. [Decoding PostgreSQL Monitoring Guide - SigNoz](https://signoz.io/blog/postgresql-monitoring/)

### 系统级监控工具
66. [Dynamic Monitoring PostgreSQL Using pg_top - Severalnines](https://severalnines.com/blog/dynamic-monitoring-postgresql-instances-using-pgtop/)
67. [Key Things to Monitor in PostgreSQL - Severalnines](https://severalnines.com/blog/key-things-monitor-postgresql-analyzing-your-workload/)
68. [Performance Tuning PostgreSQL DB on Server - HostMyCode](https://www.hostmycode.in/tutorials/performance-tuning-postgresql-db-on-server)
69. [Monitoring PostgreSQL Disk I/O Performance - MinervaDB](https://minervadb.xyz/monitoring-postgresql-disk-i-o-performance/)
70. [pgDash - Comprehensive PostgreSQL Monitoring](https://pgdash.io/)

### 其他监控工具
71. [Monitoring PostgreSQL with Nagios and Checkmk - Highgo](https://www.highgo.ca/2021/03/15/monitoring-postgresql-with-nagios-and-checkmk/)
72. [How to monitor a PostgreSQL replication - Claudia Kuenzler](https://www.claudiokuenzler.com/blog/723/how-to-monitor-postgresql-replication)
73. [Monitoring Plugins - check_pgsql](https://www.monitoring-plugins.org/doc/man/check_pgsql.html)
74. [Compare Checkmk vs Zabbix - PeerSpot](https://www.peerspot.com/products/comparisons/checkmk_vs_zabbix)
75. [Understanding Monitoring Tools - Netdata](https://www.netdata.cloud/blog/understanding-monitoring-tools/)

### 连接池监控
76. [Track health of PostgreSQL connection pooling with PgBouncer - Microsoft](https://techcommunity.microsoft.com/blog/adforpostgresql/monitoring-pgbouncer-in-azure-postgresql-flexible-server/3762146)
77. [PostgreSQL Connection Pooling with PgBouncer - pgDash](https://pgdash.io/blog/pgbouncer-connection-pool.html)
78. [PostgreSQL Connection Pooling: PgBouncer Vs. Pgpool-II - ScaleGrid](https://scalegrid.io/blog/postgresql-connection-pooling-part-4-pgbouncer-vs-pgpool/)
79. [PgBouncer Monitoring Metrics - Instaclustr](https://www.instaclustr.com/support/documentation/postgresql-add-ons/pgbouncer-monitoring-metrics/)
80. [PgBouncer command-line usage](https://www.pgbouncer.org/usage.html)
81. [PgBouncer in Azure Database for PostgreSQL - Microsoft](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-pgbouncer)
82. [Connection Pooling - CloudNativePG](https://cloudnative-pg.io/documentation/1.16/connection_pooling/)
83. [Monitor PgBouncer with Datadog - Aiven](https://aiven.io/docs/products/postgresql/howto/monitor-pgbouncer-with-datadog)
84. [Connection pooling intro - PgBouncer and pgpool-II - Cybertec](https://www.cybertec-postgresql.com/en/connection-pooling-intro-pgbouncer-and-pgpool-ii/)
85. [Improve database performance with connection pooling - Stack Overflow](https://stackoverflow.blog/2020/10/14/improve-database-performance-with-connection-pooling/)

### 云平台监控
86. [Managed PostgreSQL Comparison: AWS vs Google Cloud vs Azure - Hasura](https://hasura.io/blog/comparison-of-managed-postgresql-aws-rds-google-cloud-sql-azure-postgresql)
87. [Amazon RDS for PostgreSQL - AWS](https://aws.amazon.com/rds/postgresql/)
88. [Comparing AWS RDS to Google Cloud and Azure - N2W](https://n2ws.com/blog/comparing-aws-relational-database-services-rds-google-microsoft)
89. [Monitoring managed cloud databases - pgwatch2](https://pgwatch2.readthedocs.io/en/latest/using_managed_services.html)
90. [Comparing Postgres Managed Services - PeerDB](https://blog.peerdb.io/comparing-postgres-managed-services-aws-azure-gcp-and-supabase)
91. [AWS vs Azure vs GCP vs Supabase - RisingWave](https://risingwave.com/blog/aws-vs-azure-vs-gcp-vs-supabase-postgres-managed-services-showdown/)
92. [Migrating PostgreSQL to the Cloud - Severalnines](https://severalnines.com/blog/migrating-postgresql-cloud-comparing-solutions-amazon-google-microsoft/)
93. [Database as a service roundup: AWS vs Azure vs Google Cloud - DevOps](https://devopscon.io/blog/database-as-a-service-roundup-aws-vs-azure-vs-google-cloud/)

### APM 工具集成
94. [Comparison of Monitoring Features: DataDog, New Relic, Dynatrace - Medium](https://devjaime.medium.com/comparison-of-monitoring-features-datadog-new-relic-and-dynatrace-71483753d719)
95. [Datadog vs. Dynatrace comparison - Better Stack](https://betterstack.com/community/comparisons/datadog-vs-dynatrace/)
96. [Dynatrace vs AppDynamics vs New Relic](https://www.dynatrace.com/platform/comparison/apm-dynatrace-vs-appdynamics-vs-newrelic)
97. [New Connected Infrastructure & APM Experience - New Relic](https://newrelic.com/blog/how-to-relic/connected-infrastructure-and-apm)
98. [Cost Comparison for New Relic, Datadog, and Dynatrace](https://newrelic.com/blog/nerdlog/cost-comparison-new-relic-vs-datadog-vs-dynatrace)
99. [New Relic Vs Appdynamics Vs Dynatrace - Coralogix](https://coralogix.com/blog/apm-comparison/)

### ELK Stack 集成
100. [Analyze PostgreSQL Statistics Using Elastic Stack - DigitalOcean](https://www.digitalocean.com/community/tutorials/how-to-analyze-managed-postgresql-database-statistics-using-the-elastic-stack-on-ubuntu-18-04)
101. [PostgreSQL monitoring with ELK - GitHub](https://github.com/xeraa/postgresql-monitoring)
102. [Docker-ELK-PostgreSQL - GitHub](https://github.com/melli0505/Docker-ELK-PostgreSQL)
103. [Monitor PostgreSQL with the Elastic Stack - Speaker Deck](https://speakerdeck.com/xeraa/monitor-postgresql-with-the-elastic-stack)
104. [Configuring and authoring Kibana dashboards - AWS](https://aws.amazon.com/blogs/database/configuring-and-authoring-kibana-dashboards/)
105. [Real-time monitoring with ELK Stack - Medium](https://medium.com/@jeromedecinco/real-time-monitoring-with-elk-stack-solutions-and-best-practices-cc7b85ef0469)
106. [Local Development and Log Monitoring Using ELK Stack - Medium](https://abasi-ifreke.medium.com/local-development-and-log-monitoring-using-the-elk-stack-a1469d1f038f)
107. [Kibana Dashboard - Elastic](https://www.elastic.co/kibana/kibana-dashboard)
108. [The Complete Guide to the ELK Stack - Logz.io](https://logz.io/learn/complete-guide-elk-stack/)

### OpenTelemetry 和分布式追踪
109. [Monitor PostgreSQL metrics with OpenTelemetry - SigNoz](https://signoz.io/blog/opentelemetry-postgresql-metrics-monitoring/)
110. [OpenTelemetry PostgreSQL Monitoring - Uptrace](https://uptrace.dev/guides/opentelemetry-postgresql)
111. [Monitor PostgreSQL Performance via OpenTelemetry - OpenObserve](https://openobserve.ai/blog/how-to-monitor-postgresql-performance/)
112. [How to Use OpenTelemetry with Postgres - Last9](https://last9.io/blog/how-to-use-opentelemetry-with-postgres/)
113. [Monitor PostgreSQL with OpenTelemetry - Pradumn Saraf](https://blog.pradumnasaraf.dev/monitor-your-postgresql)
114. [Monitoring PostgreSQL with OpenTelemetry - ServiceNow](https://www.servicenow.com/community/cloud-observability-blog/monitoring-postgresql-with-opentelemetry-and-cloud-observability/ba-p/2671951)
115. [Monitoring Postgres with OpenTelemetry - Splunk](https://lantern.splunk.com/Observability/Product_Tips/Observability_Cloud/Monitoring_Postgres_with_OpenTelemetry)
116. [Distributed Tracing for Postgres with OpenTelemetry - Coditation](https://www.coditation.com/blog/implementing-distributed-tracing-for-postgres-queries-with-opentelemetry-and-jaeger)
117. [Performance and errors monitoring - Uptrace](https://pg.uptrace.dev/tracing/)
118. [EDB Postgres Distributed OpenTelemetry integration](https://www.enterprisedb.com/docs/pgd/5.8/monitoring/otel/)

### Kubernetes 和容器监控
119. [Setup PostgreSQL Monitoring in Kubernetes - Crunchy Data](https://www.crunchydata.com/blog/setup-postgresql-monitoring-in-kubernetes)
120. [Kubernetes PostgreSQL Operator - Portworx](https://portworx.com/postgres-kubernetes/)
121. [CloudNativePG - PostgreSQL Operator for Kubernetes](https://cloudnative-pg.io/)
122. [Percona Operator for PostgreSQL - Monitor Kubernetes](https://docs.percona.com/percona-operator-for-postgresql/2.0/monitor-kubernetes.html)
123. [Deploy Postgres via Kubernetes PostgreSQL Operator - KubeDB](https://kubedb.com/articles/how-to-deploy-postgres-via-kubernetes-postgresql-operator/)
124. [CrunchyData/postgres-operator - GitHub](https://github.com/CrunchyData/postgres-operator)
125. [Choosing a Kubernetes Operator for PostgreSQL - Portworx](https://portworx.com/blog/choosing-a-kubernetes-operator-for-postgresql/)
126. [Monitoring PostgreSQL Containers - Medium](https://pankajconnect.medium.com/monitoring-postgresql-containers-techniques-and-tools-for-docker-environments-490fbd810bd)
127. [PostgreSQL Operator for Kubernetes and Prometheus monitoring](https://rtfm.co.ua/en/postgresql-postgresql-operator-for-kubernetes-and-its-prometheus-monitoring/)
128. [Monitoring PostgreSQL Clusters in Kubernetes - Crunchy Data](https://www.crunchydata.com/blog/monitoring-postgresql-clusters-in-kubernetes)

### CDC 和实时数据流
129. [Enabling CDC with Debezium PostgreSQL Connector - Confluent](https://www.confluent.io/blog/cdc-and-data-streaming-capture-database-changes-in-real-time-with-debezium/)
130. [PostgreSQL CDC Source V2 Connector - Confluent](https://docs.confluent.io/cloud/current/connectors/cc-postgresql-cdc-source-v2-debezium/cc-postgresql-cdc-source-v2-debezium.html)
131. [Debezium connector for PostgreSQL](https://debezium.io/documentation/reference/stable/connectors/postgresql.html)
132. [Real-time CDC using Postgres, Debezium, and Redpanda](https://www.redpanda.com/blog/change-data-capture-postgres-debezium-kafka-connect)
133. [Real-time CDC using PostgreSQL and Debezium - Medium](https://shreyasp619.medium.com/real-time-cdc-using-postgresql-debezium-and-redpanda-b6b074c4242c)
134. [Real Time Data Streaming with Debezium and CDC - Medium](https://sefikcankanber.medium.com/real-time-data-streaming-with-debezium-and-cdc-change-data-capture-c1aa162585a9)
135. [Monitoring Database Changes with Postgres and Debezium - Medium](https://medium.com/@jushijun/real-time-data-streaming-monitoring-database-changes-with-postgres-debezium-and-kafka-f37c85cc9975)
136. [CDC Realtime Streaming with Postgres - Medium](https://medium.com/towards-data-engineering/change-data-capture-cdc-realtime-streaming-with-postgres-debezium-kafka-apache-spark-and-slack-42f6ee74bc1c)
137. [CDC-MySQL-Debezium-PostgreSQL - GitHub](https://github.com/AmanLonare/CDC-MySQL-Debezium-PostgreSQL)

### 中文资源
138. [监控 PostgreSQL 数据库的 5 种方法 - TimescaleDB](https://www.timescaledb.cn/learn/5-ways-to-monitor-your-postgresql-database)
139. [PostgreSQL 实战篇——监控性能及调优方法 - CSDN](https://blog.csdn.net/thinking_chou/article/details/142653818)
140. [PostgreSQL 监控 - w3cschool](https://www.w3cschool.cn/postgresql13_1/postgresql13_1-67l43jhg.html)
141. [PostgreSQL 教程: PostgreSQL 监控 - Redrock](https://www.rockdata.net/zh-cn/tutorial/postgres-monitoring/)
142. [一个能融会贯通PostgreSQL监控的人，大概率是高手 - 知乎](https://zhuanlan.zhihu.com/p/299613755)
143. [使用 Prometheus 和 Grafana 监控 PostgreSQL - Redrock](https://www.rockdata.net/zh-cn/tutorial/monitor-with-prometheus-and-grafana/)
144. [postgresql数据库性能监控 - CSDN](https://blog.csdn.net/qiaowan6397/article/details/101421890)
145. [如何监控PostgreSQL - Cloud Insight](https://www.aiops.com/docs/ci/services_example/postgresql/)
146. [PostgreSQL 性能指南 - TimescaleDB](https://timescale.postgresql.ac.cn/learn/guide-to-postgresql-performance)

### 书籍和培训资源
147. [PostgreSQL: Tutorials & Other Resources](https://www.postgresql.org/docs/online-resources/)
148. [PostgreSQL Tutorial - Neon](https://neon.com/postgresql/tutorial)
149. [PostgreSQL Tutorial - W3Schools](https://www.w3schools.com/postgresql/)
150. [PostgreSQL Documentation](https://www.postgresql.org/docs/)
151. [Top PostgreSQL Courses - Udemy](https://www.udemy.com/topic/postgresql/)
152. [Free EDB Postgres Training and Certification - EDB](https://www.enterprisedb.com/training)
153. [Learn PostgreSQL: Build and manage high-performance database - Amazon](https://www.amazon.com/Learn-PostgreSQL-high-performance-database-solutions/dp/183898528X)
154. [PostgreSQL: Books](https://www.postgresql.org/docs/books/)

### GitHub Awesome 列表
155. [dhamaniasad/awesome-postgres - GitHub](https://github.com/dhamaniasad/awesome-postgres)
156. [Awesome Postgres](https://awesome-postgres.github.io/awesome-postgres/)
157. [pg-tr/awesome-postgres - GitHub](https://github.com/pg-tr/awesome-postgres)
158. [edib/awesome-postgres - GitHub](https://github.com/edib/awesome-postgres)

### 其他监控项目
159. [shadabshaukat/postgres-monitoring - GitHub](https://github.com/shadabshaukat/postgres-monitoring)
160. [DataDog/the-monitor PostgreSQL monitoring tools](https://github.com/DataDog/the-monitor/blob/master/postgresql/postgresql-monitoring-tools.md)
161. [free/sql_exporter - Database agnostic SQL exporter](https://github.com/free/sql_exporter)
162. [databaseleague/percona-postgres_exporter](https://github.com/databaseleague/percona-postgres_exporter)
163. [Grafana Agent postgres.exporter component](https://github.com/grafana/agent/blob/main/docs/sources/flow/reference/components/prometheus.exporter.postgres.md)

### 专业博客和文章
164. [Top Postgres Monitoring Tools in 2024 - Bytebase](https://www.bytebase.com/blog/top-postgres-monitoring-tools/)
165. [Top PostgreSQL Monitoring Tools in 2025 - Uptrace](https://uptrace.dev/tools/postgresql-monitoring-tools/)
166. [Effective PostgreSQL Monitoring - Percona](https://www.percona.com/blog/key-metrics-and-tools-for-effective-postgresql-monitoring/)
167. [Effective PostgreSQL Monitoring pg_stat_all_tables - EDB](https://www.enterprisedb.com/blog/effective-postgresql-monitoring-utilizing-pg_stat_all_tables-and-indexes-postgresql-16)
168. [PostgreSQL Reporting Tools PgBadger - DBAMaster](https://www.dbamaster.com/2025/05/postgresql-reporting-toolspgbadger.html)
169. [PGBadger stands out - Baremon](https://www.baremon.eu/pgbadger-postgresql-monitoring-tools-comparison/)
170. [A detailed look at Pgwatch2 - Cybertec](https://www.cybertec-postgresql.com/en/a-more-detailed-look-at-pgwatch2-postgresql-monitoring-tool/)
171. [How to utilize pgBadger - EDB](https://www.enterprisedb.com/blog/how-to-use-pgbadger-log-analyzer-postgresql-query-performance)
172. [Best PostgreSQL Monitoring Tools - Sematext](https://sematext.com/blog/postgresql-monitoring/)
173. [PostgreSQL monitoring pgwatch - Cybertec](https://www.cybertec-postgresql.com/en/products/pgwatch-postgresql-monitoring/)
174. [PGWatch: Optimized PostgreSQL monitoring](https://pgwatch.com/)
175. [Whats New in Postgres 10 Monitoring - pganalyze](https://pganalyze.com/blog/whats-new-in-postgres-10-monitoring-improvements)
176. [pgCenter, TOP like utility - FatDBA](https://fatdba.com/2021/07/12/pgcenter-a-top-like-utility-for-postgresql-databases/)
177. [Postgres performance at any scale - pganalyze](https://pganalyze.com/)
178. [Monitor PostgreSQL Cluster using pgCenter - DBsGuru](https://dbsguru.com/monitor-postgresql-cluster-using-pgcenter/)
179. [pgCenter download - SourceForge](https://sourceforge.net/projects/pgcenter.mirror/)
180. [App to monitor PostgreSQL queries in real time - Stack Overflow](https://stackoverflow.com/questions/8597516/app-to-monitor-postgresql-queries-in-real-time)

### 高级主题
181. [Data Observability in 2025 - Dagster](https://dagster.io/guides/data-observability-in-2025-pillars-pros-cons-best-practices)
182. [PostgreSQL SolarWinds Monitoring](https://www.solarwinds.com/solarwinds-observability/integrations/postgres-monitoring)
183. [How to efficiently vacuum analyze tables - Stack Overflow](https://stackoverflow.com/questions/37261697/how-to-efficiently-vacuum-analyze-tables-in-postgres)
184. [agapoff/check_kubernetes - Nagios/Icinga/Zabbix plugin](https://github.com/agapoff/check_kubernetes)
185. [Checkmk vs. Nagios XI vs. Zabbix Comparison](https://sourceforge.net/software/compare/Checkmk-vs-Nagios-XI-vs-Zabbix/)
186. [Best monitoring solution for proxmox - Proxmox Forum](https://forum.proxmox.com/threads/best-monitoring-solution-for-proxmox-zabbix-vs-nagios.21347/page-2)
187. [Comparison to other monitoring tools - Zabbix Forums](https://www.zabbix.com/forum/off-topic-discussion/407743-comparison-to-other-monitoring-tools)
188. [Aurora PostgreSQL Audit Log - DataSunrise](https://www.datasunrise.com/knowledge-center/aurora-postgresql-audit-log/)
189. [Postgres Auditing - DataSunrise](https://www.datasunrise.com/knowledge-center/postgres-auditing/)
190. [Audit logs with Cloud SQL and pgAudit - Google Cloud](https://medium.com/google-cloud/audit-logs-on-steroids-with-cloud-sql-for-postgresql-and-pgaudit-d1fdf8725faf)
191. [Using Google Cloud PostgreSQL as source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.GCPostgres.html)
192. [PostgreSQL CDC Source Legacy Connector - Confluent](https://docs.confluent.io/cloud/current/connectors/cc-postgresql-cdc-source-debezium.html)
193. [Pome - PostgreSQL Metrics Dashboard](https://github.com/rach/pome)
194. [PMM - Percona Monitoring and Management](https://www.percona.com/software/database-tools/percona-monitoring-and-management)
195. [pgmetrics - PostgreSQL metrics tool](https://pgmetrics.io/)
196. [pg_view - PostgreSQL activity viewer](https://github.com/zalando/pg_view)
197. [opm.io - Open PostgreSQL Monitoring](https://opm.io/)
198. [Metabase - Simple dashboards for PostgreSQL](https://www.metabase.com/)
199. [PoWA - PostgreSQL Workload Analyzer](https://powa.readthedocs.io/)
200. [Top PostgreSQL Courses Online - Updated 2025](https://www.udemy.com/topic/postgresql/)

### 其他重要资源
201. [PostgreSQL Tutorial PDF](https://www.postgresql.org/files/documentation/pdf/7.3/tutorial-7.3.2-US.pdf)
202. [PostgreSQL Tutorial - Part I](https://www.postgresql.org/docs/current/tutorial.html)
203. [Amazon RDS for PostgreSQL Pricing](https://aws.amazon.com/rds/postgresql/pricing/)
204. [Monitor PostgreSQL Comparison to other tools](https://devopscon.io/blog/monitoring-strategies-for-postgresql-databases/)
205. [How to setup effective PostgreSQL monitoring](https://www.postgresql.org/message-id/flat/CAH%2ByL9KRAa96MXPeCgx3fKhH1rNh7w6b8TJCgfxOBOvB_wD6Ow%40mail.gmail.com)

## 学习目标

完成本章学习后，你将能够：

1. **理解监控原理**：掌握 PostgreSQL 监控的核心概念和层次架构
2. **使用内置工具**：熟练使用 pg_stat_* 视图和 pg_stat_statements 进行性能分析
3. **搭建监控系统**：能够独立搭建 Prometheus + Grafana 监控栈
4. **配置告警规则**：设计合理的告警策略和阈值
5. **分析性能问题**：使用监控数据定位和解决性能瓶颈
6. **审计与合规**：配置审计日志满足合规要求
7. **容器化监控**：在 Kubernetes 环境中部署和管理监控
8. **优化监控策略**：根据业务需求定制监控方案

## 小结

监控是保障 PostgreSQL 数据库稳定运行的关键环节。通过本章的学习，你将掌握从基础的内置监控工具到企业级监控平台的完整知识体系，能够构建适合自己业务需求的监控解决方案，及时发现和解决数据库性能问题，确保系统的高可用性和最佳性能。