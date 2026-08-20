---
title: 第 10 章 顾此失彼：并发控制与隔离异常
linkTitle: 10 顾此失彼：并发控制与隔离异常
weight: 200
aliases:
- "/ch10/"
- "/volume-1/concurrency-isolation/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch10
book_number: 10
book_part: part-2
book_status: draft
---

单条 SQL 正确、单个事务顺序执行正确，不代表并发执行仍正确。并发控制的起点不是先选隔离级别，而是写出业务不变量和允许的失败语义：

```text
business invariant
  → concurrent read/write set and possible interleavings
  → snapshot/isolation guarantee
  → atomic SQL, row lock, optimistic CAS, SSI or advisory coordination
  → retryable SQLSTATE + whole-transaction replay
  → idempotency and external-effect protocol
  → lock/error/latency evidence
  → two-connection invariant test
```

PostgreSQL 的 Read Committed、Repeatable Read 与 Serializable 不是“性能低、中、高”的旋钮。它们允许或拒绝的交错不同；拒绝通常表现为需要应用处理的 `40001`，不是数据库自动把原事务重新执行。

## 本章目标

完成本章后，读者应当能够：

- 区分 Read Committed 的语句快照与 Repeatable Read 的事务快照；
- 知道 PostgreSQL 的 Read Uncommitted 实际等同 Read Committed；
- 解释 PostgreSQL Repeatable Read 是 snapshot isolation，仍允许 write skew；
- 说明 Serializable Snapshot Isolation 如何用 `SIReadLock` 识别危险依赖；
- 把 `40001` 理解为“整个事务必须重放”，而非重试最后一条 SQL；
- 用确定性交错重现 read–compute–write lost update；
- 用 `SET col = col - $1 WHERE ...` 做原子条件更新；
- 用 version compare-and-swap 识别并处理乐观冲突；
- 区分 `FOR UPDATE`、`FOR NO KEY UPDATE`、`FOR SHARE` 与 `FOR KEY SHARE`；
- 正确选择 `NOWAIT`、`SKIP LOCKED`，并说明后者为何只适合 queue-like workload；
- 建立统一 lock order，识别 `40P01` 并回放整个事务；
- 区分 session-level 与 transaction-level advisory lock 生命周期；
- 设计 advisory key namespace、owner、timeout 与释放协议；
- 使用 `pg_stat_activity`、`pg_locks` 和 `pg_blocking_pids()` 保存精确阻塞图；
- 用 Pigsty 的 Activity/Xacts/PGCAT Locks/日志时间窗量化并发问题；
- 设计 payment idempotency key、payload fingerprint 与响应复用；
- 用 transactional outbox 跨越数据库 commit 与外部消息边界；
- 把隔离、重试、幂等与外部副作用要求追加到 `DEFAULT-TXNN-007`。

## 实验边界

实验基线为 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04 L1；主体机制保持 PostgreSQL 14–18 可用。只创建六张带固定 marker 的表：

```text
ch10_inventory        two SKUs / available=100 / version=0
ch10_doctor           two on-call doctors
ch10_deadlock_probe   two lock-order rows
ch10_job              six queued jobs
ch10_payment_request  idempotency authority
ch10_outbox            committed external-effect intent
```

协调器使用 advisory 两整数 key space：

```text
(3610, 1001..1016)
```

它只控制教学 interleaving，不参与业务正确性。每个 case 后必须 worker=0、barrier lock=0。`setup` 在 marker 匹配后重建，属于 R1；`reset` 属于 R2，需要 action/target 双 token。

下载资产：

- [实验合同](/labs/ch10/lab-contract.md)
- [上下文 guard](/labs/ch10/context.sql)
- [确定性 fixture](/labs/ch10/setup.sql)
- [并发协调与断言器](/labs/ch10/run_concurrency.py)
- [lost-update worker](/labs/ch10/lost-update-worker.sql)
- [原子更新 worker](/labs/ch10/atomic-update-worker.sql)
- [乐观更新 worker](/labs/ch10/optimistic-worker.sql)
- [乐观重试](/labs/ch10/optimistic-retry.sql)
- [Repeatable Read worker](/labs/ch10/repeatable-update-worker.sql)
- [write-skew/SSI worker](/labs/ch10/doctor-worker.sql)
- [行锁 holder](/labs/ch10/row-lock-holder.sql)
- [行锁 waiter](/labs/ch10/row-lock-waiter.sql)
- [`NOWAIT` probe](/labs/ch10/nowait-worker.sql)
- [`SKIP LOCKED` worker](/labs/ch10/job-worker.sql)
- [deadlock worker](/labs/ch10/deadlock-worker.sql)
- [payment idempotency worker](/labs/ch10/payment-worker.sql)
- [不同 payload 反例](/labs/ch10/payment-mismatch.sql)
- [最终状态验收](/labs/ch10/verify.sql)
- [双 token reset](/labs/ch10/reset.sql)
- [语义审查器](/labs/ch10/review.py)
- [v0.5 规则提案](/labs/ch10/baseline-v0.5-proposal.json)
- [任务入口](/labs/ch10/task.sh)

## 本章目录

### [10.1 隔离级别与可观察现象](01/)

- [10.1.1 Read Committed 的语句快照](01/#item-10-1-1)
- [10.1.2 Repeatable Read 的事务快照与写冲突](01/#item-10-1-2)
- [10.1.3 Serializable、谓词冲突与序列化失败](01/#item-10-1-3)

### [10.2 Lost update 不是一句口号](02/)

- [10.2.1 读—算—写在 Read Committed 下如何丢更新](02/#item-10-2-1)
- [10.2.2 原子更新与带版本条件的更新](02/#item-10-2-2)
- [10.2.3 更高隔离级别何时拒绝而不是静默覆盖](02/#item-10-2-3)

### [10.3 悲观锁与锁队列](03/)

- [10.3.1 `FOR UPDATE`、`NO KEY UPDATE` 与引用关系](03/#item-10-3-1)
- [10.3.2 `NOWAIT`、`SKIP LOCKED` 与任务领取](03/#item-10-3-2)
- [10.3.3 锁顺序、阻塞链与死锁](03/#item-10-3-3)

### [10.4 乐观控制、重试与幂等](04/)

- [10.4.1 版本列、唯一键与条件写入](04/#item-10-4-1)
- [10.4.2 重试只包围可重放的事务](04/#item-10-4-2)
- [10.4.3 支付、消息与外部副作用的边界](04/#item-10-4-3)

### [10.5 咨询锁与跨行协调](05/)

- [10.5.1 会话级与事务级咨询锁](05/#item-10-5-1)
- [10.5.2 键空间、碰撞与所有权](05/#item-10-5-2)
- [10.5.3 不用咨询锁掩盖缺失的数据约束](05/#item-10-5-3)

### [10.6 观察与诊断并发](06/)

- [10.6.1 `pg_stat_activity`、`pg_locks` 与等待事件](06/#item-10-6-1)
- [10.6.2 从 Pigsty 定位锁等待与长事务](06/#item-10-6-2)
- [10.6.3 保存阻塞图，而不是先杀会话](06/#item-10-6-3)

### [10.7 实战：库存扣减与支付幂等](07/)

- [10.7.1 在指定隔离级别重现丢更新和死锁](07/#item-10-7-1)
- [10.7.2 比较原子更新、行锁与可重试事务](07/#item-10-7-2)
- [10.7.3 用并发测试验证业务不变量并追加规约](07/#item-10-7-3)

## 实测摘要

一次 PostgreSQL 18.4 全量验收得到：

```text
lost:
  both read 100 / requested total 30
  serial expected 70 / actual 80 or 90

safe writes:
  atomic → 2 successes / final 70 / version 2
  optimistic → first 1 success + 1 conflict
               whole retry 1 success / final 70 / version 2

isolation:
  Repeatable Read same-row update → 1 commit + one 40001
  Repeatable Read write skew      → 2 commits / on-call 0
  Serializable write skew         → SIReadLock observed
                                    1 commit + one 40001 / on-call 1

locks:
  NOWAIT=55P03
  deadlock=one 40P01 / survivor leaves rows [1,1]
  SKIP LOCKED=two workers × 3 / duplicate 0
  row lock=one blocker edge / waiter sees 90 / final 70

idempotency:
  concurrent requests 2 / inserted 1 / reused 1
  payment 1 / outbox 1 / distinct response 1
  same key different payload=P0001 / state unchanged

final:
  worker=0 / advisory barrier=0
  relation checksum=f8a7bfae59c6d16cd323abecfefe1014
```

胜出事务、PID、XID、backend_start、lost-update 最终是 80 还是 90 都不是 golden。稳定断言是允许/拒绝的交错、SQLSTATE、多连接关系、业务不变量和最终清理。

## 章节验收

1. 每个并发写先声明 invariant、read set、write set 与 failure contract；
2. Read Committed 的两条普通 `SELECT` 可见不同已提交状态；
3. `UPDATE SET x=x+...` 与 application read–compute–write 的语义差别明确；
4. optimistic zero-row update 被当冲突，而非成功；
5. Repeatable Read concurrent row update 以 40001 拒绝；
6. Repeatable Read write skew 反例被实际重现；
7. Serializable 的 `SIReadLock` 和 40001 都有 raw evidence；
8. 整事务 retry 有 attempt/time budget、backoff/jitter 与新 snapshot；
9. row lock mode 与 foreign-key key update 边界正确；
10. `NOWAIT` 55P03、`SKIP LOCKED` queue-only 边界明确；
11. 所有多行写有统一 lock order，40P01 仍被整事务处理；
12. advisory key namespace/lifetime/owner/timeout 可审计；
13. 阻塞动作使用 PID + backend_start + database + application identity；
14. Pigsty 时间窗能落回 exact blocker graph、SQLSTATE 与 transaction age；
15. idempotency key 绑定 payload fingerprint 与 response；
16. 相同 key 不同 payload 必须拒绝；
17. 数据库事务内只写 outbox，不调用远程支付/消息；
18. `task.sh all`、双 token reset 与错误 token 反例均通过；
19. 最终 worker/advisory=0，业务 checksum 不变；
20. v0.5 仍是有依赖的 candidate，不冒充已发布 baseline。

下一章 [ch11《守正出奇：模式变更与安全发布》](/schema-change-release/) 将把本章的锁、事务与兼容语义应用到真实 DDL 发布。

## 参考资料

- [PostgreSQL 18：Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html)
- [PostgreSQL 18：Explicit Locking](https://www.postgresql.org/docs/18/explicit-locking.html)
- [PostgreSQL 18：Serialization Failure Handling](https://www.postgresql.org/docs/18/mvcc-serialization-failure-handling.html)
- [PostgreSQL 18：Advisory Lock Functions](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS)
- [Pigsty：PostgreSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)

---

[上一章：巧夺天工：索引设计与效果验证](/index-design/) · [返回上卷导读](/upper-volume/) · [下一章：守正出奇：模式变更与安全发布](/schema-change-release/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
