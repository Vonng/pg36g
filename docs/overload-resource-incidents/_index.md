---
title: 第 34 章 过载保护与资源故障判型——李代桃僵
linkTitle: 34 过载保护与资源故障判型——李代桃僵
weight: 440
aliases:
- "/ch34/"
- "/volume-2/overload-resource-incidents/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch34
book_number: 34
book_part: part-6
book_status: draft
---

数据库“慢、满、连不上”时，最危险的动作往往不是没有动作，而是把正确手段用在了
错误根因上：

```text
连接风暴  -> 扩大 max_connections  -> 内存与调度更快耗尽
WAL 撑盘 -> 取消慢查询              -> restart_lsn 一字节也不前进
XID 保留 -> 清理普通表空间          -> 冻结边界仍被旧 xmin 钉住
I/O 排队 -> 同时重启所有组件        -> 证据消失，恢复负载叠加
```

本章把资源事故分成两条首先必须分开的路径：

```text
flow pressure
  新工作到达得比系统完成得快
  -> 排队、拒绝、超时、重试放大
  -> 目标是减少进入量、并发量或单项成本

retention pressure
  某个仍被声明为“需要”的历史边界不能前进
  -> WAL、旧版本或事务状态不能回收
  -> 目标是识别 owner、保护证据、修复消费者或恢复链
```

二者可以同时发生，也可能都不是。如果证据不足，正确路线不是猜一个，而是
`STOP_AND_INVESTIGATE`：停止破坏性清理、冻结新增变量、保留 SQL 与主机证据，并明确
尚未回答的问题。

## 学习完成标准

完成本章后，读者应能：

1. 把“CPU 高、磁盘满、延迟高、连接失败”视为症状，而不是根因；
2. 区分流量型竞争与 WAL/XID/slot/归档/长事务造成的保留型压力；
3. 解释到达率、服务率、并发、队列和超时为什么会形成正反馈；
4. 为应用池、PgBouncer、HAProxy 与 PostgreSQL 分配一致的连接预算；
5. 识别健康检查、短连接和无抖动重试造成的隐藏放大；
6. 用 `pg_stat_activity`、wait event、阻塞树和执行计划识别失控工作；
7. 区分 `pg_cancel_backend` 与 `pg_terminate_backend` 的影响和权限边界；
8. 在结束长事务或大事务前评估锁释放、中止清理、既有 WAL、死版本与后续 vacuum 成本；
9. 用并发最坏值估算 `work_mem`、并行 worker 与连接数的内存风险；
10. 将 PostgreSQL 的 I/O 证据与主机设备延迟、队列和文件系统余量互证；
11. 为限流、熔断、摘流、取消和只读降级写出收益、代价、停止线与回退；
12. 从 `backend_xmin`、复制槽 `xmin`/`catalog_xmin` 和 prepared transaction 判断
    XID 保留者；
13. 从 `restart_lsn`、`wal_status`、归档与备份状态判断 WAL 保留者；
14. 解释为什么绝不能在运行中的实例里手工删除 `pg_wal` 文件；
15. 用 Pigsty 的服务端点、连接池与监控缩小影响范围，但回到 PostgreSQL/OS 证据判型；
16. 在不知道盲测答案时选择正确路线，并拒绝 34 类越界或误判证据。

## 一张判型表

| 问题 | 流量型 | 保留型 |
|---|---|---|
| 核心状态 | 到达工作超过可服务能力 | 最老的必需历史边界不能前进 |
| 典型信号 | 连接拒绝、队列、锁等待、CPU/I/O 饱和 | inactive slot、旧 `xmin`、归档失败、WAL 累积 |
| 第一目标 | 减少 admission、并发或单项成本 | 找到 owner 与恢复来源，保护 lineage |
| 可以立即做 | 限流、暂停批处理、精确 cancel、降级 | 留证、隔离增长、恢复消费者、评估精确释放 |
| 不应盲做 | 临时放大连接/内存，广域 terminate | cancel 普通查询、删 `pg_wal`、随意 drop slot |
| 成功证据 | 队列下降、拒绝停止、业务探针恢复 | 保留边界推进、归档/消费者恢复、恢复链完整 |

资源余量也不是一个百分比。至少要同时表达：

$$
H_r = L_r - U_r
$$

其中 $L_r$ 是资源 $r$ 的安全上限，$U_r$ 是当前与已承诺使用量。对连接、内存、WAL
空间、XID age、I/O 服务能力分别计算的 $H_r$ 不能相互替代。磁盘还有 30% 并不能
证明连接有余量；CPU 只有 20% 也不能证明 WAL 保留安全。

对流量型队列，若一段持续窗口内到达率 $\lambda$ 大于完成率 $\mu$：

$$
\frac{dQ}{dt} \approx \lambda-\mu > 0
$$

队列 $Q$ 就会增长。平均值暂时正常也救不了尾延迟；重试还会反过来抬高 $\lambda$。
对保留型压力，真正需要测的是“最老仍被需要的位置”及其推进速度，而不是只看目录
当前大小。

## 事故时的四步闭环

```text
1. bound
   影响哪个服务、角色、数据库、主机和时间窗？

2. classify
   flow、retention、both 还是 unknown？

3. relieve or route
   流量型做精确减压；保留型保护证据并进入专门恢复路径

4. verify
   用户探针、队列、保留边界、拓扑与临时动作是否全部复位？
```

每一步都要记录 UTC 时间、证据引用、操作者、预期收益、停止条件和实际结果。仅仅看到
面板曲线下降，不能说明动作正确：流量也可能因为所有客户端都超时而“下降”。

## 正式实验

本章在已确认的 Pigsty 开发沙箱做两层实验：

```text
managed pg-test
  Patroni / SQL read-only capture before and after
  no connection storm, slot, cancel, service or route mutation

pg-test-3 disposable PostgreSQL 18.4
  /tmp/pg36-ch34-overload-<run-id>
  listen_addresses=''
  private Unix socket
  max_connections=24
  exact cleanup after server stop
```

runner 用系统随机源安排两个 blind case，classifier 只能读取共同告警
`postgresql-resource-headroom-at-risk` 及观测字段，不能读取 hidden truth。正式顺序为：

```text
RETENTION -> FLOW
```

正式观测：

| 情形 | 关键证据 | 判定与动作 |
|---|---|---|
| connection storm | 30 次尝试，21 个会话，9 次拒绝，20 个锁等待 | `RELIEVE_FLOW_PRESSURE`；精确 cancel fixture sessions |
| WAL retention | 1 个 inactive physical slot，保留 42,611,296 bytes | `PRESERVE_RETENTION_EVIDENCE`；先留证，再 drop exact disposable slot |

两个 case 完成后：

```text
fixture sessions                   0
disposable physical slots          0
manual pg_wal file deletion    false
OOM / filesystem fill          false
managed topology changed       false
managed system id changed      false
managed timeline changed       false
exact temporary root remains   false
```

验证器同时构造并拒绝 34 个真实 mutant，包括生产边界被打开、blind packet 泄露答案、
阈值被削弱、广域 cancel、slot 仍残留以及谎报清理成功。公开证据见
[`overload-run.json`](/labs/ch34/overload-run.json)。

这份实验能证明**在该隔离 PG18 合同内**两类证据可区分，且精确动作能复位 fixture。
它不证明生产连接上限、真实 OOM victim、文件系统填满行为、归档仓库故障或未知
replication slot 可以安全删除；最终门禁固定为 `production_ch34_gate=pending`。

## 阅读前后关系

- 前置：[第 22 章 服务接入、连接池与路由](/connection-pooling-routing/)、
  [第 31 章 事件分级、现场保护与应急决策](/incident-response/)
- 后续：[第 35 章 数据抢救与工程取证](/data-rescue-forensics/)

## 本章目录

### [34.1 第一动作：流量型还是保留型](01/)

- [34.1.1 流量增长、慢查询、锁与连接导致的竞争](01/#item-34-1-1)
- [34.1.2 WAL、XID、复制槽、归档和长事务导致的保留](01/#item-34-1-2)
- [34.1.3 同样表现为“磁盘满”或“延迟高”，动作可以相反](01/#item-34-1-3)
- [34.1.4 判型不清时先停止破坏性清理](01/#item-34-1-4)

### [34.2 连接风暴与排队失控](02/)

- [34.2.1 数据库连接、代理池与应用池三层](02/#item-34-2-1)
- [34.2.2 重试放大、健康检查和短连接](02/#item-34-2-2)
- [34.2.3 限流、队列、连接预算与指数退避](02/#item-34-2-3)

### [34.3 失控查询、锁与事务](03/)

- [34.3.1 识别高消耗查询和阻塞根节点](03/#item-34-3-1)
- [34.3.2 cancel、terminate 与中止后成本](03/#item-34-3-2)
- [34.3.3 长事务和大事务结束前先评估后果](03/#item-34-3-3)

### [34.4 CPU、内存、I/O 与 OOM](04/)

- [34.4.1 饱和、排队、抖动与抢占](04/#item-34-4-1)
- [34.4.2 临时文件、并行、checkpoint 与后台维护](04/#item-34-4-2)
- [34.4.3 内存最坏并发、OOM killer 与进程重启](04/#item-34-4-3)

### [34.5 流量型止血动作](05/)

- [34.5.1 限流、熔断、摘除非关键负载](05/#item-34-5-1)
- [34.5.2 取消查询、暂停批处理与只读降级](05/#item-34-5-2)
- [34.5.3 每个动作写清收益、代价、停止条件和回退](05/#item-34-5-3)

### [34.6 保留型故障的安全路由](06/)

- [34.6.1 XID：检查 `backend_xmin`、复制槽 `xmin` 与 `pg_prepared_xacts`](06/#item-34-6-1)
- [34.6.2 WAL 撑盘：检查归档失败、复制槽和未完成备份](06/#item-34-6-2)
- [34.6.3 绝不手工删除 `pg_wal`；保护现场后转 ch21/ch28/ch35](06/#item-34-6-3)
- [34.6.4 本章的一般止血动作不构成保留型修复](06/#item-34-6-4)

### [34.7 平台级流量控制与证据](07/)

- [34.7.1 从服务端点隔离批处理和只读流量](07/#item-34-7-1)
- [34.7.2 用连接池、代理与应用控制点逐级减压](07/#item-34-7-2)
- [34.7.3 从面板判断范围，再用 SQL 与主机证据判型](07/#item-34-7-3)

### [34.8 实战：同一症状、两种成因](08/)

- [34.8.1 随机注入连接风暴或 WAL 保留](08/#item-34-8-1)
- [34.8.2 在不知道答案时先判型，再选择动作](08/#item-34-8-2)
- [34.8.3 对流量型恢复服务，对保留型完成安全路由](08/#item-34-8-3)
- [34.8.4 输出动作时间线、误判代价与容量改进项](08/#item-34-8-4)

## 权威参考

PostgreSQL：

- [Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)
- [`pg_stat_activity` and cumulative statistics](https://www.postgresql.org/docs/18/monitoring-stats.html)
- [System Administration Functions](https://www.postgresql.org/docs/18/functions-admin.html)
- [`pg_replication_slots`](https://www.postgresql.org/docs/18/view-pg-replication-slots.html)
- [Resource Consumption](https://www.postgresql.org/docs/18/runtime-config-resource.html)
- [Kernel Resources and Linux OOM](https://www.postgresql.org/docs/18/kernel-resources.html)
- [Replication Configuration](https://www.postgresql.org/docs/18/runtime-config-replication.html)

Pigsty：

- [Service Access](https://pigsty.io/docs/concept/ha/svc/)
- [PostgreSQL Monitoring](https://pigsty.io/docs/pgsql/monitor/)
- [Service and Access](https://pigsty.io/docs/pgsql/service/)
- [Database and Pool Configuration](https://pigsty.io/docs/pgsql/config/db/)

---

[上一章：故障切换与集群重建——力挽狂澜](/failover-rebuild/) · [返回下卷导读](/lower-volume/) · [下一章：数据抢救与工程取证——起死回生](/data-rescue-forensics/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
