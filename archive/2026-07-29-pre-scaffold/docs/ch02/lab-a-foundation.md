---
title: "实验 A（基础）：全局地图闭环"
weight: 280
math: true
breadcrumbs: false
---

## 目标

在 30-45 分钟内跑通 `todo_app` 主线闭环，产出一份可复现、可审计的全局操作记录。

## 实验范围

只做 5 件事：

1. 连接快照
2. 四层对象地图
3. 主线对象创建与写入
4. 事务回滚验证
5. 系统目录元数据核验

## 前置条件

- 已完成 ch01，能使用 `psql postgres://dbuser_dba@/meta` 连接数据库。
- 当前账号具备建模式/建表权限。

## 标准步骤

### Step 1：记录连接快照

```sql
SELECT
    inet_server_addr(), inet_server_port(),
    current_database(), current_user,
    current_setting('search_path'), pg_backend_pid();
```

### Step 2：列出对象层级

```sql
SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY 1;
SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\_%' ESCAPE '\\' AND nspname <> 'information_schema' ORDER BY 1;
```

### Step 3：创建主线对象并写入样例

```sql
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.task (
  id bigserial PRIMARY KEY,
  title text NOT NULL,
  done boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO app.task(title) VALUES ('setup sandbox'), ('write ch02'), ('review output');
SELECT * FROM app.task ORDER BY id;
```

### Step 4：执行一次显式回滚

```sql
BEGIN;
UPDATE app.task SET done = true WHERE id = 1;
SELECT id, done FROM app.task WHERE id = 1;
ROLLBACK;
SELECT id, done FROM app.task WHERE id = 1;
```

### Step 5：查询系统目录确认对象

```sql
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'app' AND c.relname = 'task';
```

## 验收标准（全部满足为通过）

- `app.task` 存在，且不少于 3 行样例数据。
- 回滚前后 `id=1` 的 `done` 状态可对照恢复。
- 系统目录能查到 `app.task`，`relkind='r'`。
- 产出一份对象树（文本即可）。

## 可提交产出模板

- `连接快照`
- `对象树`
- `主线 SQL`
- `回滚对照`
- `目录查询结果`
