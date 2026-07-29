---
title: "2.4 一次可撤销的变更"
weight: 240
math: true
breadcrumbs: false
---

## 本节要解决的问题

数据改了以后，怎么确认“可以撤销且确实撤销成功”？

## 目标

先不讲复杂事务理论，只做一个最小闭环：

`BEGIN -> UPDATE -> 对照查询 -> ROLLBACK -> 对照查询`

## 显式事务最小闭环

```sql
SELECT id, title, done FROM app.task WHERE id = 1;

BEGIN;
UPDATE app.task SET done = true WHERE id = 1;
SELECT id, title, done FROM app.task WHERE id = 1;
ROLLBACK;

SELECT id, title, done FROM app.task WHERE id = 1;
```

你应该看到：

- 事务中：`done = true`
- 回滚后：恢复到事务前状态

## 进阶：用 SAVEPOINT 做局部回滚

```sql
BEGIN;
UPDATE app.task SET done = true WHERE id = 1;
SAVEPOINT s1;

UPDATE app.task SET title = 'wrong title' WHERE id = 1;
SELECT id, title, done FROM app.task WHERE id = 1;

ROLLBACK TO s1;
SELECT id, title, done FROM app.task WHERE id = 1;

COMMIT;
```

这个流程用于演示：同一事务里可以撤销“后半段变更”，保留前半段。

## 如何验证不是“幻觉”

- 验证前：先查一遍初始值。
- 验证中：事务内再查一遍。
- 验证后：回滚/提交后再查一遍。
- 三次结果必须形成清晰对照。

## WAL 在这里扮演什么角色（点到为止）

你可以先把 WAL 理解为“变更记录日志”。

- `COMMIT` 时，事务结果要进入持久化路径。
- `ROLLBACK` 时，当前事务改动对外不可见。

本章不展开内部实现，后续章节再深入。

## 常见偏差与排查

### 偏差 1：忘记显式 `BEGIN`

- 结果：每条语句自动提交，无法整体回滚。
- 修正：涉及多步变更时，先写 `BEGIN`。

### 偏差 2：把 `COMMIT` 和 `ROLLBACK` 混用

- 结果：以为回滚了，实际已经提交。
- 修正：事务结束语句只保留一种，且写在最后一步。

## 本节产出物

- 一份“变更前/变更中/变更后”对照记录
- 一份 SAVEPOINT 局部回滚演示记录

## 与下一节衔接

下一节切到系统目录视角，回答“业务对象在数据库里是如何登记和识别的”。

## 延伸阅读

- [BEGIN](https://www.postgresql.org/docs/current/sql-begin.html)
- [ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html)
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html)
- [事务隔离与可见性](https://www.postgresql.org/docs/current/transaction-iso.html)
- [老彭：PG 先写脏页还是先写 WAL？](https://vonng.com/cn/blog/db/pg-wal-page-seq/)
