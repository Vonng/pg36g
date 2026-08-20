---
title: 附录 C：症状与首个安全动作索引
linkTitle: 附录 C 症状与首个安全动作索引
weight: 30
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

这是“先别把事故变糟”的路由表，不是自动诊断器。任何症状先确认 environment、
cluster/system identity、用户影响、数据风险和变化速度；证据缺失或冲突时进入
[ch31 的 `STOP_AND_ESCALATE`](/incident-response/)，不要强行匹配一行。

## C.1 误删误改、主节点故障、DCS 故障、复制停滞 {#appendix-c-1}

| 症状 | 首个安全动作 | 首批证据 | 路由 | 禁止捷径 |
|---|---|---|---|---|
| 误删/误改 | 停止继续写与外部副作用，保留 audit/WAL/backup | exact transaction、时间/XID/LSN、影响对象、合法后写 | [ch32 PITR](/pitr/) | 在原库盲目反向 SQL、删除 WAL |
| writer 不可达 | 从 user path 到 proxy/DB 分层确认，并保护单 writer authority | endpoint、HAProxy、Patroni/DCS、role/timeline、client unknown | [ch33 failover](/failover-rebuild/) | 未围栏旧主就强制 promotion |
| DCS 异常 | 暂停扩大 authority 的动作，确认 quorum/failsafe/watchdog 与节点视图 | member health、leader/term/revision、network 分区、DB role | [ch33 DCS](/failover-rebuild/04/) | 删 key、重建 DCS 后宣称 lineage 安全 |
| replica 停滞 | 保护 primary 与 WAL，识别 receive/replay/network/slot/source | sender/receiver、LSN、timeline、logs、disk、slot | [ch20 HA](/high-availability/)、[ch33](/failover-rebuild/) | 立即 reinit，先抹掉故障证据 |

### 误操作的最小记录

```text
who/role/application
exact database/schema/object
transaction identity and commit status
first known bad / last known good
external dispatch and caches
backup + WAL coverage
post-target legitimate writes
```

应用 timeout 不能证明 transaction 回滚；先用 request/idempotency token 对账。

### “主库故障”的分层

```text
user/client
  -> DNS/VIP/HAProxy
  -> PgBouncer
  -> PostgreSQL listener/session
  -> Patroni/DCS authority
  -> storage/host/network
```

代理错误不应触发数据库 promotion；进程停止也不等于硬件已围栏。每层用独立证据，
接受新 writer 前证明旧 writer 不能继续拥有 authority。

## C.2 连接耗尽、锁等待、CPU、内存、I/O 与 OOM {#appendix-c-2}

| 症状 | 首个安全动作 | 先分辨 | 禁止捷径 |
|---|---|---|---|
| connection exhausted | 在入口阻止新放大，保留管理通道 | pool wait、server session、role/app、retry | 先调大 `max_connections` |
| lock wait | 建 blocker/waiter graph，保护业务 owner | lock queue、long xact、DDL、prepared xact | 无差别 kill 全库 |
| CPU 高 | 观察 run queue、query mix、plan、spin/系统进程 | demand、单 query、并行、vacuum、非 DB | 仅凭 load average 重启 |
| memory/OOM | 限制新工作，保存 kernel/cgroup/PostgreSQL 证据 | resident/cache、per-op memory、并发、OOM victim | drop cache、反复拉起 |
| I/O 慢 | 降低非关键 I/O，区分 latency/queue/throughput | device/fs、checkpoint、WAL、temp、backup | 同时重启所有组件 |

### flow pressure 的首要目标

```text
reduce arrival
reduce concurrency
reduce per-item cost
protect critical lane
```

按 service/role/application_name/query class 精确限流、降级或取消，并定义 expected、
stop、rollback。客户端 retry 没有 backoff/jitter/idempotency 时，会把短故障放大为
持续过载。

### retention pressure 不走限流捷径

WAL、XID 或磁盘满可能由仍被声明为“需要”的历史边界造成。取消慢 SQL 不一定推进 slot
`restart_lsn` 或旧 `xmin`。先查 owner、恢复/复制语义，再清 exact owned consumer。

详见 [ch22 连接预算](/connection-pooling-routing/)、
[ch25 可观测](/observability/) 和 [ch34 资源事故](/overload-resource-incidents/)。

## C.3 XID 回卷：先查 `backend_xmin`、复制槽 `xmin`、`pg_prepared_xacts` {#appendix-c-3}

### 首个目标：找谁钉住 horizon

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;

SELECT
    pid,
    datname,
    usename,
    application_name,
    backend_xmin,
    xact_start,
    state,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY xact_start NULLS LAST;

SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_catalog.pg_replication_slots;

SELECT *
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

再查：

```text
autovacuum/freeze progress and logs
table relfrozenxid/relminmxid age
long-running idle-in-transaction
logical decoder/subscriber owner
prepared transaction business owner
disk and WAL headroom
```

### 动作边界

- 先阻止新的长事务/无界读取，保护 maintenance lane；
- exact backend 取消/终止需要业务 owner 和 commit/rollback 影响判断；
- slot 可能代表 DR、CDC 或恢复承诺，不能只因 inactive 删除；
- prepared transaction 要按业务协议 commit/rollback，不能猜；
- 提高 freeze 参数或跑更激进 vacuum 前确认 I/O、WAL、lock 与时间余量；
- 接近 wraparound 时升级 severity 与 authority，不在压力下尝试不熟悉的 catalog 修改。

路由：[ch28 VACUUM、冻结与膨胀](/vacuum-freeze-bloat/)；
资源止血见 [ch34.6](/overload-resource-incidents/06/)。

## C.4 WAL 撑盘：先查归档、复制槽和备份保留者，绝不手工删除 `pg_wal` {#appendix-c-4}

### 先建立 conservation picture

```text
generation rate
  pg_stat_wal + workload/checkpoint

archive
  pg_stat_archiver + archive logs + repository

physical/logical consumers
  pg_stat_replication + pg_replication_slots + subscriptions

restore/backup
  pgBackRest process, spool, lock and repository

filesystem
  PGDATA/pg_wal mount, free bytes/inodes, I/O errors
```

常见分类：

| 证据 | 方向 |
|---|---|
| archive failed_count 增长/last success 停滞 | 修 archive destination/auth/network |
| inactive slot restart LSN 不动 | 找 owner，保护证据，再决定 consumer/slot |
| replica receive/replay 停滞 | 分 network/storage/query/recovery |
| WAL 生成率暴增但消费者正常 | flow/query/checkpoint/DDL/backup workload |
| filesystem error/只读/OOM | 基础设施事故，先保护数据 |

### 首个安全动作

1. 停止非关键的大写入、bulk/DDL 与 retry 放大；
2. 保留管理连接和当前 slot/archive/replication evidence；
3. 估算 time-to-full，而不是只报百分比；
4. 确认能否安全扩容/迁移 filesystem；
5. 修复 exact owned consumer，或在审批后清理；
6. 验证 archive continuity、replica/slot 和 backup。

绝不手工删除 `pg_wal`、伪造 archive success 或随意 `pg_resetwal`。这些动作会破坏 crash
recovery、replication 或 PITR，且可能把可恢复事故变成不可恢复损坏。

## C.5 checksum、索引、collation 与逻辑不一致 {#appendix-c-5}

| 症状 | 首个安全动作 | 分类证据 | 主要恢复源 |
|---|---|---|---|
| checksum/invalid page/I/O | 停写或隔离、snapshot、hash 原件 | checksum、relation/block、kernel/storage | backup/健康副本/snapshot |
| `amcheck` 索引异常 | 保留 heap 与索引证据，查同故障域 | index check、heap check、checksum | heap + 正确规则重建 |
| collation version mismatch | 枚举 exact dependencies，不先消 warning | stored/actual version、provider、amcheck | REINDEX derived objects 后 REFRESH |
| 合法 page 但业务错误 | 阻止副作用，定义 affected fact/cutoff | audit、ledger、不变量、external | PITR/审计/upstream/补偿 |

### 不能互相替代

```text
checksum clean
  != index order correct
  != business data correct

amcheck pass
  != heap/page/storage safe

service starts
  != recovered data trusted
```

抢救先保存 original evidence，再从同一 snapshot 分叉 working clone。危险恢复参数仅在
clone、明确接受损失和专业升级下使用。详见
[ch35 数据抢救与取证](/data-rescue-forensics/)。

## C.6 每一行同时标明目标章节、首个安全动作和禁止动作 {#appendix-c-6}

### 总路由

| 入口症状 | 首个安全动作 | 目标章节 | 禁止动作 |
|---|---|---|---|
| 影响不明、证据冲突 | 建 identity/impact/evidence，保持可逆 | [ch31](/incident-response/) | 根据第一个告警猜根因 |
| 误写/误删 | 停副作用、保存 audit/WAL/backup | [ch32](/pitr/) | 原库反复试回滚 |
| primary/DCS/lineage | 保护单 writer authority、先围栏 | [ch33](/failover-rebuild/) | 无 fence 强制切换 |
| 慢/满/连不上 | 分 flow 与 retention | [ch34](/overload-resource-incidents/) | 统一用 restart/扩连接 |
| page/index/collation/语义 | 原件 snapshot/hash，clone 分类 | [ch35](/data-rescue-forensics/) | 改唯一副本、删 WAL |
| 服务已恢复 | 清临时控制、复盘、验证 action | [ch36](/postmortem-platform-improvement/) | 以 ticket/PR 代替效果 |

### 首个动作卡

```yaml
symptom:
target_identity:
user_impact:
data_and_recovery_risk:
changing_now:
first_safe_action:
evidence_before:
expected:
stop:
rollback:
owner_and_authority:
route_if_supported:
route_if_unknown: STOP_AND_ESCALATE
```

若没有权限执行首个动作，正确动作是升级 owner 并继续只读取证，而不是扩大权限范围。

---

[返回附录目录](../) · [对象与证据速查](../b/) · [实验风险与复位](../e/) ·
[查看全书目录](/toc/)
