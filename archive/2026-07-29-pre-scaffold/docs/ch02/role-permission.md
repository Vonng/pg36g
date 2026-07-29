---
title: "2.6 支线案例：只读角色闭环"
weight: 260
math: true
breadcrumbs: false
---

## 本节要解决的问题

团队协作时，如何让“只读用户能查数据但不能改数据”？

## 目标

建立一个最小权限闭环：

- 创建只读角色 `reporter`
- 授予最小必要权限
- 验证“查询成功、写入失败”

## 授权前先看权限边界

只读最小集合通常是三层：

- 数据库级：`CONNECT`
- 模式级：`USAGE`
- 表级：`SELECT`

## 执行授权

```sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporter') THEN
    CREATE ROLE reporter LOGIN PASSWORD 'reporter_demo_pwd';
  END IF;
END$$;

GRANT CONNECT ON DATABASE meta TO reporter;
GRANT USAGE ON SCHEMA app TO reporter;
GRANT SELECT ON TABLE app.task TO reporter;
```

## 验证闭环

```sql
SET ROLE reporter;

SELECT current_user, session_user;
SELECT count(*) FROM app.task;

-- 预期失败：权限不足
INSERT INTO app.task(title) VALUES ('should fail');

RESET ROLE;
```

可以再用函数做一次机器可读校验：

```sql
SELECT
  has_database_privilege('reporter', 'meta', 'CONNECT') AS can_connect,
  has_schema_privilege('reporter', 'app', 'USAGE')      AS can_use_schema,
  has_table_privilege('reporter', 'app.task', 'SELECT') AS can_select,
  has_table_privilege('reporter', 'app.task', 'INSERT') AS can_insert;
```

预期结果：前三项 `true`，最后一项 `false`。

## 可选：未来新表默认只读授权

如果你后续会在 `app` 下持续建表，可以提前配置默认权限：

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA app
GRANT SELECT ON TABLES TO reporter;
```

> [!NOTE]
> `ALTER DEFAULT PRIVILEGES` 只影响“之后新建”的对象，不回溯历史对象。

## 常见偏差与排查

### 偏差 1：只给了 `SELECT`，忘了 `CONNECT` 或 `USAGE`

- 症状：角色无法正常访问对象。
- 修正：按“数据库 -> 模式 -> 表”顺序授权。

### 偏差 2：直接用超级用户做业务连接

- 风险：误操作影响面大，审计困难。
- 修正：业务连接使用最小权限角色。

## 本节产出物

- 一份最小权限矩阵（角色 -> 权限 -> 结果）
- 一份验证日志（成功查询 + 失败写入）

## 与下一节衔接

权限边界明确后，最后一节收束“内建能力与扩展能力”边界，并交接给 ch03 工具链。

## 延伸阅读

- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html)
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [PostgreSQL Wiki：CVE-2018-1058 与 search_path](https://wiki.postgresql.org/wiki/A_Guide_to_CVE-2018-1058:_Protect_Your_Search_Path)
- [老彭：PostgreSQL 规约](https://vonng.com/cn/blog/db/pg-convention/)
