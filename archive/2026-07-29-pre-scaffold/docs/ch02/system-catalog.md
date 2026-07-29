---
title: "2.5 系统目录视角：对象不是黑箱"
weight: 250
math: true
breadcrumbs: false
---

## 本节要解决的问题

我创建了 `app.task`，PostgreSQL 内部怎么识别它？怎么确认对象类型、所在模式、列结构、索引状态？

## 什么是系统目录

系统目录（`pg_catalog`）是 PostgreSQL 自己维护的“对象元数据仓库”。

你在 GUI 里看到的很多对象信息，本质上都来自这些目录表。

## 模板 1：对象定位（模式 + 名称 + 类型）

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS relkind,
    c.oid     AS object_oid
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'app'
  AND c.relname = 'task';
```

`relkind` 常见取值：

- `r`：普通表
- `i`：索引
- `v`：视图
- `m`：物化视图

## 模板 2：查看列定义

```sql
SELECT
    a.attnum,
    a.attname,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull
FROM pg_attribute a
WHERE a.attrelid = 'app.task'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

## 模板 3：查看索引定义

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'task'
ORDER BY 1;
```

## 为什么这对实战重要

- 排查“表到底有没有建成功”。
- 排查“对象是不是建在预期 schema”。
- 排查“列类型或索引是否和设计一致”。
- 给后续迁移、审计、回归测试提供事实基线。

## 常见偏差与排查

### 偏差 1：只看 GUI，不会写目录查询

- 风险：工具不可用时无法排障。
- 修正：至少掌握上面 3 条模板 SQL。

### 偏差 2：拿 `information_schema` 当万能入口

- 说明：`information_schema` 偏标准化，字段细节不如 `pg_catalog` 完整。
- 修正：业务排障优先使用 `pg_catalog`。

## 本节产出物

- 一套 `对象定位/列信息/索引信息` 查询模板
- `app.task` 的元数据快照结果

## 与下一节衔接

对象可观测之后，下一节补上协作边界：谁可以查，谁可以改。

## 延伸阅读

- [系统目录总览](https://www.postgresql.org/docs/current/catalogs.html)
- [pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html)
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html)
- [pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html)
- [老彭：PostgreSQL 技术内幕（PG Internal）](https://pgint.vonng.com/ch1/)
