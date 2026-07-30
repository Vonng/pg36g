---
title: 第 33 章 故障切换与集群重建——力挽狂澜
linkTitle: 33 故障切换与集群重建——力挽狂澜
weight: 430
aliases:
- "/ch33/"
- "/volume-2/failover-rebuild/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch33
book_number: 33
book_part: part-6
book_status: draft
---

第 20 章演练的是**健康集群上的计划切换**；第 31 章要求事故处理中先保护现场、分清
事实与假设；第 32 章处理“集群健康、数据却已经写错”的 PITR。本章面对另一条恢复
路线：

> 原主库已经不可用或不再可信，怎样在不制造两个可写主库的前提下接受新主库，并让
> 旧主库安全归队？

这不是一条 `failover` 命令的问题。操作者必须连续回答三个不同问题：

```text
failure diagnosis
  客户端失败发生在哪一层，数据库真的失去主库了吗？

authority
  哪个节点仍有权写；旧主是否已围栏；谁有资格成为候选？

lineage repair
  旧主与新主是否已经分叉；可以 rewind，还是必须从可信源全量重建？
```

把三问混在一起，会产生两类相反事故：代理故障被误判成数据库故障，执行了一次多余
promotion；真正的主机分区又被当成普通进程退出，在旧主仍可能写时接受了新主。

## 学习完成标准

完成本章后，读者应能：

1. 区分 PostgreSQL 进程、主机、存储、复制、DCS、代理与客户端失败；
2. 从用户症状反向追踪服务路径，而不是把“连不上”直接翻译成“主库宕机”；
3. 用 Patroni、SQL、操作系统、DCS 与客户端证据共同判定当前数据库角色；
4. 解释 WAL 的 sent、write、flush、replay 位置分别代表什么；
5. 解释 timeline history、共同祖先与历史分叉，而不是把 timeline 当版本号；
6. 理解“数据看起来最新”只是候选条件之一，不等于可安全提升；
7. 列出 Patroni 候选的可达性、tag、lag、timeline、同步状态与 watchdog 条件；
8. 区分 DCS 多数派、PostgreSQL 副本数量和业务写多数派，避免混用“quorum”；
9. 解释 `failsafe_mode` 为什么要求 incumbent primary 联系全部已知成员；
10. 为旧主选择进程、watchdog、云/虚拟化、电源、存储或网络 fence，并写出证据；
11. 区分 automatic failover、planned switchover 与 manual failover；
12. 在自动化不能证明 authority 时停下来转人工，而不是强制选一个候选；
13. 判断 `pg_rewind` 的 lineage、停机、checksums/`wal_log_hints`、WAL 与权限前提；
14. 在 rewind 失败或前提不明时，转向可信 backup 或 fresh base backup；
15. 重建后复核复制槽、连接端点、客户端未知结果、监控和备份；
16. 分开报告检测时间、围栏时间、控制面恢复、客户端写缺口与数据损失；
17. 用 Pigsty/Patroni 命令执行动作，再回到 PostgreSQL 原生证据验收；
18. 输出一份包含失败域、authority、timeline、token 对账、复位与结论边界的证据包。

## 三个平面，四道门

一次 HA 事故至少横跨三个平面：

| 平面 | 关键事实 | 典型证据 |
|---|---|---|
| 数据面 | 谁可写、WAL 到哪里、哪条 timeline | `pg_is_in_recovery()`、LSN、sender/receiver、control data |
| 控制面 | 谁持有 leader lock、谁可竞选、自动化是否暂停 | Patroni REST/CLI、DCS revision、动态配置、tags |
| 服务面 | 客户实际连到哪里、池与代理何时摘挂节点 | HAProxy/PgBouncer health、DNS/VIP、端到端 token |

恢复路径依次通过四道门：

```text
诊断门
  失败域与影响边界是否有多源证据？

围栏门
  旧主是持有有效 authority，还是已经被证明不能写？

候选门
  新主是否同 lineage、可达、合格且在可接受数据风险内？

交付门
  路由、未知结果、归队副本、监控、归档和备份是否重新健康？
```

任何一道门为 unknown，都不能用“业务很急”把 unknown 改写成 true。可以在事故指挥下
明确承担风险，但风险接受必须被记录，不能藏在 `--force` 后面。

## 本章的核心不变量

故障切换不是“副本变成主库”，而是维持下面的不变量：

$$
\left|\text{accepted writable primary}\right| = 1
$$

这里的 accepted 很重要。网络分区两侧可能各有一个 `pg_is_in_recovery()=false` 的
PostgreSQL；只看本机 SQL 会得到两个“主库”。要让其中一个可被系统接受，还必须有
authority 与 fence：

```text
accepted primary
  = writable PostgreSQL
  + valid control-plane authority
  + old-primary exclusion
  + admissible lineage
  + service-route acceptance
```

路由摘除只能防止正常客户端访问旧主，不等于围栏。定时任务、直连、复制、维护脚本或
网络另一侧仍可能写入旧主。真正的 fence 必须使它失去写能力，或至少使它无法继续产生
会被业务接受的状态，并能由独立证据验证。

## 正式实验

本章在已确认的四节点 Pigsty 开发沙箱完成两段真实实验。

第一段对 managed `pg-test`：

```text
initial primary       pg-test-1
eligible replicas     pg-test-2, pg-test-3
fault                 guarded systemctl stop patroni on pg-test-1
candidate             not forced; selected by Patroni at runtime
client                200 ms idempotent INSERT through port 5433
rejoin                start pg-test-1 and require streaming
baseline restore      planned switchover to pg-test-1
DCS/network mutation  none
managed reinit        none
```

实际候选是 `pg-test-3`。这不是脚本预期之外的杂音，而是实验最重要的结果之一：
自动竞选必须接受“任一满足条件的副本”，runbook 不能把某个候选预写成已经发生的事实。

正式观测：

```text
timeline                         17 -> 18 -> 19
Patroni service stop             1.582 s
action start -> process fence    1.817 s
action start -> topology stable  4.536 s
old primary start -> streaming   2.527 s
planned baseline switchover      2.832 s

client attempts                  160
acknowledged                     130
unknown                          30
acknowledged missing             0
duplicate tokens                 0
unreconciled unknown             0
maximum acknowledgement gap      6.212 s
```

服务路径通过 Unix socket 回源，`inet_server_addr()` 为 NULL，因此 runner 没有伪造
后端地址，而是用“客户端观察到的 timeline + 同期 Patroni 拓扑”归属提交：旧 timeline
确认 18 次，新 timeline 确认 112 次。

第二段在 `pg-test-3` 的一次性目录创建同源临时集群 A/B/C：

```text
A -> basebackup -> B
stop A
promote B and write new-primary branch
stop B
start A alone and write old-primary-divergent branch
stop A; restart B
pg_rewind A from B -R
start A as streaming standby
fresh pg_basebackup C -R from B
start C as streaming standby
stop all and remove exact root
```

两个分叉 primary 从不同时运行。结果：

```text
same system identifier           true
timeline diverged                true
pg_rewind                        0.245 s
rewound A streaming              true
B branch markers on A            present
A divergent marker after rewind  absent
fresh pg_basebackup              0.228 s
C streaming                      true
temporary root removed           true
```

这些是几十 MB 的本机虚拟化沙箱观测，不是生产 RTO。环境使用异步复制、单 etcd、
watchdog off；没有注入断电、存储故障、真实网络分区，也没有执行破坏性的 managed
`reinit`。最终门禁保持 `production_ch33_gate=pending`。

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第六篇：出山——按响应目标演练恢复与改进
- 前置：[第 20 章 高可用拓扑与容灾目标](/high-availability/)、
  [第 31 章 事件分级、现场保护与应急决策](/incident-response/)
- 后续：[第 34 章 过载保护与资源故障判型](/overload-resource-incidents/)
- 兼容入口：`/ch33/`、`/volume-2/failover-rebuild/`

## 本章目录

### [33.1 先识别失败域](01/)

- [33.1.1 进程失败、主机失败与存储失败](01/#item-33-1-1)
- [33.1.2 网络分区、客户端不可达与代理误判](01/#item-33-1-2)
- [33.1.3 主库失败、复制停滞与控制面失败](01/#item-33-1-3)

### [33.2 复制状态与时间线证据](02/)

- [33.2.1 发送、接收、重放位置与延迟](02/#item-33-2-1)
- [33.2.2 timeline、历史文件与分叉](02/#item-33-2-2)
- [33.2.3 数据最新不等于可以安全提升](02/#item-33-2-3)

### [33.3 自动故障转移的保护条件](03/)

- [33.3.1 候选健康、数据风险与多数判断](03/#item-33-3-1)
- [33.3.2 fencing 旧主与防止双写](03/#item-33-3-2)
- [33.3.3 自动化不确定时何时转人工](03/#item-33-3-3)

### [33.4 DCS 故障的安全处理](04/)

- [33.4.1 DCS 不可达、失去多数与延迟](04/#item-33-4-1)
- [33.4.2 先保护当前数据库角色，不盲目重置选举状态](04/#item-33-4-2)
- [33.4.3 恢复控制面后核对 leader lock 与数据库事实](04/#item-33-4-3)

### [33.5 旧主重加入与集群重建](05/)

- [33.5.1 `pg_rewind` 的前提、失败与验证](05/#item-33-5-1)
- [33.5.2 从备份或新基础备份重建](05/#item-33-5-2)
- [33.5.3 复制槽、端点和客户端状态清理](05/#item-33-5-3)

### [33.6 切换与重建 runbook](06/)

- [33.6.1 计划切换、故障切换与人工干预入口](06/#item-33-6-1)
- [33.6.2 Patroni、DCS、代理和 SQL 证据互证](06/#item-33-6-2)
- [33.6.3 集群恢复后重新建立监控与备份健康](06/#item-33-6-3)

### [33.7 实战：主库故障与 DCS 干扰](07/)

- [33.7.1 随机注入主机、网络或 DCS 症状](07/#item-33-7-1)
- [33.7.2 保护旧主、选择候选、测量 RTO/RPO](07/#item-33-7-2)
- [33.7.3 重建旧主并验证时间线、端点和业务写入](07/#item-33-7-3)

## 权威参考

PostgreSQL：

- [Failover](https://www.postgresql.org/docs/18/warm-standby-failover.html)
- [Log-Shipping Standby Servers](https://www.postgresql.org/docs/18/warm-standby.html)
- [`pg_rewind`](https://www.postgresql.org/docs/18/app-pgrewind.html)
- [Monitoring Database Activity](https://www.postgresql.org/docs/18/monitoring.html)

Patroni：

- [Replication Modes](https://patroni.readthedocs.io/en/latest/replication_modes.html)
- [REST API and candidate checks](https://patroni.readthedocs.io/en/latest/rest_api.html)
- [DCS Failsafe Mode](https://patroni.readthedocs.io/en/latest/dcs_failsafe_mode.html)
- [Watchdog Support](https://patroni.readthedocs.io/en/latest/watchdog.html)

Pigsty：

- [High Availability](https://pigsty.io/docs/concept/ha/)
- [`pig pt`](https://pigsty.io/docs/pig/pt/)
- [PostgreSQL Parameters: Patroni and watchdog](https://pigsty.io/docs/pgsql/param/)
- [Security and Availability](https://pigsty.io/docs/deploy/security/)

---

[上一章：PITR 与误操作恢复——妙手回春](/pitr/) · [返回下卷导读](/lower-volume/) · [下一章：过载保护与资源故障判型——李代桃僵](/overload-resource-incidents/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
