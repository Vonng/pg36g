---
title: 第 21 章 未雨绸缪：备份体系与恢复演练
linkTitle: 21 未雨绸缪：备份体系与恢复演练
weight: 310
aliases:
- "/ch21/"
- "/volume-2/backup-recovery/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch21
book_number: 21
book_part: part-4
book_status: draft
---

`pgbackrest info` 显示 `status: ok`，不等于数据可恢复；每天都生成备份，
不等于误删后能回到正确时刻；有三台流复制副本，更不等于有一份独立备份。

备份体系真正要交付的是一个可证伪的命题：

> 当某个已声明的损失场景发生时，团队能否找到一条完整、可信、权限可用的
> 恢复链，在隔离环境中把 PostgreSQL 带到预定边界，验证数据库与业务不变量，
> 再以受控方式交付服务？

这句话里没有“备份成功率”这个单一答案。它至少包含：

```text
scenario
  -> recovery point objective
      -> base backup lineage
          -> continuous WAL
              -> repository and key availability
                  -> target selection
                      -> isolated restore
                          -> PostgreSQL consistency
                              -> business validation
                                  -> controlled cutover
```

本章先从误删、介质丢失、区域故障和合规留存反推 RPO/RTO；再解释物理
基础备份、WAL、timeline 与归档链；随后把 full/diff/incr、过期、加密、
不可变和异地副本放进同一份仓库设计；最后用 Pigsty 与 pgBackRest
完成一次真实的命名恢复点演练。

本章不把成功说大：

```text
fresh full backup                 通过
named-point physical PITR         通过
base + keep / no discard          通过
isolated Unix-socket postmaster   通过
new timeline and same lineage     通过
source cluster remains healthy    通过
arbitrary-time recovery           未测试
missing WAL / lost key            未注入
immutable off-site repository     未证明
production-sized RTO              未证明
regional disaster recovery        未测试
production approval               pending
```

## 本章目标

读完并完成实验后，你应当能够：

1. 从损失场景与业务真相出发，而不是从“每天全备”出发设计恢复；
2. 区分 RPO、RTO、恢复粒度、保留周期、历史版本数和法律留存；
3. 说明逻辑备份、物理备份、存储快照、流复制与 CDC 各自能恢复什么；
4. 解释基础备份为何必须配合一条连续 WAL 链；
5. 从 `backup_label`、LSN、WAL 文件名与 timeline history 判断物理血缘；
6. 设计幂等且不会覆盖不同内容的归档路径，并理解归档积压为何会填满
   `pg_wal`；
7. 正确比较全量、差异、增量的依赖、恢复复杂度与过期语义；
8. 把加密密钥、不可变、独立凭据、异地副本与恢复权限纳入仓库合同；
9. 区分“仓库可读”“文件恢复完成”“只读可用”“提升完成”“业务可用”；
10. 正确选择 time、name、XID、LSN、inclusive/exclusive 与 timeline；
11. 在 Pigsty 中声明、观察和操作 pgBackRest，而不把平台包装当成原理；
12. 在不覆盖原集群的前提下完成一次可重放、可审计的隔离恢复；
13. 输出测量口径、证据、反例、例外与生产准入差距；
14. 知道成功恢复一次之后，下一次应该故意测试哪些失败路径。

## 前置与后续

前置：

- [第 18 章 PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) 已定义服务目标与
  责任边界；
- [第 19 章 部署基线](/deployment-baseline/) 保留了 exact Pigsty
  v4.4.0 四机沙箱；
- [第 20 章 高可用](/high-availability/) 已区分 replica、RPO、timeline
  与客户端完成条件；
- 读者已掌握 Linux、SQL、事务与基本 PostgreSQL 运维概念。

后续：

- [第 22 章 服务接入、连接池与路由](/connection-pooling-routing/) 处理恢复后如何
  把客户端安全带到正确角色；
- 第 23 章深入身份、传输、凭据与密钥；
- 后续容量、监控、变更与事故章节会把恢复证据纳入生产治理；
- 区域级 DR 和真正的 destructive replacement 必须在独立授权的演练中
  完成，不由本章沙箱命令暗中代替。

## 学习路径

```text
business loss scenario
  -> authoritative truth + tolerated loss
      -> RPO / RTO / granularity / retention
          -> logical vs physical vs snapshot vs replica
              -> base backup + WAL continuity + timeline
                  -> repository dependency graph
                      -> select backup and target
                          -> restore into isolation
                              -> wait through promotion
                                  -> database + business proof
                                      -> gaps and next drill
```

这条路径故意不从复制 `pgbackrest restore` 命令开始。恢复命令是一个高风险
状态迁移；没有目标语义、血缘、WAL、隔离和验收标准时，命令执行得越顺利，
越可能迅速得到一个“能启动但不该交付”的数据库。

## 四层恢复证明

把“可恢复”拆成四层，能避免指标替代：

| 层次 | 最低问题 | 常见证据 | 尚不能推出 |
|---|---|---|---|
| 仓库层 | 备份与 WAL 对象能否读取 | catalog、checksum、archive range | PostgreSQL 能启动 |
| 引擎层 | 能否恢复到一致状态 | recovery log、timeline、`pg_is_in_recovery()` | 目标数据正确 |
| 数据层 | 预期事实是否存在/不存在 | token、行数、约束、聚合、对账 | 应用依赖可用 |
| 服务层 | 应用能否安全接入 | routing、权限、smoke、backlog | 长期 SLO 已满足 |

本章正式实验走到数据层，并用 rollback-only write probe 证明提升后可写；
它不切换生产路由，因此没有宣称服务层 cutover 通过。

## 正式实验拓扑

```text
target           pg36-l2-vagrant/pg-test
Pigsty           v4.4.0
PostgreSQL       18.4
pgBackRest       2.59.0
source           pg-test-1, live primary, timeline 7
repository       S3-compatible MinIO, AES-256-CBC, one sandbox target
restore host     pg-test-3
live member      Patroni replica on 5432, unchanged
isolated copy    fresh path + private Unix socket + port 55432
archive push     off
recovery target  named point
target action    promote
target timeline  latest
```

实验业务边界：

```text
base      committed before fresh full backup       must exist
keep      committed after backup, before target    must exist
target    named restore point
discard   committed after target                    must not exist
```

正式观测：

```text
backup label                        20260729-201041F
backup command                         2.086 s
pgBackRest check                       0.598 s
logical backup bytes                   36,121,841
repository delta bytes                  4,539,288
restore copy                            2.758 s
start -> first connection               0.963 s
first connection state                  recovery=true, read_only=true
start -> promoted and writable          1.319 s
read-only -> promoted                   0.356 s
source timeline -> restored timeline    7 -> 8
system identifier relation              matches source
source replica lag after drill          0 bytes
counterexamples rejected                14
```

这些时间是 36 MB 级合成沙箱的一次观测，不是生产 RTO。它们最有价值的
发现反而是：

> `pg_ctl -w start` 返回时，实例可能刚进入 hot standby 的只读可用阶段，
> `recovery_target_action=promote` 尚未完成。

所以正式脚本没有把“第一条 SELECT 成功”当成恢复完成，而是继续等待
`pg_is_in_recovery() = false`，再做一次回滚写入。

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
EX21-SHARED-RESTORE-HOST
  恢复进程、目录与网络隔离，但与 live replica 共用 guest/hypervisor；
  不能声称主机、内核、设备和故障域隔离。

EX21-REPOSITORY-NOT-IMMUTABLE
  只有本地单 MinIO；未证明 object lock、独立凭据或跨区域副本。

EX21-SMALL-SYNTHETIC-DATA
  数据量很小；不能拿时间结果做生产容量规划。

EX21-NAMED-POINT-ONLY
  只验证一个命名点，并主动切 WAL 后检查；不能代表任意时间点或最坏
  归档间隙 RPO。
```

例外不是装饰性免责声明。每项都对应一个被禁止的推论，机器验收要求它们
完整保留。

## 本章目录

### [21.1 从恢复场景设计备份](01/)

- [21.1.1 误删、介质故障、区域故障与合规留存](01/#item-21-1-1)
- [21.1.2 RPO、RTO、恢复粒度与保留周期](01/#item-21-1-2)
- [21.1.3 逻辑、物理、快照和副本的职责边界](01/#item-21-1-3)

### [21.2 物理备份与 WAL 连续性](02/)

- [21.2.1 基础备份、检查点与一致性起点](02/#item-21-2-1)
- [21.2.2 归档、timeline history 与恢复链](02/#item-21-2-2)
- [21.2.3 复制槽、归档失败与 WAL 保留者](02/#item-21-2-3)

### [21.3 备份仓库与保留策略](03/)

- [21.3.1 全量、差异、增量与过期](03/#item-21-3-1)
- [21.3.2 校验、加密、不可变与异地副本](03/#item-21-3-2)
- [21.3.3 容量预算、失败告警与责任人](03/#item-21-3-3)

### [21.4 恢复流程与验证](04/)

- [21.4.1 选择备份集、目标时间和恢复位置](04/#item-21-4-1)
- [21.4.2 启动前核对时间线与 WAL 完整性](04/#item-21-4-2)
- [21.4.3 数据库一致不等于业务数据正确](04/#item-21-4-3)

### [21.5 用 pgBackRest 交付备份策略](05/)

- [21.5.1 仓库、策略、调度与凭据](05/#item-21-5-1)
- [21.5.2 备份状态、归档状态与容量观察](05/#item-21-5-2)
- [21.5.3 在隔离目标而不是原集群上恢复](05/#item-21-5-3)

### [21.6 实战：完成一次隔离恢复演练](06/)

- [21.6.1 创建已知业务检查点并执行备份](06/#item-21-6-1)
- [21.6.2 恢复到隔离集群，核对数据库与业务不变量](06/#item-21-6-2)
- [21.6.3 输出 RPO/RTO 实测、证据链和失败处理 SOP](06/#item-21-6-3)

## 实验入口

- [`lab-contract.md`](/labs/ch21/lab-contract.md)：风险、动作与解释边界；
- [`requirements.json`](/labs/ch21/requirements.json)：机器验收合同；
- [`recovery-scenarios.json`](/labs/ch21/recovery-scenarios.json)：四类恢复场景；
- [`recovery-adr.md`](/labs/ch21/recovery-adr.md)：隔离命名点恢复决策；
- [`task.sh`](/labs/ch21/task.sh)：唯一安全入口；
- [`setup.sql`](/labs/ch21/setup.sql)：三阶段 synthetic marker；
- [`restore-run.json`](/labs/ch21/restore-run.json)：无凭据、无原始 system ID 的
  正式结果；
- [`negative-cases.json`](/labs/ch21/negative-cases.json)：十四个必须拒绝的反例；
- [`topology.mmd`](/labs/ch21/topology.mmd)：数据、备份与恢复路径。

动作语义：

```text
capture / verify / review / all
  L0 read-only

drill:pitr
  guarded local sandbox mutation
  insert markers + full backup + fresh isolated restore + stopped retention

reset:fixture
  destructive and separate
  delete exactly one reviewed run only
```

`all` 只重验已有证据，不会为了演示方便再做一份备份或再启动一次恢复。

## 权威资料

原理优先以当前 PostgreSQL 18 文档为准：

- [连续归档与 PITR](https://www.postgresql.org/docs/18/continuous-archiving.html)
- [`pg_basebackup`](https://www.postgresql.org/docs/18/app-pgbasebackup.html)
- [SQL dump](https://www.postgresql.org/docs/18/backup-dump.html)
- [恢复目标设置](https://www.postgresql.org/docs/18/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET)

实现与平台入口：

- [pgBackRest User Guide](https://pgbackrest.org/user-guide.html)
- [Pigsty Backup & Restore](https://pigsty.io/docs/pgsql/backup/)
- [Pigsty Backup Admin Commands](https://pigsty.io/docs/pgsql/backup/admin/)
- [Pigsty Restore Operations](https://pigsty.io/docs/pgsql/backup/restore/)
- [Pigsty Backup Repository](https://pigsty.io/docs/pgsql/backup/repository/)

版本相关命令在使用前应回到对应版本文档核对。本章 formal evidence 固定
在 Pigsty v4.4.0、PostgreSQL 18.4 与 pgBackRest 2.59.0；“当前文档入口”
不是“历史版本命令完全相同”的承诺。

## 本章最重要的判断

```text
backup command succeeded        != recoverable
catalog status ok               != WAL chain complete for every target
replica healthy                 != independent backup
physical restore started        != recovery complete
read-only query succeeded       != promotion complete
PostgreSQL consistent           != business truth correct
one fast sandbox restore        != production RTO
encrypted repository            != ransomware resistance
retained for 14 days            != 14 days of arbitrary PITR
restore directory retained      != service approved
```

真正的完成条件是：

```text
declared scenario
+ selected truth boundary
+ complete lineage and WAL
+ isolated executable restore
+ engine and business proof
+ controlled service decision
+ explicit residual risk
```

下一节从第一项开始：先定义究竟要从什么损失中恢复。

---

[上一章：狡兔三窟：高可用拓扑与容灾目标](/high-availability/) · [返回下卷导读](/lower-volume/) · [下一章：四通八达：服务接入、连接池与路由](/connection-pooling-routing/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
