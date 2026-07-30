# 第 34 章实验合同

本实验只对已确认的 Pigsty 开发沙箱做 L0 read-only capture。连接风暴、锁队列和 WAL
保留全部发生在 `pg-test-3` 的
`/tmp/pg36-ch34-overload-<run-id>` 一次性 PostgreSQL cluster 中：

```text
listen_addresses=''
private mode-0700 Unix socket
max_connections=24
superuser_reserved_connections=3
max_replication_slots=4
max_slot_wal_keep_size=-1
```

临时 cluster 不加入 Patroni/DCS，不接入 HAProxy/PgBouncer，不使用 managed PGDATA、
备份仓库或业务路由。

## 同症状、双根因：两个盲场景

runner 用系统随机源决定顺序，并给场景分配不含语义的 case ID。classifier 只能读取
blind packet，不能读取 hidden truth。不会在受管集群上制造连接风暴。

### Flow pressure

30 个非超级用户 client 尝试进入 24-connection cluster，成功连接者在同一 advisory
lock 上排队并保持 20 秒。必须观察：

```text
at least 18 fixture sessions
at least one connection rejection
at least one lock waiter
no inactive physical replication slot
```

允许动作仅为 `pg_cancel_backend` 命中 exact fixture application-name prefix。若 client
进程未在 deadline 内退出，只能终止本 runner 直接创建、持有 PID 的子进程。不得取消
managed PostgreSQL 或无关会话。

### Retention pressure

runner 创建一个带 run marker 的 exact inactive physical slot，然后生成 WAL，直到
`pg_wal_lsn_diff(current_lsn,restart_lsn)` 至少 32 MiB、且绝不超过 128 MiB。必须观察：

```text
one inactive physical slot
restart_lsn present
retained WAL >= 32 MiB
zero connection rejection
```

先保存证据，再删除这个 disposable、exact-owned slot。生产上的未知 slot 不能套用这份
授权：必须先确定 owner、consumer、backup/replica 需求和数据损失。实验不会手工删除
`pg_wal` 文件。

## 判型与动作

共同告警名为 `postgresql-resource-headroom-at-risk`。分类：

```text
connection saturation + rejects + lock waiters + no retaining slot
  -> RELIEVE_FLOW_PRESSURE

inactive slot + retained restart_lsn + no connection rejection
  -> PRESERVE_RETENTION_EVIDENCE

both/neither
  -> STOP_AND_INVESTIGATE
```

错误动作只做 counterfactual 分析，不真实执行。尤其不会为了证明危害去删除 WAL、
触发 OOM、drop OS cache、占满文件系统或扩大 `max_connections`。

## 授权与清理

完整实验要求：

```text
PG36_CH34_TARGET=pg36-l2-vagrant/pg-test
PG36_CH34_NONPRODUCTION=true
PG36_CH34_PRODUCTION_DATA=false
PG36_CH34_PRODUCTION_TRAFFIC=false
PG36_CH34_CONFIRM=BLIND_FLOW_VS_RETENTION_CH34
```

任一 guard 缺失都在远端目录创建前失败。正常或失败清理只停止这个 run 的临时
postmaster、终止 runner 自己持有的 client process，并在 marker 匹配后删除 exact root。
它不执行 managed cancel/terminate、slot/drop、service restart、route change 或 DCS
mutation。

## 结论边界

实验能证明两类证据在隔离 PG18 中可区分，并证明 exact cancel 与 exact disposable slot
drop 的机制。它不证明 Pigsty managed cluster 的真实连接上限、生产磁盘满行为、OOM
killer 选择、归档失败、真实备份/复制消费者处置或生产恢复时长。最终门禁固定为
`production_ch34_gate=pending`。
