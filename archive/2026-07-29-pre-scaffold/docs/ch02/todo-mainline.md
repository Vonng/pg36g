---
title: "2.3 主线案例启动：todo_app"
weight: 230
math: true
breadcrumbs: false
---

## 本节要解决的问题

我如何在四层地图上快速落地一个“最小可用”业务对象，并让它可验证、可复现、可回滚？

## 主线范围

本章主线只保留一个对象：`app.task`。

- 不引入复杂表关系
- 不引入 ORM
- 先跑通数据库动作闭环

## 第一步：创建业务模式与表

```sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.task (
    id          bigserial PRIMARY KEY,
    title       text        NOT NULL,
    done        boolean     NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    done_at     timestamptz
);
```

## 第二步：写入样例数据

```sql
INSERT INTO app.task(title)
VALUES
    ('setup sandbox'),
    ('write ch02'),
    ('review output')
RETURNING id, title, done, created_at;
```

## 第三步：读取与核对

```sql
SELECT id, title, done, done_at, created_at
FROM app.task
ORDER BY id;
```

## 第四步：做一次最小更新

```sql
UPDATE app.task
SET done = true, done_at = now()
WHERE id = 2
RETURNING id, title, done, done_at;
```

再核对一次：

```sql
SELECT id, title, done, done_at
FROM app.task
ORDER BY id;
```

## 可选：用 `psql` 看结构

```bash
psql postgres://dbuser_dba@/meta -c '\\d+ app.task'
```

## 本节验收标准

- `app.task` 存在。
- 表内至少有 3 行数据。
- 至少有 1 行完成状态从 `false` 变为 `true`。
- 能稳定执行 `SELECT ... ORDER BY id` 复现结果。

## 常见偏差与排查

### 偏差 1：对象建在 `public` 而不是 `app`

- 排查：`SELECT schemaname, tablename FROM pg_tables WHERE tablename='task';`
- 修正：关键 SQL 强制写 `app.task`。

### 偏差 2：忘记 `RETURNING` 导致无法快速确认结果

- 修正：写入/更新时尽量带 `RETURNING`，减少“是否成功”的不确定性。

## 本节产出物

- `app.task` 建表 SQL
- 初始化数据 SQL
- 一份结果截图/结果文本

## 与下一节衔接

有了可写数据后，下一节用事务把“改动可逆”演示清楚。

## 延伸阅读

- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html)
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html)
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html)
- [老彭：PostgreSQL 规约](https://vonng.com/cn/blog/db/pg-convention/)
