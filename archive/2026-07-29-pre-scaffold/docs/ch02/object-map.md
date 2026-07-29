---
title: "2.2 四层地图：从全局到对象"
weight: 220
math: true
breadcrumbs: false
---

## 本节要解决的问题

我知道很多术语，但不清楚 `集群/数据库/模式/表` 到底是什么关系，遇到同名对象也容易混乱。

## 四层地图（先建立统一坐标系）

先记住一条主线：

`实例(集群) -> 数据库 -> 模式(schema) -> 表`

- 实例/集群：PostgreSQL 服务器进程管理的整体对象空间。
- 数据库：同一实例中的逻辑隔离单元。
- 模式：数据库里的命名空间。
- 表：真正承载业务数据的对象。

## 把抽象层级映射到当前环境

### 1) 看当前实例里有哪些数据库

```sql
SELECT datname
FROM pg_database
WHERE datistemplate = false
ORDER BY 1;
```

### 2) 看当前数据库里有哪些模式

```sql
SELECT nspname
FROM pg_namespace
WHERE nspname NOT LIKE 'pg\_%' ESCAPE '\\'
  AND nspname <> 'information_schema'
ORDER BY 1;
```

### 3) 看模式里有哪些业务表

```sql
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
```

## 同名对象为什么不冲突

因为模式是命名空间。`app.task` 和 `public.task` 可以同时存在。

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.task(id bigint);
CREATE TABLE IF NOT EXISTS public.task(id bigint);

SELECT 'app.task' AS obj, count(*) FROM app.task
UNION ALL
SELECT 'public.task' AS obj, count(*) FROM public.task;
```

> [!NOTE]
> 在实战中，建议关键 SQL 都写成 `schema.table` 全名，避免被 `search_path` 影响。

## 画出你的第一张对象树

建议把当前环境整理成一页文本图，后面每章都复用：

```text
实例/集群
└── meta（数据库）
    ├── app（模式）
    │   └── task（表）
    └── public（模式）
```

## 本节产出物

- 一份数据库清单
- 一份模式清单
- 一份对象树（文本或图）

## 与下一节衔接

对象层级已经明确，下一节开始主线案例 `todo_app`，把地图变成可执行业务对象。

## 延伸阅读

- [系统目录 pg_database](https://www.postgresql.org/docs/current/catalog-pg-database.html)
- [系统目录 pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)
- [Schema 与命名空间](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [老彭：PostgreSQL 好处都有啥](https://vonng.com/cn/blog/db/pg-is-good/)
