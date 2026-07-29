---
title: "2.7 全局认知收束：能力边界与交接"
weight: 270
math: true
breadcrumbs: false
---

## 本节要解决的问题

PostgreSQL 的能力边界在哪里？哪些是内建能力，哪些是“按需扩展”能力？

## 先建立一条边界线

- 内建能力：安装 PostgreSQL 后默认可用（SQL、事务、权限、系统目录等）。
- 扩展能力：通过 `CREATE EXTENSION` 显式启用（如 `pg_trgm`、`vector`、`postgis`）。

这条边界决定了你后续做技术方案时的依赖管理方式。

## 先看当前环境有什么扩展

```sql
SELECT extname, extversion, extnamespace::regnamespace AS ext_schema
FROM pg_extension
ORDER BY 1;
```

再看“可安装但未安装”的扩展池：

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
ORDER BY name
LIMIT 30;
```

## 做一次最小扩展实践（pg_trgm）

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_trgm';
```

可选验证（调用一个函数证明扩展能力可用）：

```sql
SELECT similarity('postgres', 'postgre');
```

## 如何判断“该不该上扩展”

建议用三条硬规则：

- 业务收益是否明确（性能、能力、开发效率）。
- 运维成本是否可控（升级、兼容、备份恢复）。
- 回退路径是否存在（卸载、替代方案、降级策略）。

## 交付给 ch03 的输入

到这里，你应该已经有一份“可工具化”的动作清单：

- 连接快照命令
- 对象树与主线 SQL
- 事务回滚脚本
- 系统目录查询模板
- 权限验证脚本
- 扩展状态检查脚本

ch03 会把这些动作升级为 `psql` 元命令、脚本、批处理和自动化执行。

## 本节产出物

- 一页 `ch02` 全局操作图（连接、对象、变更、权限、扩展）
- 一份交接清单（供 ch03 直接复用）

## 延伸阅读

- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html)
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html)
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)
- [老彭：PostgreSQL 好处都有啥](https://vonng.com/cn/blog/db/pg-is-good/)
- [PG Internal：系统全景与组件认知](https://pgint.vonng.com/ch1/)
