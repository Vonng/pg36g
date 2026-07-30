# ch10 并发控制实验合同

## 教学目标

在两个真实 PostgreSQL backend 之间制造可观察、可复现的交错，并用
SQLSTATE、阻塞边和最终数据不变量区分：

1. Read Committed 读—算—写的静默 lost update；
2. 原子条件更新和 version compare-and-swap；
3. Repeatable Read 的 concurrent-update `40001`；
4. Repeatable Read write skew 与 Serializable SSI；
5. row lock、`NOWAIT`、`SKIP LOCKED` 和 deadlock；
6. session/transaction advisory lock 生命周期；
7. payment idempotency key、payload fingerprint 与 transactional outbox。

## 前置条件与专属对象

- ch04-v1/ch05 verification 通过；
- 只在确认可写、可重建的 L1/本地 PostgreSQL 运行；
- PostgreSQL 14 或更新；
- 六张 `shop_private.ch10_*` 表携带固定 marker；
- 所有 worker 使用唯一 `pg36-ch10-*` application identity；
- 协调器只使用 advisory 两整数 key space `(3610, 1001..1016)`。

`setup` 在 marker 完全匹配后重建，属于 R1。`reset` 删除专属对象，
属于 R2，需要 action/target 双 token。

## 协调方法

每个 worker 先执行关键 read/first lock，再等待专属 advisory barrier。
controller 确认所有 worker 的 `wait_event=advisory` 后同时放行。barrier
只控制教学 interleaving，不作为业务正确性机制；case 结束必须为：

```text
active pg36-ch10 worker = 0
advisory namespace 3610 / keys 1001..1016 = 0
```

PID、XID、backend_start、胜负事务、lost-update 最终为 80 还是 90，
都不是 golden value。

## 稳定断言

- lost update：两 worker 都读 100，请求总扣 30，最终为 80 或 90，
  而不是串行正确值 70；
- atomic：两个条件 UPDATE 均影响一行，最终 70/version 2；
- optimistic：首轮一成功一冲突，冲突方整事务重试后为 70/version 2；
- Repeatable Read：一提交、一条 SQLSTATE 40001，不静默覆盖；
- RR write skew：两事务都读到 on-call=2 并提交，最终 0；
- Serializable：观察到 SIReadLock，一提交、一条 40001，最终 on-call=1；
- NOWAIT：SQLSTATE 55P03；
- SKIP LOCKED：两个 worker 各领 3 个、不重复；
- deadlock：一条 40P01，幸存事务提交，两个 row value 都为 1；
- session advisory lock 跨 ROLLBACK 保留，xact lock 在事务结束释放；
- row-lock graph 有一个精确 blocker，waiter 锁定新版本 90，最终 70；
- 两个同 payload payment 请求只产生一条 payment/outbox 且响应相同；
- 同 key 不同 fingerprint 以 P0001 拒绝且状态不变；
- ch04-v1 业务 checksum 不变。

## 生产边界

自动化不在生产执行，不自动终止 backend，不改变全局
`deadlock_timeout`，不把实验 advisory namespace 当业务协议，也不调用
任何支付/消息外部系统。生产设计必须补齐：

- invariant owner、isolation/lock strategy 与 lock order；
- retryable SQLSTATE、whole-transaction replay、attempt/time budget 与 jitter；
- request identity、payload fingerprint、retention 与 response contract；
- commit-unknown、outbox relay、consumer dedup/reconciliation；
- Pigsty lock/deadlock/serialization/transaction-age 时间窗；
- 精确停止、回退与 incident owner。
