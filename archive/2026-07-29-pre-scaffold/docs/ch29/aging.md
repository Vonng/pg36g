---
title: "XID 回卷问题处理"
weight: 10
math: true
breadcrumbs: false
---


## XID wraparound 是什么？

PostgreSQL 用 32 位事务号（XID）；旧版本文档常用“约 20 亿（2^31）”阈值来描述危险区。为防止旧行“穿越时空”，系统通过 **冻结（FREEZE）** 把很老的行标记为永远可见，从而允许重用旧 XID。冻结由 `VACUUM` 完成（含 autovacuum 的“防环绕”模式）。



## 常见原因

1. 大写入负载过饱和
2. AutoVacuum 未正确运行
3. AutoVacuum 未正确配置（集群/DB/表）
4. 长事务/长游标持有很老的快照
5. 两阶段提交，长时间未提交
6. 复制阻塞，复制进度不更新，从库反馈
7. MultiXact 积压
8. 系统BUG（如 hypercore）

后面详细介绍每种根因定位与处理的方法。



## 常用SQL

### 检查并清理整个数据库

检查数据库的年龄，以及 MultiXact 年龄（PG13+，如果启用 MultiXact）

```sql
SELECT datname, age(datfrozenxid), mxid_age(datminmxid) FROM pg_database ORDER BY 2 DESC;
```

以最大速度，执行整库 Vacuum。

```bash
SET vacuum_cost_delay = 0;         -- 不间断 VACUUM
SET vacuum_cost_limit = 10000;     -- 最大化 VACUUM 速度
SET maintenance_work_mem = '1GB';  -- 视实例内存调整
VACUUM (FREEZE, VERBOSE) ;         -- 全库（当前 DB）
```

另外也可以使用外部命令 `vacuumdb` 来处理

```bash
# 仅处理“年龄≥X”的最老表，优先清风险
vacuumdb --all --freeze --min-xid-age=50000000 --jobs=4 --verbose
# 如需减少争用，可加 --skip-locked（会跳过拿不到锁的表，谨慎）
```



### 找到年龄最大的表进行清理

找到年龄最大的数据库，进入其中，找出当前数据库中年龄最大的表：

```sql
SELECT n.nspname, c.relname::text AS relname, age(c.relfrozenxid) AS age, mxid_age(c.relminmxid) AS mxid_age,
       pg_size_pretty(pg_table_size(c.oid)) AS tbl_size, st.n_dead_tup, st.last_autovacuum, st.last_vacuum
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace LEFT JOIN pg_stat_all_tables st ON st.relid = c.oid
WHERE c.relkind IN ('r','m') AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY age DESC LIMIT 50;
```

针对单表执行 Vacuum，可以指定并行数量，[有多种参数可选择](https://www.postgresql.org/docs/18/sql-vacuum.html)

```sql
SET vacuum_cost_delay = 0;         -- 不间断 VACUUM
SET vacuum_cost_limit = 10000;     -- 最大化 VACUUM 速度
SET maintenance_work_mem = '1GB';  -- 视实例内存调整
VACUUM (FREEZE, VERBOSE, PARALLEL 2, INDEX_CLEANUP OFF) monitor.heartbeat; -- 替换为你自己的表名
```

与此同时可以查阅 Vacuum 的进度。

```bash
SELECT * FROM pg_stat_progress_vacuum; \watch 1
```







## 分析问题

### 检查AutoVacuum配置是否正常

列出有过表级自定义参数的表，看看是否有表级别的 AutoVacuum 参数覆盖

```sql
SELECT n.nspname, c.relname, c.reloptions
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.reloptions IS NOT NULL;
```


### 检查长事务

查阅 PGSQL XACT 监控面板，或者使用 SQL：

```sql
SELECT pid, usename, xact_start, now()-xact_start AS xact_age, state, query
FROM pg_stat_activity WHERE xact_start IS NOT NULL ORDER BY xact_start;
```

检查复制槽：

```sql
-- 4) 复制槽是否拖住冻结/清理
SELECT slot_name, slot_type, active, xmin, catalog_xmin, restart_lsn
FROM pg_replication_slots
ORDER BY age(coalesce(catalog_xmin, xmin)) DESC NULLS LAST;
```


```bash
SELECT pv.pid, pv.relid::regclass AS relation, pv.phase,
       pv.heap_blks_total, pv.heap_blks_scanned, pv.heap_blks_vacuumed,
       sa.wait_event_type, sa.wait_event, pg_blocking_pids(pv.pid) AS blockers
FROM pg_stat_progress_vacuum pv
JOIN pg_stat_activity sa USING (pid);
```