---
title: 第 32 章 PITR 与误操作恢复——妙手回春
linkTitle: 32 PITR 与误操作恢复——妙手回春
weight: 420
aliases:
- "/ch32/"
- "/volume-2/pitr/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch32
book_number: 32
book_part: part-6
book_status: draft
---

第 21 章已经证明一条基础备份与连续 WAL 可以在隔离实例中恢复；第 31 章又要求事故
响应先保护现场、明确目标，再授权动作。本章把两者接起来，处理一种尤其危险的情况：

> PostgreSQL 没有宕机，复制、监控甚至备份都显示正常，但一笔已经提交的事务把业务
> 数据改错了。

同步副本会忠实重放错误，HA 切换不会让错误消失；物理 PITR 又会把**整个 cluster**
带回旧状态，连错误之后的合法写入一起拿走。因此“执行恢复命令”只占很小一部分，
真正的工作是：

```text
界定事故
  -> 固定提交边界与事后合法写集
      -> 选择能覆盖目标的 backup + WAL + timeline
          -> 在隔离环境恢复多个候选
              -> 证明目标事务存在或不存在
                  -> 合并目标之后的合法事实
                      -> 控制外部副作用
                          -> 决定提取、修补或整库切换
```

本章正式实验故意恢复两个候选。第一个使用默认的 inclusive XID 语义，错误事务被重放，
所以必须否决；第二个使用 exclusive XID，安全事务存在而错误事务不存在，才可作为历史
正确状态。实验随后证明一个更重要的反例：直接切到第二个候选会丢掉目标之后 100 笔合法
写入，只有经过审计对账，最终业务状态才完整。

## 学习完成标准

完成本章后，读者应能：

1. 区分误更新、误删除、误 DDL、批处理越界和外部副作用事故；
2. 写出影响对象、错误事务、持续写入、事后合法写与业务真相来源；
3. 在逻辑补偿、从恢复副本提取对象、整库 PITR 之间作出有条件的选择；
4. 正确比较 time、XID、LSN、name、immediate 与 end-of-WAL 目标；
5. 解释 `recovery_target_inclusive` 为什么会决定错误事务是否被保留；
6. 理解 XID 按事务开始分配而按提交顺序恢复，不能把数字大小当提交顺序；
7. 根据 backup lineage 与 timeline history 选择 `current`、`latest` 或明确 timeline；
8. 把时区、时钟偏差、日志延迟和事务时间语义写入目标误差预算；
9. 使用 Pigsty `pig pitr --plan` 审阅真实恢复计划，并区分 managed restore 与 side
   restore；
10. 在不覆盖原集群、不接入 Patroni、不开放 TCP、不回写 archive 的环境中恢复候选；
11. 用 PostgreSQL 日志、recovery 配置、控制信息与 SQL 共同判断恢复进度；
12. 以对象 manifest、关键交易和跨表不变量验证数据，而不是只看实例能启动；
13. 用条件写入把历史正确值与目标之后的合法增量合并，并在不匹配时整批回滚；
14. 隔离 outbox、定时任务、CDC、邮件、支付和 webhook，防止恢复副本制造第二次事故；
15. 区分“历史候选正确”“对账完成”“服务可切换”和“生产已批准”；
16. 输出一份可复核的 target、backup、WAL、timeline、验证、清理与决策证据包。

## 这不是“把时间拨回去”

物理 PITR 的输入和输出可以写成：

$$
C(T,\tau)=B(T_b)+W(T_b \rightarrow T,\tau)
$$

其中：

- $B$ 是结束于目标之前的某份物理基础备份；
- $W$ 是从该备份一致点开始的连续 WAL；
- $T$ 是恢复目标；
- $\tau$ 是所选 timeline；
- $C$ 是**整个 PostgreSQL cluster** 在该历史分支上的一致状态。

这个公式没有说 $C$ 就是现在应交付给用户的业务状态。若错误提交点为 $T_e$，当前时刻
为 $T_n$，则还存在两类信息：

```text
good_before   在 Te 之前且应保留的事实
bad_at        在 Te 提交的错误事务及其副作用
good_after    在 Te 之后仍然合法的提交
```

exclusive PITR 可以得到 `good_before`，但不会自动得到 `good_after`；外部支付、邮件或消息
也不在物理数据目录里。最终状态通常更接近：

$$
S_{\text{final}}
  = S_{\text{exclusive before }T_e}
  \oplus \Delta_{\text{good after}}
  \oplus \text{external reconciliation}
$$

这里的 $\oplus$ 不是盲目覆盖，而是带身份、顺序、幂等键和前置状态检查的业务合并。

## 从事故到交付的七道门

| 决策门 | 必须回答 | 缺失时 |
|---|---|---|
| 事故门 | 哪些对象错、哪笔提交错、错误是否仍继续 | 只保护现场，不恢复 |
| 真相门 | 历史正确值与事后合法事实分别来自哪里 | 升级业务 owner |
| 血缘门 | 哪份 backup 结束于目标前，WAL 是否连续，timeline 是哪条 | 阻断 restore |
| 隔离门 | 是否保留原集群、关闭路由与外部副作用 | 不启动候选 |
| 目标门 | inclusive/exclusive 的可证伪预期是什么 | 至少恢复两个候选 |
| 数据门 | manifest、不变量与副作用对账是否通过 | 不切流 |
| 服务门 | 写围栏、路由、观察窗、回退与 owner 是否齐备 | `production gate=pending` |

严重度不能替代这些门。即便是 SEV1，也不能因为“时间紧”就跳过 timeline 或外部副作用
判断；即便只错一行，也可能因为已经触发支付而需要跨系统对账。

## 与第 21 章的分工

| 第 21 章 | 本章 |
|---|---|
| 从损失场景设计备份体系 | 从已发生的误操作界定恢复边界 |
| 证明 full backup + WAL 可恢复 | 证明目标事务能被精确包含或排除 |
| 使用预先创建的 named restore point | 从 source audit 独立取得真实 damage XID |
| 验证 keep 存在、discard 不存在 | 验证 safe、damage、post-target 三类提交 |
| 保留停止后的恢复目录 | 验证后删除两个一次性候选 |
| 不处理事后合法写入 | 实际对账并保留 100 笔合法写 |

两章共同坚持：repository `status=ok` 不是恢复证明，第一条查询成功也不是恢复完成，
恢复工具成功更不是业务可用。

## 正式实验与结论边界

参考实验运行于已确认的四节点 Pigsty 开发沙箱：

```text
target             pg36-l2-vagrant/pg-test
source             pg-test-1, managed primary
restore host       pg-test-3, live replica remains unchanged
PostgreSQL         18.4
Pig                1.5.1
pgBackRest         2.59.0
fixture            5,000 accounts
random victims     1,000 contiguous accounts
safe-before        +100 cents to every victim
damage             set 1,000 balances to zero + 1,000 pending outbox rows
good-after         +700 cents to first 100 victims
target             damage XID from source audit
restore            exact fresh full backup, timeline=current
isolation          custom -D, no restart, Unix socket only, archive off
```

正式观测：

```text
fresh full backup                    2.090 s
backup logical / repository delta    42,355,954 / 5,751,304 bytes
pgBackRest check                     0.630 s
target identification               0.183 s
inclusive plan / restore             0.219 s / 3.040 s
inclusive start -> promoted/validate 0.961 s / 0.340 s
inclusive damage present             true
inclusive accepted                   false
exclusive plan / restore             0.214 s / 2.974 s
exclusive start -> promoted/validate 0.939 s / 0.503 s
exclusive safe present               true
exclusive damage/post present        false / false
exclusive accepted                   true
raw exclusive legitimate writes lost 100
reconciled legitimate writes kept    100
reconciliation                      0.200 s
conditional rows repaired            1,000
wrong outbox rows canceled            1,000
external dispatch                         0
fixture data loss after reconcile         0
source -> candidate timeline          11 -> 12
```

最终还证明：

```text
source Patroni topology unchanged    true
managed PGDATA touched               false
DCS / route changed                  false / false
TCP listener created                 false
fixture schema removed               true
side restore roots removed           true
fresh backup retained                true
backup or WAL deleted                false
declared counterexamples rejected    32
live evidence mutants rejected       32
source files hash-bound              12
production_ch32_gate                 pending
```

这些时间只是 42.4 MB 合成沙箱的一次观测，不能外推生产 RTO。实验没有切业务路由，没有
测试并发交错事务、缺失 WAL、加密密钥丢失、区域故障、真实支付补偿，也没有批准生产
操作。

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第六篇：出山——按响应目标演练恢复与改进
- 前置：[第 21 章 备份体系与恢复演练](/backup-recovery/)、
  [第 31 章 事件分级、现场保护与应急决策](/incident-response/)
- 后续：[第 33 章 故障切换与集群重建](/failover-rebuild/)
- 兼容入口：`/ch32/`、`/volume-2/pitr/`

## 本章目录

### [32.1 先界定误操作](01/)

- [32.1.1 错误 UPDATE、DELETE、DROP 与批处理](01/#item-32-1-1)
- [32.1.2 影响对象、开始时间、结束时间和持续写入](01/#item-32-1-2)
- [32.1.3 逻辑补偿、对象恢复与整库 PITR 的选择](01/#item-32-1-3)

### [32.2 恢复目标与时间线](02/)

- [32.2.1 时间、LSN、事务 ID 与命名恢复点](02/#item-32-2-1)
- [32.2.2 timeline 分叉与“恢复到刚刚之前”](02/#item-32-2-2)
- [32.2.3 时钟、时区和证据误差](02/#item-32-2-3)

### [32.3 隔离恢复策略](03/)

- [32.3.1 不覆盖仍可取证的原集群](03/#item-32-3-1)
- [32.3.2 选择备份、WAL 与目标环境](03/#item-32-3-2)
- [32.3.3 控制网络、凭据和外部副作用](03/#item-32-3-3)

### [32.4 执行恢复并观察进度](04/)

- [32.4.1 从已验证备份克隆恢复目标](04/#item-32-4-1)
- [32.4.2 监控 WAL 重放、目标达成与启动状态](04/#item-32-4-2)
- [32.4.3 用原生文件、日志和 SQL 复核工具状态](04/#item-32-4-3)

### [32.5 数据验证与安全回切](05/)

- [32.5.1 行数、摘要、关键交易与跨表不变量](05/#item-32-5-1)
- [32.5.2 提取差异、逻辑补回或切换整个服务](05/#item-32-5-2)
- [32.5.3 防止恢复环境向外重复发送消息和支付](05/#item-32-5-3)

### [32.6 实战：随机恢复目标演练](06/)

- [32.6.1 在隐藏时间窗内注入误更新](06/#item-32-6-1)
- [32.6.2 独立定位目标、恢复、验证与回切](06/#item-32-6-2)
- [32.6.3 测量 RPO/RTO 并记录版本迁移工时](06/#item-32-6-3)
- [32.6.4 输出恢复证据和备份体系改进项](06/#item-32-6-4)

## 权威参考

PostgreSQL：

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/18/continuous-archiving.html)
- [Recovery Target Settings](https://www.postgresql.org/docs/18/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET)
- [Backup Control Functions](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADMIN-BACKUP)
- [Recovery Information Functions](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-RECOVERY-INFO-TABLE)
- [Control Data Functions](https://www.postgresql.org/docs/18/functions-info.html#FUNCTIONS-CONTROLDATA)

Pigsty：

- [`pig pitr`](https://pigsty.io/docs/pig/pitr/)
- [Point-in-Time Recovery](https://pigsty.io/docs/concept/pitr/)
- [Backup & Restore](https://pigsty.io/docs/pgsql/backup/)
- [Restore Operations](https://pigsty.io/docs/pgsql/backup/restore/)

---

[上一章：事件分级、现场保护与应急决策——枕戈待旦](/incident-response/) · [返回下卷导读](/lower-volume/) · [下一章：故障切换与集群重建——力挽狂澜](/failover-rebuild/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
