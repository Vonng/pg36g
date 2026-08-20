---
title: 附录 B：对象、视图、命令与证据速查
linkTitle: 附录 B 对象、视图、命令与证据速查
weight: 20
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

本附录用于事故前后的快速定位，不替代正文中的机制、权限与风险判断。所有视图和命令
按 PostgreSQL 18 / Pigsty v4.4 基线列出；跨版本先查[附录 A](../a/)。

## B.1 连接、角色、对象、事务、锁和计划 {#appendix-b-1}

### 身份与对象

| 问题 | 首选证据 | 注意 |
|---|---|---|
| 连到哪个 server | `inet_server_addr/port()`、`version()` | Unix socket 时地址/端口可为 `NULL` |
| 哪个 database/role | `current_database()`、`current_user`、`session_user` | role 是 cluster-wide，database 不是 |
| 对象从哪解析 | `SHOW search_path`、`current_schemas(true)` | 临时 schema 与 `$user` 会改变结果 |
| 是否 recovery | `pg_is_in_recovery()` | 不能单独证明 route/authority |
| 哪个 schema/object | `pg_class` + `pg_namespace`、`regclass` | 名称需 schema-qualified |
| 对象 owner/ACL | `pg_get_userbyid(relowner)`、`\dp`、`aclexplode` | owner、membership、grant 要合并判断 |
| extension 已安装 | `pg_extension` | 不等同于 `pg_available_extensions` |

最小 identity：

```sql
SELECT
    current_database(),
    current_user,
    session_user,
    inet_server_addr(),
    inet_server_port(),
    pg_is_in_recovery(),
    current_setting('server_version_num');
```

`psql`：

| 命令 | 用途 |
|---|---|
| `\conninfo` | 当前连接摘要 |
| `\l+` / `\dn+` | database / schema |
| `\dtS+ pattern` / `\diS+ pattern` | table / index |
| `\d+ schema.object` | 对象定义摘要 |
| `\df+ pattern` / `\dx+` | function / extension |
| `\du+` / `\dp` | role / ACL |
| `\gdesc` | 只描述结果列，不执行取数 |
| `\gx` | expanded result |

元命令适合交互探索；可审计脚本应同时保存等价 catalog query、目标 identity 和版本。

### 会话、事务与锁

| 问题 | 视图/函数 | 关键列 |
|---|---|---|
| 谁在运行/等待 | `pg_stat_activity` | `pid`、`backend_type`、`state`、`wait_event_type/event`、`xact_start` |
| 谁阻塞 PID | `pg_blocking_pids(pid)` | 结果是 blocker PID 数组 |
| 持有哪些锁 | `pg_locks` | `locktype`、对象 identity、`mode`、`granted` |
| prepared transaction | `pg_prepared_xacts` | `transaction`、`prepared`、`owner`、`database` |
| 当前 backend XID/XMIN | `pg_stat_activity` | `backend_xid`、`backend_xmin` |
| 数据库事务计数 | `pg_stat_database` | counter 受 stats reset 影响 |

等待链骨架：

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    pg_catalog.pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

query text 可能含敏感数据、被截断或因权限不可见。取消/终止 backend 是有副作用动作，
先绑定 exact PID + backend start + application/user/database + expected/stop。

### 计划与语句

| 工具 | 能回答 | 不能单独回答 |
|---|---|---|
| `EXPLAIN` | planner 估算和选路 | 实际时间、cache/I/O |
| `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)` | 实际执行与资源投影 | 全部并发/OS/历史上下文 |
| `pg_stat_statements` | 聚合 workload | 单次 timeline、未归一化业务语义 |
| `auto_explain` | 被采样语句计划 | 完整 workload；有 logging 开销 |
| `pg_stat_io` | backend/object context I/O 计数 | device latency 的全部机理 |

`ANALYZE` 选项会真的执行语句；对 `INSERT/UPDATE/DELETE/MERGE` 或 volatile function，
先在可回滚/隔离环境设计，不要对生产写语句直接照抄。正文：
[ch07](/query-plans-statistics/)、[ch08](/slow-query-diagnosis/)、
[ch09](/index-design/)、[ch10](/concurrency-isolation/)。

## B.2 复制、备份、vacuum、WAL 与容量 {#appendix-b-2}

### 复制、权威与 WAL

| 问题 | 证据 | 关键边界 |
|---|---|---|
| primary 看 replicas | `pg_stat_replication` | 一行是 walsender，不自动等于业务健康 |
| standby 看 receiver | `pg_stat_wal_receiver` | source/LSN/status |
| slot 保留什么 | `pg_replication_slots` | `slot_type`、`active`、`xmin`、`catalog_xmin`、`restart_lsn` |
| subscription 状态 | `pg_stat_subscription*` | logical replication 语义不同 |
| archive 是否推进 | `pg_stat_archiver` + repository | counter 与实际可恢复性不同 |
| WAL 位置差 | `pg_current_wal_lsn()` / replay/receive LSN | byte lag 不是 time/RPO |
| timeline/system id | control data、Patroni/DCS、backup metadata | 不公开 raw identifier 时保存一致性投影 |

不要手工删除 `pg_wal`。WAL 撑盘先判 archive、slot、replica、backup/restore owner；见
[ch34](/overload-resource-incidents/) 与[附录 C](../c/)。

### backup 与 restore

| 证据 | 用途 |
|---|---|
| `pgbackrest info` | backup set、timeline、size、status |
| `pgbackrest check` | stanza/repository/archive 基础检查 |
| backup/repository manifest | source、hash、retention |
| isolated restore output | 实际可读性与阶段时间 |
| PostgreSQL control + SQL identity | 恢复后的 lineage/target |
| business manifest | 业务 cutoff 与不变量 |

“最近 backup success”不等于能在目标 RTO 内恢复，也不证明正确 target。恢复必须在隔离
candidate 验证；见 [ch21](/backup-recovery/) 与 [ch32](/pitr/)。

### vacuum、freeze 与膨胀

| 问题 | 证据 |
|---|---|
| table maintenance | `pg_stat_all_tables`、`pg_stat_progress_vacuum` |
| relation age | `age(relfrozenxid)`、`mxid_age(relminmxid)` |
| database age | `age(datfrozenxid)` |
| blockers | `pg_stat_activity.backend_xmin`、slot xmin/catalog_xmin、prepared xacts |
| dead/live estimates | `n_dead_tup`、`n_live_tup`（估算） |
| relation bytes | `pg_relation_size`、`pg_total_relation_size` |
| index validity/use | `pg_index`、`pg_stat_all_indexes`、`amcheck` |

膨胀不是单一准确 counter。stats 是估算且可 reset；结合 page/sample/extension 工具时
记录版本、锁和开销。见 [ch28](/vacuum-freeze-bloat/)。

### 容量与配置

```text
work arrival / concurrency / queue
CPU run and saturation
memory budget and OOM/swap
I/O latency, throughput and queue
connections and per-operation memory
WAL/archive/replication retention
XID/multixact age
data/index/temp/log/backup storage
```

PostgreSQL：

| 证据 | 说明 |
|---|---|
| `pg_settings` | value、unit、source、context、pending_restart |
| `pg_stat_database` | database workload counters |
| `pg_stat_wal` / `pg_stat_bgwriter` / `pg_stat_checkpointer` | WAL/checkpoint/background write |
| `pg_stat_io` | backend/object/context I/O |
| `pg_stat_activity` | sessions、transactions、wait |
| `pg_stat_progress_*` | 部分长任务进度 |

同时采样 OS `vmstat`、`iostat`、`pidstat`/cgroup/host metrics。数据库 counter 不能解释
所有 kernel/device 行为。见 [ch25](/observability/)～[ch27](/configuration-tuning/)。

## B.3 每项命令的风险等级、适用范围和验证方式 {#appendix-b-3}

### 先填 action card

```yaml
target:
  environment:
  cluster/system:
  instance/database/object/session:
risk: R0 | R1 | R2 | R3
authority:
preconditions:
expected:
stop:
rollback_or_recovery:
before_evidence:
after_evidence:
```

| 风险 | 定义 | 示例类别 | 最低要求 |
|---|---|---|---|
| R0 观察 | 不改变目标状态 | identity、catalog/stat、plan without ANALYZE | exact context、成本/隐私边界 |
| R1 可逆变更 | 改对象/配置/流量，有验证过的回退 | fixture DDL、reload、bounded cancel、canary | owner、scope、before/after、rollback |
| R2 受控状态变更/演练 | 有非平凡状态影响，但范围隔离且恢复路径已验证 | 精确 cancel、一次性对象删除、隔离 PITR/failover、byte fault | guard、批准、恢复源、停止线、证据 |
| R3 生产敏感/潜在不可逆 | 触及真实数据/流量、authority/lineage，或恢复昂贵 | 生产 failover/cutover、rewind/reinit、host rebuild、`pg_resetwal` | 原件保留、明确授权、独立复核、业务验收 |

风险由**目标与后果**决定，不由命令长短决定。同一 PITR 机制在一次性隔离 candidate
上可为 R2，切换生产 authority 或覆盖真实目标时应升为 R3。`SELECT` 可调用 volatile/security
definer function；`EXPLAIN ANALYZE` 可执行写入；`VACUUM FULL`、`REINDEX`、DDL 和
playbook 可能持锁、重写、重启或改变路由。

### 常见动作速查

| 动作 | 通常风险 | 前置 | after |
|---|---|---|---|
| catalog/stat query | R0 | role、database、query cost | timestamp、rows、source |
| `ANALYZE` | R1 | workload/lock/I/O window | stats timestamp、plan |
| `CREATE INDEX CONCURRENTLY` | R1 | version、invalid index、disk/WAL | `indisvalid/indisready`、plan |
| parameter reload | R1 | context/source、rendered diff | `pg_settings` + runtime |
| restart-required config | R1/R2 | HA/traffic/rollback | identity、role、availability |
| cancel exact query | R1 | PID reuse protection、owner | target gone、business effect |
| switchover/failover | R2/R3 | fence/authority/candidate/client contract | timeline、route、unknown |
| restore/PITR | R2/R3 | source/target/candidate/isolated destination | lineage、business manifest |
| `pg_rewind`/base backup | R2/R3 | system id/timeline/source direction | streaming lineage |
| checksum fault injection | R2 | stopped disposable clone | original hash + recovery copy |

`pg_resetwal`、`zero_damaged_pages`、`ignore_checksum_failure`、手改 relation/WAL 不属于
普通速查动作；仅在证据 clone、明确损失和专业升级下考虑，见 [ch35](/data-rescue-forensics/)。

### 验证模板

```text
before
  exact identity + objective + independent baseline

action
  command/source hash + parameters + exit/stdout/stderr + authority

after
  expected observation + no-regression + business invariant

restore
  temporary artifacts removed or retained by policy

boundary
  what this evidence does not prove
```

退出码 0、service active 和 dashboard green 都只能证明局部命题。

---

[返回附录目录](../) · [症状索引](../c/) · [实验风险与复位](../e/) ·
[查看全书目录](/toc/)
