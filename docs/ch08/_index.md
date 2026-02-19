---
title: "8. 抽丝剥茧：慢 SQL 诊断方法论"
weight: 800
math: true
breadcrumbs: false
---

> [!WARN] 本章为 AI 批量生成的草稿目录，尚未编写，请务必注意。

## 章节大纲

### 一、扩展基础概念
#### 1.1 什么是 PostgreSQL 扩展
- 扩展的定义和架构
- 扩展与内核的关系
- 扩展的优势与劣势
- 扩展生态系统概览

#### 1.2 扩展的分类体系
- 按功能分类（时序、地理、搜索、分析等）
- 按语言分类（C、Rust、Python、Perl、JavaScript）
- 按来源分类（Contrib、第三方、自研）
- 按部署方式分类（共享库、SQL、混合）

#### 1.3 扩展的工作原理
- 动态加载机制
- 钩子（Hook）系统
- 共享内存管理
- 后台工作进程

### 二、扩展管理基础
#### 2.1 CREATE EXTENSION 命令
- 基本语法和参数
- 依赖管理（CASCADE）
- 架构（SCHEMA）指定
- 版本控制

#### 2.2 扩展的安装方式
- 包管理器安装（apt、yum、brew）
- 源码编译安装
- PGXS 构建系统
- Docker 容器部署

#### 2.3 扩展的配置管理
- postgresql.conf 配置
- shared_preload_libraries
- 会话级配置
- 权限管理

#### 2.4 扩展的升级与迁移
- ALTER EXTENSION UPDATE
- 版本兼容性检查
- pg_upgrade 注意事项
- 云平台迁移策略

### 三、核心扩展详解
#### 3.1 Contrib 模块
- pg_stat_statements：查询性能分析
- pgcrypto：加密功能
- uuid-ossp：UUID 生成
- hstore：键值存储
- ltree：层次数据
- intarray：整数数组操作

#### 3.2 监控与性能扩展
- pg_stat_statements：查询统计
- pg_wait_sampling：等待事件采样
- pg_hint_plan：执行计划控制
- auto_explain：自动 EXPLAIN
- pg_stat_kcache：内核级统计

#### 3.3 安全与审计扩展
- pgAudit：审计日志
- set_user：权限提升控制
- pgcrypto：数据加密
- passwordcheck：密码策略
- sepgsql：SELinux 集成

#### 3.4 维护管理扩展
- pg_partman：分区管理
- pg_cron：作业调度
- pg_repack：在线重组
- pgstattuple：表膨胀分析

### 四、时序与分析扩展
#### 4.1 TimescaleDB
- 时序数据模型
- 超表（Hypertable）
- 连续聚合
- 数据保留策略
- 性能优化

#### 4.2 Citus
- 分布式架构
- 分片策略（行级、模式级）
- 查询路由
- 分布式事务
- 集群管理

#### 4.3 列存储扩展
- Citus columnar
- ZEDSTORE（实验性）
- Parquet 支持
- 压缩算法

### 五、地理空间扩展
#### 5.1 PostGIS
- 空间数据类型
- 空间索引（GIST、SP-GIST）
- 空间函数
- 拓扑处理
- 栅格数据

#### 5.2 路由与地图扩展
- pgRouting：路径规划
- h3-pg：H3 六边形索引
- MobilityDB：移动对象

### 六、AI 与向量扩展
#### 6.1 pgvector
- 向量存储与索引
- 相似度搜索
- 嵌入（Embedding）管理
- HNSW 和 IVFFlat 索引
- 与 LLM 集成

#### 6.2 机器学习扩展
- PostgresML
- MADlib
- PL/Python 与 scikit-learn

### 七、全文搜索扩展
#### 7.1 内置全文搜索
- tsvector 和 tsquery
- 文本搜索配置
- 词典和同义词

#### 7.2 高级搜索扩展
- PGroonga：多语言全文搜索
- pg_search（Ruby）
- zhparser：中文分词
- pg_jieba：结巴分词

### 八、编程语言扩展
#### 8.1 过程语言
- PL/pgSQL（内置）
- PL/Python（plpython3u）
- PL/Perl（plperl）
- PLV8（JavaScript）
- PL/Rust

#### 8.2 语言特性比较
- 性能对比
- 使用场景
- 安全性考虑
- 生态系统

### 九、外部数据访问
#### 9.1 Foreign Data Wrapper
- postgres_fdw：PostgreSQL 互联
- oracle_fdw：Oracle 访问
- mysql_fdw：MySQL 访问
- file_fdw：文件访问

#### 9.2 数据集成扩展
- Debezium：CDC 实时同步
- kafka_fdw：Kafka 集成
- mongo_fdw：MongoDB 访问

### 十、API 与协议扩展
#### 10.1 GraphQL 支持
- pg_graphql
- PostGraphile
- Hasura 集成

#### 10.2 REST API
- PostgREST
- pREST

#### 10.3 兼容性扩展
- Babelfish：SQL Server 兼容
- FerretDB：MongoDB 协议

### 十一、图数据库扩展
#### 11.1 Apache AGE
- 图数据模型
- Cypher 查询语言
- 图算法
- 可视化工具

#### 11.2 其他图扩展
- pg_graph
- 递归查询应用

### 十二、扩展开发
#### 12.1 C 语言扩展开发
- PGXS 构建系统
- 基本结构
- 内存管理
- 错误处理
- SPI 接口

#### 12.2 Rust 扩展开发（pgrx）
- pgrx 框架
- cargo-pgrx 工具
- 类型映射
- 生命周期管理

#### 12.3 扩展测试
- pgTAP 单元测试
- 回归测试
- 性能基准测试
- CI/CD 集成

### 十三、扩展生态系统
#### 13.1 扩展仓库
- PGXN（PostgreSQL Extension Network）
- apt/yum 仓库
- Pigsty 扩展仓库
- trunk、dbdev、pgxman

#### 13.2 扩展选型
- 评估标准
- 兼容性矩阵
- 性能影响
- 维护状态

#### 13.3 最佳实践
- 扩展使用原则
- 性能优化
- 安全加固
- 监控告警

### 十四、云平台扩展支持
#### 14.1 AWS RDS/Aurora
- 支持的扩展列表
- Trusted Language Extensions
- 限制和注意事项

#### 14.2 Google Cloud SQL
- 扩展配置方法
- 特有限制

#### 14.3 Azure Database
- 扩展白名单机制
- 部署策略

### 十五、动手实验
#### 实验1：安装和配置常用扩展
- 安装 pg_stat_statements
- 配置 pgAudit
- 部署 TimescaleDB

#### 实验2：使用 pgvector 构建向量搜索
- 创建向量表
- 导入嵌入数据
- 执行相似度搜索

#### 实验3：PostGIS 空间查询
- 导入地理数据
- 空间索引创建
- 距离和包含查询

#### 实验4：开发简单扩展
- 使用 PGXS 创建扩展
- 实现自定义函数
- 打包和分发

## 参考资料

### 官方文档
1. [PostgreSQL: Documentation - CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html)
2. [PostgreSQL: Documentation - Packaging Related Objects into an Extension](https://www.postgresql.org/docs/current/extend-extensions.html)
3. [PostgreSQL: Documentation - Extension Building Infrastructure](https://www.postgresql.org/docs/current/extend-pgxs.html)
4. [PostgreSQL: Documentation - ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html)
5. [PostgreSQL: Documentation - Additional Supplied Modules and Extensions](https://www.postgresql.org/docs/current/contrib.html)
6. [PostgreSQL: Documentation - pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html)
7. [PostgreSQL: Documentation - JSON Types](https://www.postgresql.org/docs/current/datatype-json.html)
8. [PostgreSQL: Documentation - JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html)
9. [PostgreSQL: Documentation - PL/Python](https://www.postgresql.org/docs/current/plpython.html)
10. [PostgreSQL Wiki - Foreign data wrappers](https://wiki.postgresql.org/wiki/Foreign_data_wrappers)
11. [PostgreSQL Wiki - Monitoring](https://wiki.postgresql.org/wiki/Monitoring)
12. [PostgreSQL Wiki - Building and Installing PostgreSQL Extension Modules](https://wiki.postgresql.org/wiki/Building_and_Installing_PostgreSQL_Extension_Modules)
13. [PostgreSQL Wiki - Extension Ecosystem: Jobs and Tools](https://wiki.postgresql.org/wiki/Extension_Ecosystem:_Jobs_and_Tools)
14. [PostgreSQL Wiki - PGXN](https://wiki.postgresql.org/wiki/PGXN)
15. [PostgreSQL Wiki - PGXN v2](https://wiki.postgresql.org/wiki/PGXN_v2)
16. [PostgreSQL Wiki - PGXN v2/Architecture](https://wiki.postgresql.org/wiki/PGXN_v2/Architecture)

### Pigsty 和 Vonng.com 资源
17. [Pigsty Extension Documentation](https://pigsty.cc/docs/pgsql/extension/)
18. [Pigsty Extension Catalog](https://pgext.cloud/)
19. [PGSQL x Pigsty: 数据库全能王](http://vonng.com/cn/blog/db/pgsql-x-pigsty/)
20. [pg_stat_statements 宏观查询优化](http://vonng.com/cn/blog/db/pgss/)
21. [展望PostgreSQL的2024](https://vonng.com/cn/blog/db/pg-in-2024/)
22. [AI大模型与向量数据库](http://vonng.com/cn/blog/db/llm-and-pgvector/)
23. [开箱即用的PG发行版：Pigsty](http://vonng.com/cn/blog/db/pigsty-intro/)
24. [PostgreSQL：最成功的数据库](https://vonng.com/cn/blog/db/pg-is-no1/)

### 扩展仓库和目录
25. [PGXN: PostgreSQL Extension Network](https://pgxn.org/)
26. [GitHub - dhamaniasad/awesome-postgres](https://github.com/dhamaniasad/awesome-postgres)
27. [GitHub - pg-tr/awesome-postgres](https://github.com/pg-tr/awesome-postgres)
28. [1000+ PostgreSQL EXTENSIONs List](https://gist.github.com/joelonsql/e5aa27f8cc9bd22b8999b7de8aee9d47)
29. [PostgreSQL Extensions on Cloud](https://www.pgextensions.org/)

### 核心扩展项目
30. [GitHub - citusdata/citus: Distributed PostgreSQL](https://github.com/citusdata/citus)
31. [GitHub - timescale/timescaledb: Time-series database](https://github.com/timescale/timescaledb)
32. [GitHub - pgvector/pgvector: Vector similarity search](https://github.com/pgvector/pgvector)
33. [PostGIS Official Site](https://postgis.net/)
34. [GitHub - apache/age: Graph database extension](https://github.com/apache/age)
35. [GitHub - apache/age-viewer: Graph visualization](https://github.com/apache/age-viewer)
36. [GitHub - pgroonga/pgroonga: Multilingual full text search](https://github.com/pgroonga/pgroonga)
37. [GitHub - laurenz/oracle_fdw: Oracle Foreign Data Wrapper](https://github.com/laurenz/oracle_fdw)
38. [GitHub - pgaudit/pgaudit: PostgreSQL Audit Extension](https://github.com/pgaudit/pgaudit)
39. [GitHub - pgaudit/set_user: Privilege escalation control](https://github.com/pgaudit/set_user)
40. [GitHub - citusdata/pg_cron: Job scheduler](https://github.com/citusdata/pg_cron)
41. [GitHub - pgpartman/pg_partman: Partition management](https://github.com/pgpartman/pg_partman)
42. [GitHub - postgrespro/pg_wait_sampling: Wait event sampling](https://github.com/postgrespro/pg_wait_sampling)
43. [GitHub - ossc-db/pg_hint_plan: Optimizer hints](https://github.com/ossc-db/pg_hint_plan)
44. [GitHub - theory/pgtap: Unit testing suite](https://github.com/theory/pgtap)
45. [GitHub - plv8/plv8: V8 JavaScript procedural language](https://github.com/plv8/plv8)
46. [GitHub - tcdi/plrust: Rust procedural language](https://github.com/tcdi/plrust)
47. [GitHub - pgcentralfoundation/pgrx: Build extensions with Rust](https://github.com/pgcentralfoundation/pgrx)
48. [GitHub - hydradatabase/columnar: Columnar storage](https://github.com/hydradatabase/columnar)
49. [GitHub - postgrespro/zson: JSONB compression](https://github.com/postgrespro/zson)
50. [GitHub - hasura/graphql-engine: GraphQL APIs](https://github.com/hasura/graphql-engine)

### 监控和性能扩展
51. [GitHub - prometheus-community/postgres_exporter](https://github.com/prometheus-community/postgres_exporter)
52. [GitHub - lesovsky/pgscv: Multi-purpose monitoring agent](https://github.com/lesovsky/pgscv)
53. [GitHub - pgsty/pg_exporter: Advanced metrics exporter](https://github.com/pgsty/pg_exporter)
54. [GitHub - CrunchyData/pgmonitor: Monitoring resources](https://github.com/CrunchyData/pgmonitor)
55. [GitHub - coroot/coroot-pg-agent: Query performance](https://github.com/coroot/coroot-pg-agent)
56. [GitHub - cybertec-postgresql/pgwatch2: Metrics monitor](https://github.com/cybertec-postgresql/pgwatch2)
57. [GitHub - dalibo/pg_activity: Top-like application](https://github.com/dalibo/pg_activity)
58. [GitHub - darold/pgbadger: Log analyzer](https://github.com/darold/pgbadger)
59. [GitHub - percona/pg_stat_monitor: Query monitoring](https://github.com/percona/pg_stat_monitor)

### 中文分词和搜索扩展
60. [GitHub - amutu/zhparser: Chinese full-text search](https://github.com/amutu/zhparser)
61. [GitHub - jaiminpan/pg_jieba: Jieba Chinese segmentation](https://github.com/jaiminpan/pg_jieba)
62. [GitHub - yanyiwu/pg_jieba: Alternative pg_jieba](https://github.com/yanyiwu/pg_jieba)
63. [GitHub - VitoVan/pg_jieba_opencc: Traditional/Simplified Chinese](https://github.com/VitoVan/pg_jieba_opencc)
64. [GitHub - postgres-cn/pgdoc-cn: Chinese documentation](https://github.com/postgres-cn/pgdoc-cn)

### 教程和最佳实践
65. [Top PostgreSQL Extensions: Installation and Management](https://hevodata.com/learn/top-postgresql-extensions/)
66. [Top 8 PostgreSQL Extensions - TigerData](https://www.tigerdata.com/blog/top-8-postgresql-extensions)
67. [Top 11 PostgreSQL Extensions - Airbyte](https://airbyte.com/data-engineering-resources/postgresql-extensions)
68. [Top 9 PostgreSQL Extensions 2024 - Bytebase](https://www.bytebase.com/blog/top-postgres-extension/)
69. [PostgreSQL Extension Installation Best Practices - DBA Stack Exchange](https://dba.stackexchange.com/questions/210508/postgresql-extension-installation-best-practices)
70. [How to Upgrade PostgreSQL Extensions - Percona](https://www.percona.com/blog/upgrading-postgresql-extensions/)
71. [PostgreSQL Extensions: uuid-ossp - TigerData](https://www.tigerdata.com/learn/postgresql-extensions-uuid-ossp)
72. [PostgreSQL Extensions: hstore - TigerData](https://www.tigerdata.com/learn/postgresql-extensions-hstore)
73. [PostgreSQL Extensions: pgTAP - TigerData](https://www.tigerdata.com/learn/postgresql-extensions-pgtap)
74. [PostgreSQL Extensions: PGroonga - Supabase](https://supabase.com/docs/guides/database/extensions/pgroonga)
75. [pgTAP: Unit Testing - Supabase](https://supabase.com/docs/guides/database/extensions/pgtap)
76. [pgvector: Embeddings and vector similarity - Supabase](https://supabase.com/docs/guides/database/extensions/pgvector)
77. [timescaledb: Time-Series data - Supabase](https://supabase.com/docs/guides/database/extensions/timescaledb)

### 扩展开发
78. [PostgreSQL: Simple C Extension Development - Percona](https://www.percona.com/blog/postgresql-simple-c-extension-development-for-a-novice-user/)
79. [Writing PostgreSQL Extensions is Fun – C Language - Percona](https://www.percona.com/blog/writing-postgresql-extensions-is-fun-c-language/)
80. [PostgreSQL C Extension - DEV Community](https://dev.to/hadyo/postgresql-c-extension-g1h)
81. [Easy guide to writing PostgreSQL extensions - Cybertec](https://www.cybertec-postgresql.com/en/easy-guide-to-writing-postgresql-extensions/)
82. [How to create, test and debug a C extension - Highgo](https://www.highgo.ca/2020/01/10/how-to-create-test-and-debug-an-extension-written-in-c-for-postgresql/)
83. [Writing PostgreSQL extension in Rust With pgrx](https://kaiwern.com/posts/2022/07/20/writing-postgresql-extension-in-rust-with-pgx/)
84. [PL/Rust Guide](https://plrust.io/)
85. [Develop Extensions Using PGRX - Apache Cloudberry](https://cloudberry.apache.org/docs/developer/develop-extensions-using-rust/)
86. [PgDD extension moves to pgrx - RustProof Labs](https://blog.rustprooflabs.com/2021/10/pgdd-extension-using-pgx-rust)
87. [pgrx Documentation](https://docs.rs/pgrx/latest/pgrx/)
88. [Create unit testing framework using pgTAP - AWS](https://aws.amazon.com/blogs/database/create-a-unit-testing-framework-for-postgresql-using-the-pgtap-extension/)
89. [How To Set Up pgTAP - End Point Dev](https://www.endpointdev.com/blog/2023/04/pgtap-for-database-unit-tests/)
90. [pgTAP Documentation](https://pgtap.org/documentation.html)

### 时序数据库扩展
91. [Managing Time Series Data Using TimescaleDB - Percona](https://www.percona.com/blog/managing-time-series-data-using-timescaledb-powered-postgresql/)
92. [TimescaleDB Deployment Practices - Alibaba Cloud](https://www.alibabacloud.com/blog/postgresql-time-series-database-plug-in-timescaledb-deployment-practices_594814)
93. [How to Enable TimescaleDB - Severalnines](https://severalnines.com/blog/how-enable-timescaledb-existing-postgresql-database/)
94. [PostgreSQL TimescaleDB: Handling Time-Series Data](https://www.w3resource.com/PostgreSQL/snippets/postgresql-timescaledb.php)
95. [TimescaleDB vs. PostgreSQL for time-series data](https://medium.com/timescale/timescaledb-vs-6a696248104e)
96. [PostgreSQL + TimescaleDB: 1,000x Faster Queries](https://www.tigerdata.com/blog/postgresql-timescaledb-1000x-faster-queries-90-data-compression-and-much-more)

### 分布式扩展
97. [Citus Data - Distributed PostgreSQL](https://www.citusdata.com/)
98. [Citus 12: Schema-based sharding](https://www.citusdata.com/blog/2023/07/18/citus-12-schema-based-sharding-for-postgres/)
99. [Sharding Postgres on a single Citus node](https://www.citusdata.com/blog/2021/03/20/sharding-postgres-on-a-single-citus-node/)
100. [Understanding partitioning and sharding in Citus](https://www.citusdata.com/blog/2023/08/04/understanding-partitioning-and-sharding-in-postgres-and-citus/)
101. [Scaling Horizontally with Citus - Medium](https://demirhuseyinn-94.medium.com/scaling-horizontally-on-postgresql-cituss-impact-on-database-architecture-295329c72c62)
102. [Beginner's Guide to Sharding with Citus - Stormatics](https://stormatics.tech/blogs/a-beginners-guide-to-sharding-postgresql-with-citus)

### 向量和 AI 扩展
103. [Storing OpenAI embeddings with pgvector - Supabase](https://supabase.com/blog/openai-embeddings-postgres-vector)
104. [PostgreSQL as a Vector Database - Timescale](https://www.timescale.com/blog/postgresql-as-a-vector-database-create-store-and-query-openai-embeddings-with-pgvector)
105. [PostgreSQL as a Vector Database Guide - Airbyte](https://airbyte.com/data-engineering-resources/postgresql-as-a-vector-database)
106. [What is pgvector - EDB](https://www.enterprisedb.com/blog/what-is-pgvector)
107. [Vector Similarity Search with pgvector - Severalnines](https://severalnines.com/blog/vector-similarity-search-with-postgresqls-pgvector-a-deep-dive/)
108. [Building AI-Powered Search with PostgreSQL - Medium](https://medium.com/@richardhightower/building-ai-powered-search-and-rag-with-postgresql-and-vector-embeddings-09af314dc2ff)
109. [pgvector Tutorial - DataCamp](https://www.datacamp.com/tutorial/pgvector-tutorial)
110. [Amazon Aurora PostgreSQL Adds pgvector - InfoQ](https://www.infoq.com/news/2023/07/aws-aurora-pgvector/)
111. [Setting Up PostgreSQL with pgvector in Docker - Medium](https://medium.com/@adarsh.ajay/setting-up-postgresql-with-pgvector-in-docker-a-step-by-step-guide-d4203f6456bd)

### 地理空间扩展
112. [PostGIS Getting Started](https://postgis.net/documentation/getting_started/)
113. [Managing spatial data with PostGIS - AWS RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html)
114. [Spatial Queries with PostgreSQL and PostGIS - Medium](https://medium.com/@limeira.felipe94/a-beginners-guide-to-spatial-queries-with-postgresql-and-postgis-8128392f7bb6)
115. [Install Postgres/PostGIS and get started - Zev Ross](https://www.zevross.com/blog/2019/12/04/install-postgres-postgis-and-get-started-with-spatial-sql/)
116. [Getting Started With PostGIS Guide - Boston GIS](https://www.bostongis.com/PrinterFriendly.aspx?content_name=postgis_tut01)
117. [Using PostGIS extension - Scaleway](https://www.scaleway.com/en/docs/tutorials/postgis-managed-databases/)
118. [Introduction to PostGIS](https://postgis.net/workshops/postgis-intro/introduction.html)
119. [Creating a Spatial Database - PostGIS](https://postgis.net/workshops/postgis-intro/creating_db.html)

### GraphQL 和 API 扩展
120. [Create GraphQL APIs on PostgreSQL - Hasura](https://hasura.io/graphql/database/postgresql)
121. [Six Ways to add GraphQL API - Moesif](https://www.moesif.com/blog/graphql/technical/Ways-To-Add-GraphQL-To-Your-Postgres-Database-Comparing-Hasura-Prisma-and-Others/)
122. [Kickstart GraphQL API with Hasura - Vincit](https://www.vincit.com/blog/kickstart-your-graphql-api-with-hasura)
123. [Optimizing GraphQL API with Postgres - Hasura](https://hasura.io/blog/optimizing-your-graphql-api-postgresql)
124. [pg_graphql: GraphQL extension - Supabase](https://supabase.com/blog/pg-graphql)
125. [Full Text Search with Hasura - Hasura](https://hasura.io/blog/full-text-search-with-hasura-graphql-api-postgres)

### 图数据库扩展
126. [Apache AGE Official Site](https://age.apache.org/)
127. [Apache AGE Extension - Azure](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/generative-ai-age-overview)
128. [Apache AGE with LangChain](https://python.langchain.com/docs/integrations/graphs/apache_age/)
129. [PostgreSQL with Apache AGE - Fabio Marini](https://www.fabiomarini.net/postgresql-with-apache-age-playing-more-seriously-with-graph-databases/)
130. [ApacheAGE on PGXN](https://pgxn.org/dist/apacheage/)
131. [Introduction to Apache AGE - DEV Community](https://dev.to/markgomer/introduction-to-apache-age-graph-extension-for-postgresql-p2l)

### 云平台支持
132. [Configure PostgreSQL extensions - Google Cloud SQL](https://cloud.google.com/sql/docs/postgres/extensions)
133. [Extension versions for Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html)
134. [Managed PostgreSQL Comparison: AWS vs GCP vs Azure - Hasura](https://hasura.io/blog/comparison-of-managed-postgresql-aws-rds-google-cloud-sql-azure-postgresql)
135. [Amazon RDS for PostgreSQL](https://aws.amazon.com/rds/postgresql/)
136. [Trusted Language Extensions - AWS Blog](https://aws.amazon.com/blogs/aws/new-trusted-language-extensions-for-postgresql-on-amazon-aurora-and-amazon-rds/)
137. [Using PostgreSQL extensions with RDS - AWS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.html)
138. [Allow extensions - Azure](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-allow-extensions)
139. [Supported PostgreSQL extension versions - AWS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.FeatureSupport.Extensions.html)
140. [Major version upgrades - Azure](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-major-version-upgrade)
141. [Upgrade database major version - Google Cloud](https://cloud.google.com/sql/docs/postgres/upgrade-major-db-version-inplace)
142. [Upgrading PostgreSQL extensions - AWS Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/USER_UpgradeDBInstance.Upgrading.ExtensionUpgrades.html)

### FDW 和数据集成
143. [Working with Oracle databases using oracle_fdw - AWS RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/postgresql-oracle-fdw.html)
144. [Working with Oracle databases using oracle_fdw - AWS Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/postgresql-oracle-fdw.html)
145. [oracle_fdw on PGXN](https://pgxn.org/dist/oracle_fdw/)
146. [Using FDW to access remote databases - EDB](https://www.enterprisedb.com/postgres-tutorials/using-foreign-data-wrappers-access-remote-postgresql-and-oracle-databases)
147. [oracle_fdw Documentation](https://laurenz.github.io/oracle_fdw/)
148. [PostgreSQL Insider - oracle_fdw](https://www.postgresql.fastware.com/postgresql-insider-fdw-ora-bas)
149. [Working with supported FDW - AWS RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.foreign-data-wrappers.html)
150. [Working with supported FDW - AWS Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.foreign-data-wrappers.html)

### 维护和调度扩展
151. [Scheduling maintenance with pg_cron - AWS RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL_pg_cron.html)
152. [Scheduling maintenance with pg_cron - AWS Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/PostgreSQL_pg_cron.html)
153. [pg_partman on PGXN](https://pgxn.org/dist/pg_partman/doc/pg_partman.html)
154. [Managing partitions with pg_partman - AWS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL_Partitions.html)
155. [Range Partition Management with pg_partman - Medium](https://raghav-patel.medium.com/simplify-range-partition-management-in-aws-rds-aurora-postgresql-with-pg-partman-and-pg-cron-996219799fcc)
156. [pg_partman documentation - Crunchy Data](https://access.crunchydata.com/documentation/pg-partman/2.6.3/)

### 性能和监控扩展
157. [PostgreSQL Extension pg_wait_sampling - Andy Atkinson](https://andyatkinson.com/blog/2024/07/23/postgresql-extension-pg_wait_sampling)
158. [Control execution plans with pg_hint_plan](https://www.postgresql.fastware.com/postgresql-insider-tun-hint-plan)
159. [pg_wait_sampling on PGXN](https://pgxn.org/dist/pg_wait_sampling/)
160. [pg_hint_plan description](https://github.com/ossc-db/pg_hint_plan/blob/master/docs/description.md)
161. [Query Optimizer Hints - Medium](https://medium.com/@encodedots/postgres-query-optimizer-hints-when-and-how-to-use-them-effectively-f86e36646692)
162. [Replacing Oracle Hints with pg_hint_plan - pganalyze](https://pganalyze.com/blog/migrating-from-oracle-hints-to-pg-hint-plan-on-postgresql)

### 安全扩展
163. [PGAudit Official Site](https://www.pgaudit.org/)
164. [Secure Your PostgreSQL Database - Moldstud](https://moldstud.com/articles/p-secure-your-postgresql-database-how-to-use-security-extensions-to-harden-your-setup)

### 列存储和高级存储
165. [Zedstore - Compressed Columnar Storage](https://blogs.vmware.com/opensource/2020/07/14/zedstore-compressed-columnar-storage-for-postgres/)
166. [Zedstore discussion - PostgreSQL](https://www.postgresql.org/message-id/CALfoeiuF-m5jg51mJUPm5GN8u396o5sA2AF5N97vTRAEDYac7w@mail.gmail.com)
167. [PostgreSQL storage options comparison - Cybertec](https://www.cybertec-postgresql.com/en/postgresql-storage-comparing-storage-options/)
168. [Mixed Storage in PostgreSQL Zedstore - Alibaba Cloud](https://www.alibabacloud.com/blog/use-mixed-storage-of-rows-and-columns-in-postgresql-zedstore_598963)
169. [PostgreSQL Columnar Store discussion](https://news.ycombinator.com/item?id=7523950)

### Docker 和容器化
170. [How to Use the Postgres Docker Official Image](https://www.docker.com/blog/how-to-use-the-postgres-docker-official-image/)
171. [PostgreSQL Docker Hub](https://hub.docker.com/_/postgres)
172. [PostgreSQL Docker Image with custom extensions - DataCraze](https://datacraze.io/postgresql-docker-image-adding-extensions/)
173. [Install and run Postgres with extension using docker-compose](https://gist.github.com/leopoldodonnell/b0b7e06943bd389560184d948bdc2d5b)
174. [How to create postgres extension inside container - Stack Overflow](https://stackoverflow.com/questions/40040540/how-to-create-postgres-extension-inside-the-container)
175. [Docker with postgres and pgvector extension](https://www.thestupidprogrammer.com/blog/docker-with-postgres-and-pgvector-extension)
176. [Installing extensions on PostgreSQL docker container](https://forums.unraid.net/topic/149636-installing-extensions-on-postgresql-docker-container/)
177. [How to install PostgreSQL extension with Docker - Stack Overflow](https://stackoverflow.com/questions/78275997/how-to-install-postgresql-extension-with-docker)
178. [PostgreSQL in Docker: Step-by-Step Guide - DataCamp](https://www.datacamp.com/tutorial/postgresql-docker)

### 基准测试和性能
179. [How to Benchmark PostgreSQL for Optimal Performance - DZone](https://dzone.com/articles/how-to-benchmark-postgresql-for-optimal-performance)
180. [How to measure performance of PostgreSQL - Medium](https://medium.com/@dmitry.romanoff/how-to-measure-performance-of-postgresql-database-server-s-b27e2e5130aa)
181. [PostgreSQL vs MySQL performance benchmarking - Medium](https://medium.com/@servikash/postgresql-vs-mysql-performance-benchmarking-e2929ee377d4)
182. [A Performance Benchmark for PostgreSQL and MySQL - MDPI](https://www.mdpi.com/1999-5903/16/10/382)
183. [Better Security and Performance with PostgreSQL 16](https://blog.gitguardian.com/benchmarking-postgresql-16/)
184. [PostgreSQL Benchmarking: pgbench Guide - Heatware](https://www.heatware.net/postgresql/pgbench-for-performance-testing/)
185. [PostgreSQL Performance Improvements - EDB](https://www.enterprisedb.com/blog/performance-comparison-major-PostgreSQL-versions)
186. [How to Benchmark PostgreSQL Performance - Severalnines](https://severalnines.com/blog/benchmarking-postgresql-performance/)

### 扩展兼容性和升级
187. [Upgrade Postgres Extension - Stack Overflow](https://stackoverflow.com/questions/48325800/upgrade-postgres-extension-install-specific-version)
188. [Upgrade PostgreSQL - TigerData](https://docs.tigerdata.com/self-hosted/latest/upgrades/upgrade-pg/)
189. [Upgrades of the RDS PostgreSQL DB engine - AWS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.PostgreSQL.html)

### JavaScript 和 PLV8
190. [JavaScript in your Postgres - Heroku](https://blog.heroku.com/javascript_in_your_postgres)
191. [PL/v8 on PGXN](https://pgxn.org/dist/plv8/doc/plv8.html)
192. [plv8 disadvantages or limitations - Stack Overflow](https://stackoverflow.com/questions/30893409/plv8-disadvantages-or-limitations)
193. [Install PL/Python and PLV8 - Victor Fang](https://victorfang.wordpress.com/2015/03/21/install-plpython-and-plv8-to-postgresql-ubuntu/)
194. [Official benchmark comparing PL - GitHub Issue](https://github.com/plv8/plv8/issues/301)

### 语言扩展
195. [EDB Language Pack - Using procedural languages](https://www.enterprisedb.com/docs/language_pack/latest/using/)
196. [PostgreSQL: how to install plpythonu - Stack Overflow](https://stackoverflow.com/questions/26091390/postgresql-how-to-install-plpythonu-extension)
197. [PostgreSQL with Mingw, pltcl, plperl, plpython](https://www.postgresql.org/message-id/CY1PR03MB218754CD8AA1861D4CBC43A09CAF0@CY1PR03MB2187.namprd03.prod.outlook.com)

### 全文搜索扩展
198. [PGroonga Official Site](https://pgroonga.github.io/)
199. [PGroonga 3.2.4 announcement](https://www.postgresql.org/about/news/pgroonga-324-multilingual-fast-full-text-search-2943/)
200. [PGroonga versus textsearch and pg_trgm](https://pgroonga.github.io/reference/pgroonga-versus-textsearch-and-pg-trgm.html)
201. [GitHub - Casecommons/pg_search: Rails ActiveRecord](https://github.com/Casecommons/pg_search)
202. [Full Text Search in Rails and PostgreSQL - pganalyze](https://pganalyze.com/blog/full-text-search-ruby-rails-postgres)
203. [Full Text Search with Rails - Medium](https://medium.com/skylar-salernos-tech-blog/full-text-search-with-postgres-and-rails-6a5d1221b1d9)
204. [Full-text search with PostgreSQL - thoughtbot](https://thoughtbot.com/blog/full-text-search-with-postgres-and-action-text)
205. [Integrating Full-Text Search in Rails - Medium](https://medium.com/@usamailyas102/integrating-full-text-search-in-rails-and-postgresql-a-comprehensive-guide-57ae245fd99a)
206. [Chinese Full-Text Search](https://gist.github.com/ciiiii/0e9f3ffcd1b33b087fc5d5b02bf72bce)

### 书籍和学习资源
207. [PostgreSQL: Books](https://www.postgresql.org/docs/books/)
208. [The Art of PostgreSQL](https://theartofpostgresql.com/)
209. [PostgreSQL: Documentation](https://www.postgresql.org/docs/)
210. [PostgreSQL: Tutorials & Other Resources](https://www.postgresql.org/docs/online-resources/)
211. [Learn PostgreSQL - Amazon](https://www.amazon.com/Learn-PostgreSQL-high-performance-database-solutions/dp/183898528X)
212. [Best Books To Learn PostgreSQL - ComputingForGeeks](https://computingforgeeks.com/best-books-to-learn-postgresql-database/)
213. [The favorite four PostgreSQL books - EDB](https://www.enterprisedb.com/blog/top-postgrsql-books-for-learning-dbas-developers)
214. [7 PostgreSQL Books - BookAuthority](https://bookauthority.org/books/best-postgresql-books)

### 其他重要资源
215. [How do I import modules in PostgreSQL 9.1+ - Stack Overflow](https://stackoverflow.com/questions/9025515/how-do-i-import-modules-or-install-extensions-in-postgresql-9-1)
216. [How do I import modules in Postgres - Stack Overflow](https://stackoverflow.com/questions/1564056/how-do-i-import-modules-or-install-extensions-in-postgres)
217. [Managing PostgreSQL extensions - GitLab Docs](https://docs.gitlab.com/ee/install/postgresql_extensions.html)
218. [PostgreSQL extension installation best practices - Stack Exchange](https://dba.stackexchange.com/questions/210508/postgresql-extension-installation-best-practices)
219. [TimescaleDB support on cloud platforms - GitHub Issue](https://github.com/timescale/timescaledb/issues/65)
220. [PostgreSQL versions and extensions in DBLab - PostgresAI](https://postgres.ai/docs/database-lab/supported-databases)

## 学习目标

完成本章学习后，你将能够：

1. **理解扩展机制**：掌握 PostgreSQL 扩展的原理和架构
2. **管理扩展生命周期**：熟练安装、配置、升级和卸载扩展
3. **选择合适的扩展**：根据业务需求选择和评估扩展
4. **使用核心扩展**：掌握常用扩展的配置和使用
5. **开发自定义扩展**：能够使用 C 或 Rust 开发简单扩展
6. **优化扩展性能**：了解扩展对性能的影响和优化方法
7. **处理兼容性问题**：解决版本升级和平台迁移中的扩展问题
8. **构建扩展生态**：理解扩展生态系统和最佳实践

## 初学者可能关心的问题

1. 什么情况下需要使用扩展？
2. 如何判断一个扩展是否可靠？
3. 扩展会影响数据库性能吗？
4. 如何在不同环境中保持扩展一致性？
5. 扩展升级会影响现有数据吗？
6. 如何监控扩展的运行状态？
7. 不同云平台的扩展支持有何差异？
8. 如何开发和发布自己的扩展？

## 小结

PostgreSQL 的扩展机制是其最强大的特性之一，通过扩展，PostgreSQL 可以转变为时序数据库、向量数据库、图数据库、分布式数据库等各种专用数据库，同时保持核心的稳定性和兼容性。本章全面介绍了扩展的概念、管理、使用和开发，帮助你充分利用 PostgreSQL 庞大的扩展生态系统，构建满足各种业务需求的数据库解决方案。