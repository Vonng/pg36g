---
title: "6. 立木取信：开发规约与评审清单"
weight: 600
math: true
breadcrumbs: false
---

> [!Warn] 本章为 AI 生成的头脑风暴草稿目录，尚未编写，请务必注意。

## 章节概述

规约是团队智慧的结晶，是从无数成功和失败经验中提炼出的最佳实践。本章将系统性地介绍 PostgreSQL 开发的各类规约和标准，涵盖命名规范、SQL 编码标准、性能优化原则、安全实践等方面，帮助团队建立统一的开发规范，提高代码质量，降低维护成本，避免常见陷阱。

## 学习目标

- 掌握数据库对象的命名规范和约定
- 学习 SQL 编码的最佳实践和风格指南
- 理解数据库设计的原则和反模式
- 掌握性能优化的规约和方法论
- 熟悉安全开发的原则和实践
- 建立团队的开发规范体系

## 章节大纲

### 6.1 命名规范与约定
- 数据库与模式命名
  - 使用小写字母和下划线
  - 避免保留字和特殊字符
  - 业务域前缀策略
- 表与视图命名
  - 表名使用复数形式
  - 视图前缀：v_、mv_、tmp_
  - 分区表命名规则
- 列命名标准
  - 标准后缀：_id、_at、_by、_count
  - 布尔字段：is_、has_、can_
  - 时间字段：created_at、updated_at
- 索引与约束命名
  - 主键：表名_pkey
  - 唯一索引：表名_列名_key
  - 普通索引：表名_列名_idx
  - 外键：表名_引用表名_fkey
- 函数与存储过程命名
  - 动作前缀：get_、set_、check_
  - 参数命名与冲突处理
  - 版本管理策略

### 6.2 SQL 编码标准
- 格式化与缩进
  - 关键字大写规范
  - 合理的换行与缩进
  - 子查询对齐原则
- 查询编写规范
  - SELECT 列明确化
  - 避免 SELECT *
  - JOIN 显式化
  - WHERE 条件顺序
- DML 操作规范
  - INSERT 列明确指定
  - UPDATE 加 WHERE 限制
  - DELETE 谨慎使用
  - UPSERT 冲突处理
- 事务使用规范
  - 事务粒度控制
  - 避免长事务
  - 合理设置隔离级别
  - 死锁预防策略

### 6.3 数据类型选择规约
- 优先使用专门类型
  - inet vs varchar for IP
  - UUID vs bigserial
  - JSONB vs text for JSON
  - 枚举 vs 字符串
- 数值类型选择
  - 整数类型大小选择
  - 货币使用 numeric
  - 避免浮点数陷阱
- 时间类型规范
  - timestamptz vs timestamp
  - 统一时区处理
  - interval 使用场景
- 文本类型选择
  - text vs varchar
  - 字符集与排序规则
  - 大对象存储策略

### 6.4 索引设计规约
- 索引创建原则
  - 选择性评估
  - 复合索引顺序
  - 覆盖索引设计
  - 部分索引应用
- 索引类型选择
  - B-Tree 适用场景
  - GIN for JSONB/Array
  - BRIN for 时序数据
  - GiST for 地理数据
- 索引维护规范
  - 定期 REINDEX
  - 监控索引膨胀
  - 清理无用索引
  - 并发索引创建

### 6.5 约束与完整性
- 主键设计原则
  - 自然键 vs 代理键
  - UUID vs 自增序列
  - 复合主键考量
- 外键使用规范
  - 级联操作设置
  - 延迟约束检查
  - 性能影响评估
- 检查约束最佳实践
  - 业务规则实现
  - 约束命名规范
  - 约束文档化
- 唯一约束设计
  - NULL 值处理
  - 部分唯一索引
  - 并发插入考虑

### 6.6 查询优化规约
- 查询编写原则
  - 避免笛卡尔积
  - 合理使用子查询
  - CTE vs 子查询选择
  - 窗口函数应用
- 性能优化技巧
  - EXPLAIN 分析习惯
  - 统计信息维护
  - 查询改写技巧
  - 并行查询配置
- 分页查询规范
  - LIMIT/OFFSET 问题
  - 游标分页方案
  - Keyset 分页实现
- 批量操作优化
  - 批量插入策略
  - COPY vs INSERT
  - 批量更新技巧

### 6.7 函数与存储过程规约
- 函数设计原则
  - 单一职责原则
  - 参数验证规范
  - 错误处理机制
  - 返回值约定
- PL/pgSQL 编码规范
  - 变量命名规则
  - 异常处理模式
  - 日志记录策略
  - 性能考量点
- 函数安全性
  - SECURITY DEFINER 使用
  - SQL 注入防范
  - 权限最小化
- 版本管理
  - 函数版本策略
  - 向后兼容性
  - 部署流程规范

### 6.8 安全开发实践
- SQL 注入防范
  - 参数化查询
  - 输入验证
  - 最小权限原则
- 数据加密
  - 传输加密（SSL/TLS）
  - 存储加密策略
  - 敏感数据处理
- 审计与日志
  - 审计日志配置
  - 敏感操作记录
  - 日志保护策略
- 访问控制
  - 角色设计原则
  - 行级安全策略
  - 列级权限控制

### 6.9 性能规约
- 连接管理
  - 连接池配置
  - 连接数限制
  - 空闲连接处理
- 资源使用限制
  - work_mem 设置
  - statement_timeout
  - lock_timeout 配置
- 维护操作规范
  - VACUUM 策略
  - ANALYZE 频率
  - REINDEX 时机
  - 统计信息更新
- 监控指标
  - 关键性能指标
  - 告警阈值设定
  - 容量规划指南

### 6.10 开发流程规约
- 版本控制
  - 数据库变更管理
  - Schema 版本化
  - 迁移脚本规范
- 代码审查
  - SQL 审查要点
  - 性能影响评估
  - 安全检查清单
- 测试规范
  - 单元测试策略
  - 集成测试要求
  - 性能测试标准
  - 数据准备规范
- 部署流程
  - 蓝绿部署策略
  - 回滚方案设计
  - 监控验证步骤

### 6.11 文档规范
- 数据字典维护
  - 表结构文档
  - 字段说明规范
  - 关系图绘制
- API 文档
  - 函数接口说明
  - 参数与返回值
  - 使用示例
- 运维文档
  - 部署手册
  - 故障处理指南
  - 性能调优记录

### 6.12 团队协作规约
- 开发环境管理
  - 环境隔离策略
  - 数据脱敏规范
  - 权限分配原则
- 代码评审制度
  - 评审检查清单
  - 评审流程规范
  - 问题跟踪机制
- 知识分享
  - 最佳实践总结
  - 问题案例分析
  - 技术分享机制

## 实施建议

### 规约落地步骤
1. **评估现状** - 审查现有代码和流程
2. **制定标准** - 根据团队情况定制规约
3. **工具支持** - 引入自动化检查工具
4. **培训推广** - 组织团队学习和讨论
5. **渐进实施** - 新项目严格执行，老项目逐步改造
6. **持续改进** - 定期回顾和更新规约

### 工具链建设
- SQL 格式化工具：pgFormatter
- 静态分析工具：plpgsql_check
- 性能分析工具：pg_stat_statements
- 版本管理工具：Flyway、Liquibase
- 文档生成工具：SchemaSpy

## 常见反模式

1. **EAV 模式滥用** - 过度使用实体-属性-值模式
2. **过度范式化** - 导致过多 JOIN 操作
3. **忽视 NULL 值** - NULL 在逻辑运算中的特殊行为
4. **滥用触发器** - 复杂业务逻辑放在触发器中
5. **忽视时区问题** - timestamp without timezone 的陷阱
6. **过度索引** - 创建大量无用索引

## 参考资料

### 官方指南
- [PostgreSQL 编码约定](https://www.postgresql.org/docs/current/source-conventions.html)
- [PostgreSQL 文档风格指南](https://www.postgresql.org/docs/current/docguide-style.html)
- [SQL 标准符合性](https://www.postgresql.org/docs/current/features.html)

### 行业标准
- [SQL Style Guide](https://www.sqlstyle.guide/)
- [Database Naming Conventions](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)
- [ISO/IEC SQL Standards](https://www.iso.org/standard/63555.html)

### Vonng 博客相关文章
- [PostgreSQL 规约（PG16）](https://vonng.com/cn/blog/db/pg-convention/)
- [PostgreSQL 开发规约详解](https://vonng.com/cn/blog/db/pg-naming-convention/)
- [数据库设计最佳实践](https://vonng.com/cn/blog/db/db-design-practice/)
- [PostgreSQL 性能优化规约](https://vonng.com/cn/blog/db/pg-performance-convention/)

### 社区最佳实践
- [PostgreSQL Wiki - Best Practices](https://wiki.postgresql.org/wiki/Category:Best_Practices)
- [PostgreSQL Anti-patterns](https://wiki.postgresql.org/wiki/Don%27t_Do_This)
- [Database Style Guide](https://www.databasestar.com/database-style-guide/)
- [Modern SQL Style Guide](https://modern-sql.com/style)

### 企业实践案例
- [GitLab Database Guidelines](https://docs.gitlab.com/ee/development/database/)
- [Uber Engineering Standards](https://eng.uber.com/postgres-engineer-standards/)
- [Shopify PostgreSQL Guidelines](https://shopify.engineering/postgresql-at-scale-database-schema-design-principles)

### 工具与框架
- [pgFormatter - SQL 格式化](https://github.com/darold/pgFormatter)
- [plpgsql_check - 静态分析](https://github.com/okbob/plpgsql_check)
- [pgTAP - 单元测试框架](https://pgtap.org/)
- [SchemaSpy - 文档生成](http://schemaspy.org/)

### 书籍推荐
- 《SQL 反模式》
- 《高性能 SQL 调优》
- 《数据库设计规范》
- 《PostgreSQL 开发者指南》

### 培训资源
- [PostgreSQL 开发最佳实践课程](https://www.postgresql.org/training/)
- [SQL 编码规范培训](https://www.w3schools.com/sql/sql_syntax.asp)
- [数据库设计原则](https://www.coursera.org/learn/database-design)

### 检查清单
- [PostgreSQL 部署检查清单](https://github.com/jberkus/annotated.conf)
- [SQL 代码审查清单](https://www.databasestar.com/sql-code-review-checklist/)
- [性能优化检查清单](https://wiki.postgresql.org/wiki/Performance_Optimization_Checklist)

## 本章小结

规约不是教条，而是经验的传承和智慧的积累。一个好的开发规约体系，能够帮助团队避免重复踩坑，提高开发效率，保证代码质量。本章介绍的各类规约涵盖了 PostgreSQL 开发的方方面面，从命名规范到性能优化，从安全实践到团队协作。

重要的是，规约需要因地制宜，根据团队的实际情况进行调整和完善。规约的执行也需要循序渐进，通过工具支持、代码审查、持续改进等机制，让规约真正落地并发挥作用。

记住，最好的规约是团队共同认可并愿意遵守的规约。通过建立和完善开发规约，我们可以构建更加健壮、高效、可维护的数据库系统。至此，筑基篇的学习告一段落，下一部分我们将进入应用篇，探索 PostgreSQL 在实际项目中的高级应用。