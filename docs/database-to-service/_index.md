---
title: 第 12 章 一气呵成：从数据库契约到后端服务
linkTitle: 12 一气呵成：从数据库契约到后端服务
weight: 220
aliases:
- "/ch12/"
- "/volume-1/database-to-service/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch12
book_number: 12
book_part: part-2
book_status: draft
---

前十一章分别建立了模型、查询、事务、诊断、索引、并发与模式发布能力。本章把这些能力压进一个真实服务边界：

```text
HTTP request
  → bounded application context
  → pgxpool acquisition
  → parameterized SQL
  → one atomic PostgreSQL transaction
       inventory invariant
       idempotency ledger
       order/payment state
       outbox event
  → commit
  → stable response
```

这里最重要的不是 Go 框架，而是接口两侧能否对同一事实达成可执行合同：

```text
application owns:
  protocol, validation, deadline, retry budget,
  response shape, trace propagation, external coordination

PostgreSQL owns:
  durable state, constraints, atomic transition,
  concurrency arbitration, idempotency record, outbox commit

Pigsty owns:
  service routing, pooler, role/database declaration,
  HA boundary, secrets delivery, monitoring and operational evidence
```

任何一层都不能替另一层“猜”。数据库约束不能替 HTTP 定义错误语义；应用先查库存也不能替原子条件更新；进程存活不能替数据库 readiness；直连成功更不能替 PgBouncer 路径验收。

## 本章目标

完成本章后，读者应当能够：

- 把 schema、query、error、compatibility 与 operations 写成数据库契约；
- 判断业务不变量应由输入校验、数据库约束、事务还是外部协议负责；
- 使用占位参数传值，并把动态 identifier 限制为受控白名单；
- 设计显式列、确定顺序、keyset cursor 与稳定 JSON 结果；
- 在服务查询中正确使用 CTE、窗口函数和 `LATERAL`；
- 使用 SQLSTATE 与命名约束映射错误，不解析本地化 message；
- 用一个事务完成库存预留、订单、幂等账本与 outbox；
- 区分领域冲突、约束拒绝、语句超时、请求取消和池获取失败；
- 只对声明的 `40001` / `40P01` 做有界整事务重试；
- 把远程 API、消息发布等外部副作用放在数据库提交边界之外；
- 计算应用侧连接池与 PgBouncer server pool 的联合预算；
- 理解 session、transaction、statement pooling 的状态边界；
- 说明 `SET LOCAL` 为什么适合 transaction pooling 内的事务上下文；
- 按 pgx 与 PgBouncer 的实际版本组合决定预备语句策略；
- 区分 liveness、startup readiness 与业务 readiness；
- 用低基数 `application_name`、trace ID、query identity 和 outbox 关联请求；
- 同时观察请求延迟、pool wait、数据库 wait、SQLSTATE 和业务结果；
- 通过 Pigsty primary service 接入生产应用，通过 direct service 做受控管理；
- 拒绝把 PostgreSQL 18.4 直连实验冒充 Pigsty/PgBouncer 已验证；
- 冻结一个可运行参考服务，并把累计规约形成 v1.0 release candidate。

## 参考服务与实验边界

本章只维护一个 Go/pgx 参考服务。它不是 Go 教程，也不是可复制到所有业务的“微服务模板”。样例只保留能验证 PostgreSQL 合同的四类接口：

```text
POST /v1/orders
  atomic inventory reservation
  request-key fingerprint
  order + item + outbox in one transaction

POST /v1/payments
  payment-key fingerprint
  exact amount and state transition
  payment + order state + outbox in one transaction

GET /v1/orders/{id}
  explicit result shape
  ordered item aggregation with LATERAL

GET /v1/orders
  keyset page
  CTE + row_number + LATERAL
```

另外提供：

```text
/health/live   process/event-loop only; no database
/health/ready  acquire pool + database/user/writable/schema contract
/metrics       request, SQLSTATE, retry and pgxpool state
/debug/hold    lab-only controlled pool/cancellation fault
```

数据库对象全部位于独立模式 `shop_ch12`。运行角色 `pg36_app`：

- 有 schema `USAGE`；
- 只获得必要的 `SELECT`、`INSERT`、`UPDATE` 与 identity sequence 权限；
- 没有 schema `CREATE`；
- 没有表 `DELETE`；
- 不能复位或修改模式；
- 不能通过服务调用任意 SQL。

实验模式保存：

```text
schema_version       exact application/database contract marker
inventory            non-negative stock and monotonic version
order_request        order idempotency key + fingerprint + response
sales_order          placed/paid state and trace
sales_order_item     quantity, unit price and generated total
payment_request      payment idempotency ledger
payment              one captured payment per order
outbox               event committed with the business transition
retry_fault_seq      lab-only non-transactional retry gate
```

setup 与 reset 都先检查对象 marker。reset 还要求精确动作令牌、精确目标、对象白名单以及零 `pg36-ch12-api` 会话；它不删除 database、role、extension 或 `shop.*`。

## 下载资产

- [实验合同](/labs/ch12/lab-contract.md)
- [上下文 guard](/labs/ch12/context.sql)
- [隔离模式与最小权限](/labs/ch12/setup.sql)
- [最终 SQL 验收](/labs/ch12/verify.sql)
- [双 token reset](/labs/ch12/reset.sql)
- [Pigsty v4.4 声明示例](/labs/ch12/pigsty-declaration.example.yml)
- [systemd 服务单元示例](/labs/ch12/pg36-api.service.example)
- [HTTP 与故障矩阵](/labs/ch12/run_service_lab.py)
- [证据审查器](/labs/ch12/review.py)
- [v1.0 release candidate](/labs/ch12/baseline-v1.0-rc.json)
- [任务入口](/labs/ch12/task.sh)
- [Go 参考服务说明与源码索引](/labs/ch12/service/README.md)

服务源码固定为一个独立 Go module：

```text
service/
  go.mod / go.sum
  main.go       lifecycle and configuration
  server.go     HTTP contract, logs and health
  store.go      parameterized SQL and transactions
  model.go      request/response/error types
  metrics.go    bounded metrics and pgxpool stats
```

本章验证的 frozen 组合是：

```text
PostgreSQL 18.4
pgx v5.10.0
Go 1.26.4 runtime
QueryExecModeExec
direct PostgreSQL service
application pgxpool MaxConns=2 in the failure lab
```

这不是“当前所有环境的默认版本”，而是证据绑定的实际组合。

## 所属位置

- 卷别：[上卷：应用开发](/upper-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第二篇：应用——从 SQL 正确走向稳定交付
- 兼容入口：`/ch12/`、`/volume-1/database-to-service/`

## 本章目录

### [12.1 数据库契约与应用边界](01/)

- [12.1.1 模式、查询、错误与兼容性契约](01/#item-12-1-1)
- [12.1.2 业务不变量在应用与数据库之间分工](01/#item-12-1-2)
- [12.1.3 迁移版本与服务发布的依赖](01/#item-12-1-3)

### [12.2 为服务设计查询接口](02/)

- [12.2.1 参数化 SQL 与稳定结果语义](02/#item-12-2-1)
- [12.2.2 CTE、窗口函数和 `LATERAL` 的工程用法](02/#item-12-2-2)
- [12.2.3 错误码、约束名与领域错误映射](02/#item-12-2-3)

### [12.3 Go 服务中的连接与事务](03/)

- [12.3.1 连接池大小、超时与上下文取消](03/#item-12-3-1)
- [12.3.2 事务函数、失败重试与外部副作用](03/#item-12-3-2)
- [12.3.3 健康检查不等于业务可用](03/#item-12-3-3)

### [12.4 会话状态与连接池陷阱](04/)

- [12.4.1 session、transaction 与 statement pooling](04/#item-12-4-1)
- [12.4.2 预备语句行为必须绑定 PgBouncer 与驱动版本](04/#item-12-4-2)
- [12.4.3 `SET LOCAL`、事务边界与 RLS 上下文](04/#item-12-4-3)
- [12.4.4 在 ch22、ch23 分别深化池化与权限](04/#item-12-4-4)

### [12.5 服务级可观测性](05/)

- [12.5.1 请求、事务、查询指纹与 `application_name`](05/#item-12-5-1)
- [12.5.2 延迟、错误、连接等待和数据库等待](05/#item-12-5-2)
- [12.5.3 从一次请求追到数据库证据](05/#item-12-5-3)

### [12.6 部署与接入 `pg36_shop`](06/)

- [12.6.1 角色、数据库、服务与凭据声明](06/#item-12-6-1)
- [12.6.2 通过连接池和服务端点接入](06/#item-12-6-2)
- [12.6.3 用平台指标验证部署，而非只看进程存活](06/#item-12-6-3)

### [12.7 实战：交付应用闭环与规约 v1.0](07/)

- [12.7.1 跑通下单、扣库存、支付幂等与查询](07/#item-12-7-1)
- [12.7.2 注入数据库超时、重试与连接耗尽](07/#item-12-7-2)
- [12.7.3 汇总 ch07–ch11 的证据，发布规约 v1.0](07/#item-12-7-3)
- [12.7.4 冻结服务样例，后续改用 SQL 与工作负载脚本](07/#item-12-7-4)

## 实测摘要

`task.sh all` 先运行完整服务矩阵，再证明错误 token、错误 target 和 active service 都不能 reset；随后执行精确 reset，从空模式重建并再次运行同一套矩阵。第二轮 PostgreSQL 18.4 证据：

```text
business:
  orders=2
  payments=1
  outbox=3
  order requests=2
  payment requests=1
  SKU-001=8:v1
  SKU-002=4:v1

idempotency:
  order replay → same 1200001 response / no second decrement
  payment replay → same 1200001 response / no second payment
  same key + different payload → 409 idempotency_conflict

failure:
  statement_timeout → 57014 / HTTP 504 / committed state unchanged
  injected 40001 → whole transaction retried once / order 1200002 once
  client timeout → backend active observed=1 / after cancel=0

pool MaxConns=2:
  two database workers held
  liveness=200
  readiness=503 pool_unavailable
  business request=503 pool_unavailable
  both holders=200
  readiness after release=200

metrics:
  transaction retries=1
  idempotent replays=2
  SQLSTATE 40001=1
  SQLSTATE 57014=1
  canceled pool acquisitions=2

security:
  current_user=pg36_app
  schema CREATE=false
  table DELETE=false
  active API query after suite=0
  ch04 checksum=f8a7bfae59c6d16cd323abecfefe1014
```

连接获取次数、持续时间、端口、PID 和时间戳不是 golden。稳定结论是状态基数、只发生一次的扣减/支付、SQLSTATE、取消清理、池耗尽时三种健康语义以及业务 checksum。

v1.0 artifact 的 canonical checksum 为：

```text
c85a930af366a9e96be7a0e166d3d0c04faace778208743718af51f633d8044d
```

状态仍是 `release-candidate`。当前没有在真实 Pigsty primary/PgBouncer 路径、PostgreSQL 14–18 矩阵和 L1 生产型负载上完成晋级证据；截止时间与本地成功都不能把未执行条件改成 PASS。

## 章节验收

1. schema、query、error、compatibility 与 operations contract 都有版本身份；
2. 约束负责可强制执行的持久不变量，应用负责协议与外部协调；
3. 库存通过条件 `UPDATE ... RETURNING` 原子预留，不先查后写；
4. idempotency key 同时绑定 payload fingerprint 与持久响应；
5. 不同 payload 复用 key 必须拒绝；
6. order/payment/outbox 在同一事务提交；
7. 事务内不调用远程支付或消息系统；
8. 所有值使用参数，动态 identifier 只能来自封闭白名单；
9. 结果显式列出字段，聚合内部有稳定 `ORDER BY`；
10. 分页使用 keyset cursor，不以 OFFSET 扫描替代；
11. SQLSTATE 和命名 constraint 是错误映射证据，不解析 message；
12. request deadline 传播到 pool acquisition 与 SQL；
13. `statement_timeout` 与 client cancellation 被区分并各自留证；
14. 只对列明的完整事务错误执行有限重试；
15. 应用 pool 与 PgBouncer server pool 共同纳入连接预算；
16. liveness 不获取数据库连接；
17. readiness 验证 database、role、writable target 与 schema marker；
18. `application_name` 低基数稳定，trace ID 不塞进连接名；
19. 日志不含 connection string、密码或完整敏感参数；
20. pool wait 与 PostgreSQL wait 分开度量；
21. transaction pooling 下不依赖跨事务 session state；
22. `SET LOCAL` 位于显式事务内；
23. pgx query mode 与 PgBouncer prepared-statement 配置按实际版本验证；
24. Pigsty primary 与 direct service 的职责没有混用；
25. reset 的 target、token、object marker 和 active-session guard 全部生效；
26. direct evidence 不被标成 pooler evidence；
27. v1.0 未满足晋级条件时保持 release candidate；
28. 参考服务在本章冻结，后续不演变成框架教程。

下一章 [ch13《言出法随：函数、触发器与存储过程》](/functions-triggers-procedures/) 将从“服务与数据库如何分工”继续深入数据库端逻辑：何时值得把规则放进函数或触发器，以及如何避免隐藏副作用。

## 参考资料

- [PostgreSQL 18：Table Expressions 与 LATERAL](https://www.postgresql.org/docs/18/queries-table-expressions.html)
- [PostgreSQL 18：WITH Queries](https://www.postgresql.org/docs/18/queries-with.html)
- [PostgreSQL 18：Window Functions](https://www.postgresql.org/docs/18/functions-window.html)
- [PostgreSQL 18：Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html)
- [PostgreSQL 18：Error Codes](https://www.postgresql.org/docs/18/errcodes-appendix.html)
- [PostgreSQL 18：Client Connection Defaults](https://www.postgresql.org/docs/18/runtime-config-client.html)
- [PostgreSQL 18：SET](https://www.postgresql.org/docs/18/sql-set.html)
- [pgx v5.10.0：pgxpool](https://pkg.go.dev/github.com/jackc/pgx/v5@v5.10.0/pgxpool)
- [pgx v5.10.0：QueryExecMode](https://pkg.go.dev/github.com/jackc/pgx/v5@v5.10.0#QueryExecMode)
- [PgBouncer：Feature map](https://www.pgbouncer.org/features.html)
- [PgBouncer：Configuration](https://www.pgbouncer.org/config.html)
- [Pigsty：Service / Access](https://pigsty.io/docs/pgsql/service/)
- [Pigsty：PgBouncer Administration](https://pigsty.io/docs/pgsql/admin/pgbouncer/)

---

[上一章：守正出奇：模式变更与安全发布](/schema-change-release/) · [返回上卷导读](/upper-volume/) · [下一章：言出法随：函数、触发器与存储过程](/functions-triggers-procedures/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
