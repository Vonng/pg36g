---
title: "2.1 我到底连到了什么"
weight: 210
math: true
breadcrumbs: false
---

## 本节要解决的问题

我已经能连接 PostgreSQL，但我不确定当前操作到底落在“哪台实例、哪个数据库、哪个角色、哪个会话上下文”。

## 为什么这一步必须先做

数据库事故里最常见的一类问题不是 SQL 写错，而是“SQL 执行在了错误的上下文”：

- 连错库（测试 SQL 打到生产库）
- 用错角色（只读账号执行写入失败，或超级用户误操作）
- 忽略 `search_path`（以为改的是 `app.task`，实际改了同名对象）

所以在 ch02，我们先固定一套“连接快照”动作。后面所有操作都以这份快照为准。

## 最小连接快照（建议每次开工先执行）

```bash
psql postgres://dbuser_dba@/meta -c '\\conninfo'
```

```sql
SELECT
    now()                                  AS snapshot_time,
    inet_server_addr()                     AS server_addr,
    inet_server_port()                     AS server_port,
    current_database()                     AS db_name,
    current_user                           AS current_role,
    session_user                           AS session_role,
    current_setting('search_path')         AS search_path,
    current_setting('application_name')    AS app_name,
    pg_backend_pid()                       AS backend_pid;
```

## 输出如何解读

- `server_addr/server_port`：确认实例落点。
- `db_name`：确认数据库边界。
- `current_role/session_role`：确认当前权限身份（是否 `SET ROLE` 过）。
- `search_path`：确认未限定 schema 的对象解析顺序。
- `backend_pid`：后续排查锁等待、长事务时用于定位会话。

## 推荐补充动作

如果你是多人协作，建议每次会话开始时设置并记录 `application_name`：

```sql
SET application_name = 'ch02_connection_check';
SHOW application_name;
```

## 常见偏差与排查

### 偏差 1：连错数据库

- 症状：对象查不到，或“看起来数据为空”。
- 排查：先执行 `SELECT current_database();` 再做业务 SQL。

### 偏差 2：角色身份混淆

- 症状：同一 SQL 在不同终端行为不同。
- 排查：对照 `current_user` 与 `session_user`，确认是否切换过角色。

### 偏差 3：`search_path` 污染

- 症状：同名表读写结果异常。
- 排查：`SHOW search_path;`，关键对象强制写全名 `schema.table`。

## 本节产出物

一份“连接快照记录”（建议直接粘到实验日志）：

- 时间
- 实例地址与端口
- 数据库名
- 角色身份
- `search_path`
- `backend_pid`

## 与下一节衔接

连接上下文清楚后，下一节把 `集群 -> 数据库 -> 模式 -> 表` 四层对象关系落到你的实例里。

## 延伸阅读

- [psql 使用手册](https://www.postgresql.org/docs/current/app-psql.html)
- [会话信息函数](https://www.postgresql.org/docs/current/functions-info.html)
- [模式（Schema）与 search_path](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [老彭：PostgreSQL 规约](https://vonng.com/cn/blog/db/pg-convention/)
