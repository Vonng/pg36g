---
title: "ch02 参考资料与延伸阅读"
weight: 320
math: true
breadcrumbs: false
---

## 使用说明

- 先读“官方文档”建立准确口径。
- 再读“老彭文章”补充实战视角。
- 最后读“社区文献”扩展边界与踩坑案例。

## A. 官方文档（优先）

### 连接与会话

- [psql](https://www.postgresql.org/docs/current/app-psql.html)
- [会话信息函数](https://www.postgresql.org/docs/current/functions-info.html)

### 对象层级与模式

- [Schema（模式）](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html)
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)

### 事务与回滚

- [BEGIN](https://www.postgresql.org/docs/current/sql-begin.html)
- [ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html)
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html)
- [事务隔离级别](https://www.postgresql.org/docs/current/transaction-iso.html)

### 系统目录与可观测

- [系统目录总览](https://www.postgresql.org/docs/current/catalogs.html)
- [pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html)

### 角色权限与扩展

- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html)
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html)
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html)
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)

## B. 老彭文章与资料

- [PostgreSQL 规约](https://vonng.com/cn/blog/db/pg-convention/)
- [PG 先写脏页还是先写 WAL？](https://vonng.com/cn/blog/db/pg-wal-page-seq/)
- [并发异常那些事？](https://vonng.com/blog/db/concurrent-anomalies/)
- [PostgreSQL 好处都有啥](https://vonng.com/cn/blog/db/pg-is-good/)
- [PG Internal：第 1 章](https://pgint.vonng.com/ch1/)

## C. 社区文献与实践

- [PostgreSQL Wiki：保护 search_path（CVE-2018-1058）](https://wiki.postgresql.org/wiki/A_Guide_to_CVE-2018-1058:_Protect_Your_Search_Path)
- [PostgreSQL Wiki：Don't Do This](https://wiki.postgresql.org/wiki/Don't_Do_This)

## D. ch02 推荐阅读顺序（45 分钟版）

1. `psql` + 会话信息函数（先把连接上下文跑通）
2. `ddl-schemas` + `pg_namespace`（建立对象地图）
3. `BEGIN/ROLLBACK/SAVEPOINT`（做一遍回滚实验）
4. `pg_class/pg_attribute`（完成对象元数据核验）
5. `CREATE ROLE/GRANT` + Wiki search_path（补权限边界）
6. `CREATE EXTENSION` + `pg_extension`（补能力边界）
