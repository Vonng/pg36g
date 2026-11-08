---
title: 狡兔三窟：高可用拓扑与容灾目标
linkTitle: 狡兔三窟：高可用拓扑与容灾目标
weight: 300
aliases:
- "/ch20/"
- "/volume-2/high-availability/"
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch20
book_number: 20
book_part: part-4
book_status: reviewed
---

主库故障后，哪台备库可以接管？哪些已提交的数据可能丢失？怎样阻止旧主库继续接受写入？应用怎样连到新主库？本章围绕这四个问题讲高可用：先建立失败模型和 RPO/RTO 目标，再讲 PostgreSQL 的物理流复制（WAL、LSN、timeline、复制槽、同步提交），然后是 Patroni 的选主、租约与隔离机制，最后在第 19 章留下的四机沙箱上完成一次带客户端证据的计划切换。自动故障转移需要注入故障，属于第 33 章另行授权的演练。

## 本章目标

读完并完成实验后，你应当能够：

1. 先列故障域和共同依赖，再谈节点数与副本数；
2. 区分 RPO、RTO、降级目标、维护切换时间与客户端恢复时间；
3. 从 `pg_stat_replication`、`pg_stat_wal_receiver`、LSN 与复制槽解释物理流复制；
4. 区分 system identifier、timeline、checkpoint timeline 与当前 WAL timeline；
5. 解释异步、`remote_write`、`on`、`remote_apply` 以及 `FIRST/ANY` 同步集合的保证与代价；
6. 说明 Patroni 的 leader lock、DCS、TTL、watchdog 与 fencing 分别解决什么问题；
7. 区分计划切换（switchover）、故障转移（failover）、`pg_rewind` 重加入与完全重建；
8. 把服务端点、会话断开、结果未知与幂等 token 放进同一套客户端处理逻辑；
9. 用 Pigsty 交付的角色、服务与原生 PostgreSQL 证据交叉验证集群状态；
10. 设计一场有预检查、保护条件、证据、反例与复位动作的切换演练。

## 前置与后续

前置：

- [第 18 章 PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) 定义服务目标与能力放置；
- [第 19 章 部署基线](/deployment-baseline/) 交付四台独立 VM、两个 PostgreSQL 服务单元与私有 inventory；
- 读者已掌握 Linux、SQL、事务与基本网络知识；
- 不要求预先掌握 Patroni、etcd 或 Pigsty 的 HA 内部实现。

后续：

- [第 21 章 备份体系与恢复演练](/backup-recovery/) 处理基础备份、WAL 归档与 PITR；
- [第 22 章 服务接入、连接池与路由](/connection-pooling-routing/) 深入路由、连接池与客户端重试；
- 第 23 章处理传输安全、身份与密钥；
- 第 33 章在另行授权下演练非计划故障。

## 学习路径

本章的内容按一条因果链展开：先列故障域和共同依赖，定出 RPO/RTO 目标；再看 WAL 如何传输与重放、时间线如何分叉；然后是提交确认策略——数据保护与可用性在这里交换；接着是选主与隔离——谁来决定新主、旧主怎样退出；最后是服务路由与客户端语义，落到一次有保护的计划切换。

切换命令只是状态迁移的触发器。失败模型、数据风险和客户端的完成条件没有定义清楚之前，操作越快，把错误历史交给用户的速度就越快。

## 实验环境与范围

实验在第 19 章交付的本地四机沙箱上进行：

```text
target       pg36-l2-vagrant/pg-test
Pigsty       v4.4.0（正式证据记录版本；本书复现基线为 v4.5.0）
PostgreSQL   18.4（正式证据记录版本；本书复现基线为 18.6）
Patroni      4.1.3
DCS          单节点 etcd（沙箱例外）
members      pg-test-1 / pg-test-2 / pg-test-3
policy       异步复制；synchronous_mode=false
watchdog     关闭（沙箱例外）
client       Pigsty primary service, 10.10.10.11:5433
```

角色迁移过程：

```text
before          pg-test-1 主库，pg-test-2/3 流复制，timeline 5
forward         pg-test-2 主库，pg-test-1/3 流复制，timeline 6
restored        pg-test-1 主库，pg-test-2/3 流复制，timeline 7
lineage         PostgreSQL system identifier 全程不变
```

实验只覆盖健康状态下的计划切换。演练期间客户端通过 Pigsty primary service 连续写入幂等 token：120 次尝试中 95 次收到确认、25 次结果未知；确认的 95 次全部落库，未知的 25 次核对为未提交，无丢失、无重复。切换期间的采样写入间隙约 6 秒——这是单次健康计划切换的观测值，含约 0.2 秒的探测分辨率，不含故障检测阶段，不能当作生产 RTO，也不构成 SLO。

沙箱与生产的差距（共享宿主机、单 etcd、无 watchdog、异步基线、仅计划切换等十项例外）与生产批准状态记录在 [`ha-adr.md`](/labs/ch20/ha-adr.md) 与 [`requirements.json`](/labs/ch20/requirements.json)（例外 ID 清单）；完整数据与过程见 [20.7](07/)。

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

`task.sh` 的动作分级：

```text
capture / verify / review / all   L0 只读
drill:switchover                  L2 本地沙箱变更，需精确指定目标（exact target）并显式确认
reset:fixture                     破坏性动作，独立执行
```

普通 `all` 只验证已有证据，不会触发切换。

## 本章反复用到的区分

- 有备库在复制，不等于达到了 RPO 目标——取决于提交确认策略（20.3）；
- 三台节点不等于三个故障域——要看宿主机、机架与 DCS 的共同依赖（20.1）；
- Patroni 选出新主，不等于旧主已被隔离——那是 fencing 的事（20.4）；
- 切换命令返回，不等于应用已经恢复读写——路由、连接池与未知结果的处理还在后面（20.5）；
- 连接报错，不等于事务已回滚——结果未知的写入要靠幂等 token 核对（20.5）；
- HA 不等于备份——前者处理节点故障，后者处理数据损坏与误删除（第 21 章）。

一句话概括本章的立场：故障之后，让唯一一条可追溯的写入历史继续接受写入；“尽快选出一个新主库”只是实现它的手段。

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
