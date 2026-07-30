---
title: 第 20 章 狡兔三窟：高可用拓扑与容灾目标
linkTitle: 20 狡兔三窟：高可用拓扑与容灾目标
weight: 300
aliases:
- "/ch20/"
- "/volume-2/high-availability/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch20
book_number: 20
book_part: part-4
book_status: draft
---

三台 PostgreSQL 都在运行，不等于“高可用”；一次 `patronictl list`
显示一个 Leader，也不等于“不会脑裂”；计划切换没有丢行，更不等于
“自动故障转移零 RPO”。

本章把高可用收敛为一个可以审计的命题：

> 在明确的失败模型、提交语义与权限边界内，系统能否维持一条被授权的
> 可写历史，并在规定时间内把客户端带回可判断的服务状态？

我们先从 failure model、RPO/RTO 和 degradation target 出发，再进入
PostgreSQL 的 WAL、LSN、timeline、复制槽与同步提交；随后解释 Patroni、
DCS、租约与 fencing 如何组合；最后在第 19 章保留的 Pigsty v4.4.0
四机沙箱上完成一次有客户端证据的计划切换。

本章的正式结论很克制：

```text
健康计划切换             通过，带十项沙箱例外
自动故障转移             未测试
硬件/进程/网络故障       未注入
零 RPO                   未证明
生产 RTO                 未证明
fencing / watchdog       未验收
生产批准                  pending
```

## 本章目标

读完并完成实验后，你应当能够：

1. 先列故障域和共同依赖，再谈节点数与“几副本”；
2. 正确区分 RPO、RTO、降级目标、维护切换时间与客户端恢复时间；
3. 从 `pg_stat_replication`、`pg_stat_wal_receiver`、LSN 与复制槽解释
   物理流复制；
4. 区分 system identifier、timeline、checkpoint timeline 与当前 WAL
   timeline；
5. 解释异步、`remote_write`、`on`、`remote_apply` 以及 `FIRST/ANY`
   同步集合的保证和代价；
6. 说明 Patroni leader lock、DCS、TTL、loop、candidate eligibility、
   watchdog 与 fencing 分别解决什么问题；
7. 区分 planned switchover、automatic/manual failover、rewind 与 rebuild；
8. 把服务端点、会话断开、结果未知与幂等 token 放在同一个客户端合同中；
9. 用 Pigsty 交付的角色、服务与原生 PostgreSQL 证据交叉验证；
10. 设计一场有 preflight、mutation guard、证据、反例和复位的 HA 演练；
11. 知道一次成功实验**不能**推出哪些生产结论。

## 前置与后续

前置：

- [第 18 章 PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) 定义 service
  objective 与 capability placement；
- [第 19 章 部署基线](/deployment-baseline/) 保留四台独立 VM、两个
  PostgreSQL service unit 以及 secret-safe inventory；
- 读者已掌握 Linux、SQL、事务与基本网络知识；
- 不要求预先掌握 Patroni、etcd 或 Pigsty HA internals。

后续：

- [第 21 章 备份体系与恢复演练](/backup-recovery/) 处理 base backup、WAL archive、
  PITR 与 restore proof；
- [第 22 章 服务接入、连接池与路由](/connection-pooling-routing/) 深入 routing、
  pooling、session 与 client retry contract；
- 第 23 章处理 transport、identity 与 secret；
- 第 33 章才安排另行授权的 unplanned failure/incident exercise。

## 学习路径

```text
business loss
  -> failure model + common dependencies
      -> RPO / RTO / degradation contract
          -> WAL transport + replay + timeline
              -> commit acknowledgement policy
                  -> election authority + fencing
                      -> service routing + client semantics
                          -> guarded planned switchover
                              -> evidence + exceptions + next gate
```

这条路径故意不从“如何敲 failover 命令”开始。命令只是状态迁移的一个
触发器；如果故障、authority、数据风险与客户端完成条件没有先定义，操作
越快，越可能把错误历史更快地交给用户。

## 正式实验拓扑

```text
target       pg36-l2-vagrant/pg-test
Pigsty       exact v4.4.0 tag
PostgreSQL   18.4
Patroni      4.1.3
DCS          one etcd member (sandbox exception)
members      pg-test-1 / pg-test-2 / pg-test-3
policy       asynchronous; synchronous_mode=false
watchdog     off (sandbox exception)
client       Pigsty primary service, 10.10.10.11:5433
```

角色迁移：

```text
before          pg-test-1 primary, pg-test-2/3 streaming, timeline 5
forward         pg-test-2 primary, pg-test-1/3 streaming, timeline 6
restored        pg-test-1 primary, pg-test-2/3 streaming, timeline 7
lineage         one unchanged PostgreSQL system identifier
```

实验通过 Pigsty primary service 写入唯一 token，而不是直接连接“我们以为
是主库”的节点。正式观测：

```text
probe attempts                    120
acknowledged                       95
outcome unknown                    25
acknowledged rows missing           0
unknown committed                   0
unknown reconciled absent          25
duplicate tokens                    0
forward patronictl command      2.735 s
forward action to stable        5.823 s
conservative sampled write gap  6.007 s
```

`6.007 s` 是一次健康计划切换下的**采样写入间隙**。它包含约 0.2 秒的
probe resolution，不包含故障检测，不是生产 RTO 分布，也不是 SLO。

## 十项例外

沿用第 19 章六项：

```text
EX19-SHARED-HYPERVISOR
EX19-SINGLE-ETCD
EX19-SINGLE-BACKUP-TARGET
EX19-VIRTUAL-STORAGE
EX19-INVENTORY-SECRETS
EX19-LAB-RESOURCE-FLOOR
```

本章新增四项：

```text
EX20-ASYNC-BASELINE
  synchronous_mode=false；不能声称 zero RPO

EX20-WATCHDOG-OFF
  未验证硬件 watchdog fencing

EX20-CLIENT-PROXY-NO-TLS
  沙箱外部 5433 只以 sslmode=prefer 验证；不能通过生产传输安全

EX20-PLANNED-ONLY
  只做 healthy switchover；不能声称 automatic failover、split-brain
  exclusion 或 failure-time RTO
```

例外不是“以后再看”的备注，而是直接阻止某类推论的逻辑条件。

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第四篇：规划——建设可交付的 PostgreSQL 服务
- 兼容入口：`/ch20/`、`/volume-2/high-availability/`

## 本章目录

### [20.1 从失败模型设计高可用](01/)

- [20.1.1 进程、主机、磁盘、网络、机房与控制面故障](01/#item-20-1-1)
- [20.1.2 RPO、RTO、降级目标与数据风险](01/#item-20-1-2)
- [20.1.3 高可用不等于备份，也不等于零数据丢失](01/#item-20-1-3)

### [20.2 物理流复制](02/)

- [20.2.1 WAL 发送、接收、重放与 LSN](02/#item-20-2-1)
- [20.2.2 timeline、恢复目标与历史分叉](02/#item-20-2-2)
- [20.2.3 复制槽、归档与 WAL 保留](02/#item-20-2-3)

### [20.3 同步策略与提交语义](03/)

- [20.3.1 异步、同步与远程应用确认](03/#item-20-3-1)
- [20.3.2 多副本同步集合与退化条件](03/#item-20-3-2)
- [20.3.3 延迟、可用性和数据保护的交换](03/#item-20-3-3)

### [20.4 选主、DCS 与防脑裂](04/)

- [20.4.1 Patroni、租约、leader lock 与健康判断](04/#item-20-4-1)
- [20.4.2 fencing、watchdog 与旧主隔离](04/#item-20-4-2)
- [20.4.3 DCS 可用性与数据库可用性不是同一件事](04/#item-20-4-3)

### [20.5 切换、故障转移与重加入](05/)

- [20.5.1 planned switchover 与 unplanned failover](05/#item-20-5-1)
- [20.5.2 端点切换、客户端恢复与只读窗口](05/#item-20-5-2)
- [20.5.3 `pg_rewind`、重建与时间线验证](05/#item-20-5-3)

### [20.6 交付并观察 HA 集群](06/)

- [20.6.1 拓扑、同步策略与服务端点声明](06/#item-20-6-1)
- [20.6.2 从 Patroni、SQL 和指标验证角色](06/#item-20-6-2)
- [20.6.3 演练动作对应的 Pigsty 入口与原生证据](06/#item-20-6-3)

### [20.7 实战：一次有证据的计划切换](07/)

- [20.7.1 预检查、切换、客户端观察与数据核对](07/#item-20-7-1)
- [20.7.2 测量实际 RTO、提交风险与恢复时间](07/#item-20-7-2)
- [20.7.3 输出拓扑证据、时间线和改进项](07/#item-20-7-3)
- [20.7.4 记录把本章迁移到新版本基线的工时](07/#item-20-7-4)

## 实验入口

- [`lab-contract.md`](/labs/ch20/lab-contract.md)：动作、风险和解释边界；
- [`requirements.json`](/labs/ch20/requirements.json)：可执行验收合同；
- [`failure-model.json`](/labs/ch20/failure-model.json)：九类场景；
- [`ha-adr.md`](/labs/ch20/ha-adr.md)：为什么只接受 planned switchover；
- [`task.sh`](/labs/ch20/task.sh)：安全动作入口；
- [`ha-facts.sql`](/labs/ch20/ha-facts.sql)：PostgreSQL 原生证据；
- [`drill-run.json`](/labs/ch20/drill-run.json)：无 secret 的正式结果；
- [`negative-cases.json`](/labs/ch20/negative-cases.json)：十个必须拒绝的反例；
- [`topology.mmd`](/labs/ch20/topology.mmd)：实验数据与控制路径。

安全语义：

```text
capture / verify / review / all
  L0 read-only

drill:switchover
  L2 local sandbox mutation
  exact target + no production data/traffic + explicit confirmation

reset:fixture
  destructive and separate
  never called by all or drill:switchover
```

普通 `all` 只验证已有证据。它不会为了“方便”重跑切换。

## 本章最重要的判断

```text
replica exists             != RPO achieved
three nodes                != three failure domains
leader elected             != old primary fenced
Patroni healthy            != client service recovered
command returned           != application RTO
connection error           != transaction rolled back
planned switchover passed  != unplanned failover passed
no missing ack in one run  != asynchronous zero RPO
HA                         != backup / PITR
```

如果只记住一句话：

> 高可用的目标不是“尽快出现一个新主库”，而是在故障与不确定性中，只让
> 一条可解释、可追溯、被授权的历史继续接受写入。

## 权威参考

- [PostgreSQL 18：Log-Shipping Standby Servers](https://www.postgresql.org/docs/18/warm-standby.html)
- [PostgreSQL 18：Replication Settings](https://www.postgresql.org/docs/18/runtime-config-replication.html)
- [PostgreSQL 18：`pg_rewind`](https://www.postgresql.org/docs/18/app-pgrewind.html)
- [Patroni：Replication modes](https://patroni.readthedocs.io/en/latest/replication_modes.html)
- [Patroni：Watchdog support](https://patroni.readthedocs.io/en/latest/watchdog.html)
- [Patroni：DCS failsafe mode](https://patroni.readthedocs.io/en/latest/dcs_failsafe_mode.html)
- [Pigsty：High Availability](https://pigsty.io/docs/concept/ha/)
- [Pigsty：Service/Access](https://pigsty.io/docs/pgsql/service/)

---

[上一章：开天辟地：环境规划与部署基线](/deployment-baseline/) · [返回下卷导读](/lower-volume/) · [下一章：未雨绸缪：备份体系与恢复演练](/backup-recovery/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
