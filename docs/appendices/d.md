---
title: 附录 D：分区能力索引
linkTitle: 附录 D 分区能力索引
weight: 40
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

分区不是一个孤立功能：是否该用、查询能否裁剪、如何在线迁移、时间边界怎样表达、
旧分区如何冻结/退役，分布在五个章节。本附录把它们串成一条生命周期。

## D.1 ch04：分区决策门 {#appendix-d-1}

[ch04.6](/data-types-constraints/06/) 先问：

```text
dominant lifecycle boundary?
queries usually constrain the same key?
retention/archive needs cheap detach/drop?
maintenance can benefit from smaller independent relations?
number and creation rate of partitions remain bounded?
```

不要因为“表会变大”自动分区。分区会增加：

- parent/child catalog、DDL、statistics 与 plan 开销；
- partition creation/retention automation；
- constraint/unique/FK 设计限制；
- prepared/generic plan 与参数裁剪不确定性；
- cross-partition query/index/maintenance 复杂度；
- migration、default partition 和 late-arriving data 处理。

### key 选择

| 策略 | 适合 | 风险 |
|---|---|---|
| RANGE(time/id) | 时间生命周期、递增范围 | hot partition、时区/边界、未来 partition |
| LIST(tenant/region/state) | 少量稳定离散域 | key 增长、skew、default 膨胀 |
| HASH(key) | 均匀分布/并行维护 | 生命周期语义弱、重分片成本 |
| multi-level | 同时有生命周期与隔离 | partition 数和运维复杂度乘积 |

使用 `[start, end)` 边界，显式时区与 catch-all/拒绝策略。parent-level `PRIMARY KEY` /
`UNIQUE` 必须满足当前 PostgreSQL 对 partition key 的要求；不能假设多个本地索引自动
提供任意全局唯一性。

### 决策交付物

```yaml
decision: partition | do-not-partition | revisit
key_and_method:
business_and_retention_boundary:
query_predicates:
partition_count_now_and_horizon:
unique_fk_constraints:
late_and_future_data:
automation_owner:
evidence:
revisit_trigger:
```

## D.2 ch07：规划时/执行时裁剪与父表统计 {#appendix-d-2}

[ch07.4](/query-plans-statistics/04/) 用 `EXPLAIN` 区分：

```text
plan-time pruning
  常量/可折叠表达式在规划时排除 partition

execution-time pruning
  parameter/nested-loop value 在 executor 初始化或运行阶段排除
```

检查：

```sql
SHOW enable_partition_pruning;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE)
SELECT ...
FROM partitioned_parent
WHERE partition_key >= $1
  AND partition_key <  $2;
```

关注：

```text
Subplans Removed
loops = 0
实际访问的 child relation
parent/child row estimates
planning time and partition count
```

### 常见裁剪失败

- predicate 没落在 partition key；
- 隐式 cast、时区或函数阻止匹配；
- wrapper/表达式与 partition bound 不同；
- generic/custom prepared plan 行为不同；
- join value 只能在执行阶段知道；
- default partition 覆盖过大；
- 误把 constraint exclusion 与 declarative pruning 混为一谈。

“查询结果快”不证明裁剪；小数据可能全扫仍快。保存 plan、参数、table definition、
statistics 和 server version。

### statistics

parent/child 的 statistics、autovacuum/analyze 与增量数据分布可能不同。检查：

```text
parent estimates vs actual
hot/current child statistics freshness
partition key and correlated columns
default partition skew
newly attached partition analyze state
```

不要只在一个 child `ANALYZE` 后推断 parent workload 已正确估算。

## D.3 ch11：在线分区化 {#appendix-d-3}

[ch11.4](/schema-change-release/04/) 把“改成分区表”当迁移项目：

```text
expand
  create partitioned parent, children, indexes, constraints

migrate
  backfill bounded ranges; capture concurrent delta

validate
  counts/digests/constraints/query plans/replica lag

cut over
  bounded lock; route old/new application versions

contract
  stop dual path; retain rollback; retire old table
```

PostgreSQL 不能把普通表原地无成本变成 partitioned parent。迁移策略可用新表、shadow
write、logical change capture、短暂停写或 `ATTACH PARTITION`，但每种都要重新验证
锁、WAL、trigger/FK、sequence、replica 和 rollback。

### `ATTACH PARTITION`

若待 attach 表已有能证明 bound 的匹配 `CHECK` constraint，PostgreSQL 可避免为验证
partition constraint 扫描它；具体锁与扫描行为绑定版本与对象状态。default partition
还可能需要验证它不含新 range 数据。执行前：

```text
exact bound and no overlap
matching columns/types/collations
constraints and indexes
no rows outside bound
default partition impact
parent/child concurrent traffic
lock timeout and stop
```

attach 后再验证 parent query、direct child access、privilege、trigger、FK、stats 与
backup/replication。

### dual write 风险

应用双写或 trigger capture 可能产生：

```text
ordering difference
partial commit across systems
duplicate/retry
hidden trigger side effect
sequence drift
old/new schema incompatibility
```

优先同一 transaction 内可验证机制；仍需 source-of-truth、reconciliation 和 cutover
watermark。不要以两个 row count 相等作为唯一证明。

## D.4 ch16：时间分区场景 {#appendix-d-4}

[ch16.2](/spatiotemporal/02/) 先定义时间：

```text
event time       业务事件发生
ingest time      系统接收
effective time   业务事实生效
system time      数据库记录版本
```

partition key 必须匹配主要生命周期和查询。按 ingest time 分区容易接收 late event，
却不一定裁剪 event-time 查询；按 event time 分区需要 future/late/default 策略。

### 边界规则

```text
store timestamptz for global instant
choose one canonical timezone for bounds
use half-open [from, to)
generate future partitions ahead of time
alert before current partition end
define late-arrival and backfill authority
```

不要用本地日期字符串猜 DST 边界。保存实际 bound：

```sql
SELECT
    inhparent::pg_catalog.regclass AS parent,
    inhrelid::pg_catalog.regclass AS child,
    pg_catalog.pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_catalog.pg_inherits AS i
JOIN pg_catalog.pg_class AS c ON c.oid = i.inhrelid
WHERE inhparent = 'schema.parent'::pg_catalog.regclass
ORDER BY child::text;
```

### partition 内索引

时间 range 裁剪减少 child 数，child 内仍要按谓词、排序和 join 选 B-tree/BRIN/GiST 等。
BRIN 依赖物理相关性，不是“时序表默认更快”；空间 + 时间查询还要验证两种 selectivity
如何组合。

## D.5 ch28：分区生命周期、冻结与退役 {#appendix-d-5}

[ch28.7](/vacuum-freeze-bloat/07/) 把 partition state 作为有限状态机：

```text
future -> writable -> sealed -> validated -> archived
       -> detached -> retained -> dropped
```

每次 transition 有：

```yaml
partition:
bound:
state_before:
preconditions:
business_retention:
legal_hold:
backup_or_export:
freeze_and_visibility:
dependent_objects:
action:
validation:
rollback_or_re-attach:
owner:
```

### sealed 不等于无需 vacuum

旧 partition 即使不再业务写入，仍可能需要：

- freeze XID/multixact；
- 清理过去更新留下的 dead tuple；
- 更新 visibility map；
- 完成 index/constraint validation；
- 处理仍引用它的 snapshot/slot/prepared transaction。

观察每个 child 的 age、stats 和 size，不只看 parent aggregate。

### detach/drop 与大 DELETE

按完整 partition 退役通常能避免逐行 DELETE 的大量 WAL/dead tuples，但 DDL 仍有锁、
依赖、replication、backup 与业务风险。先确认：

```text
bound fully outside retention
no legal/audit hold
archive/export is readable
queries no longer require it
FK/view/publication/privilege dependencies understood
exact partition identity
rollback window
```

`DETACH` 后对象仍占空间；`DROP` 才释放 relation，且是不可逆 schema/data action。不要
把 retention policy 直接变成无人审批的自动 drop。

### 五章闭环检查

```text
ch04 decision still valid?
ch07 representative queries prune?
ch11 migration/cutover evidence retained?
ch16 time semantics and late data correct?
ch28 creation/seal/archive/drop automation healthy?
```

任一答案未知，先修生命周期合同，不急于增加 partition 数。

---

[返回附录目录](../) · [对象与证据速查](../b/) ·
[ch04 分区决策门](/data-types-constraints/06/) · [查看全书目录](/toc/)
