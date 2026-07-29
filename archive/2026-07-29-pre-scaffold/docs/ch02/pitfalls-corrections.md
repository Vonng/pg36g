---
title: "常见误区与纠偏"
weight: 300
math: true
breadcrumbs: false
---

## 摘要

本页汇总 ch02 最常见的五个误区，每条都给一个“立刻可执行”的纠偏动作。

## 误区 1：把数据库当最高层

- 偏差：以为“库”就是最大边界，忽略实例与模式。
- 纠偏动作：先执行三条清单 SQL，再开始业务操作。

```sql
SELECT inet_server_addr(), inet_server_port(), current_database();
SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY 1;
SELECT nspname FROM pg_namespace ORDER BY 1;
```

## 误区 2：只会点 GUI，不保留可复现命令

- 偏差：看到了结果，但过程不可复盘。
- 纠偏动作：每个关键动作至少保留 1 条 `psql` 或 SQL 记录。

## 误区 3：默认一直用超级用户

- 偏差：开发便利掩盖权限风险。
- 纠偏动作：执行 `reporter` 只读闭环，强制区分读写身份。

## 误区 4：以为事务“提交了就没法控制”

- 偏差：不会用显式事务做安全试错。
- 纠偏动作：固定演练 `BEGIN -> UPDATE -> ROLLBACK` 对照流程。

## 误区 5：把业务对象当黑箱

- 偏差：对象异常时不会查系统目录。
- 纠偏动作：创建对象后，立即执行一次目录核验。

```sql
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'app' AND c.relname = 'task';
```

## 章节收束检查（建议自测）

- 是否能在 1 分钟内给出连接快照？
- 是否能画出当前对象树？
- 是否能复现一次回滚对照？
- 是否能证明 `reporter` 只读成立？
- 是否能列出已安装扩展并验证 `pg_trgm`？
