---
title: 第 22 章 四通八达：服务接入、连接池与路由
linkTitle: 22 四通八达：服务接入、连接池与路由
weight: 320
aliases:
- "/ch22/"
- "/volume-2/connection-pooling-routing/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch22
book_number: 22
book_part: part-4
book_status: draft
---

应用需要的不是“连接 `10.10.10.11`”，而是：

```text
把这笔短事务交给当前可写主库
把这批可容忍陈旧的查询交给合格副本
让迁移工具跟随主库，但不要经过事务池
把重型分析限制在指定离线副本
```

机器地址只回答“TCP 包送到哪里”，服务端点还必须回答：

```text
role          选择主库、副本还是指定成员
consistency   允许多旧，是否要求 read-your-writes
path          经过代理、连接池还是直达 PostgreSQL
session       客户端会话是否稳定绑定一个 backend
capacity      最多建立多少 client/server connection，在哪里排队
failure       旧连接如何结束，新连接何时恢复，提交结果如何判定
security      使用哪个身份、HBA/TLS/证书与审计边界
discovery     一个地址、VIP、DNS、多 host 还是驱动拓扑发现
```

只要其中一项没有写清，端口号就是一个未经定义的偶然实现。

本章把 PostgreSQL backend、PgBouncer、HAProxy、Patroni 和客户端驱动放进
同一条证据链。学习顺序不是先背 `5433/5434/5436/5438`，而是先定义服务
语义，再计算连接预算，选择池化模式，最后验证 Pigsty 的具体映射与切换行为。

## 本章目标

完成本章后，你应当能够：

1. 把连接 URI 当作版本化服务合同，而不是主机别名；
2. 区分主写、只读、同步读取、离线读取和直连管理端点；
3. 解释异步副本为什么不能天然提供 read-your-writes；
4. 用 LSN、sticky-primary 或业务一致性 token 设计读取策略；
5. 说明一个 PostgreSQL backend 的进程、内存、锁、事务和会话成本；
6. 拒绝用调大 `max_connections` 代替容量规划；
7. 把应用进程数、应用池、PgBouncer pool 与数据库保留槽放进同一预算；
8. 正确比较 session、transaction 与 statement pooling；
9. 判断临时表、会话 GUC、`LISTEN`、咨询锁和安全上下文是否兼容事务池；
10. 区分协议级 prepared statement 与 SQL `PREPARE`；
11. 从 `SHOW POOLS` 证明排队、复用与服务端连接上限；
12. 阅读 HAProxy 的 Patroni 角色健康检查、backup 选择和连接关闭策略；
13. 为切换中的断连、退避、抖动和提交结果未知编写客户端合同；
14. 识别角色已经正确、但池化后端仍保留旧角色状态的情况；
15. 在 Pigsty 中声明、渲染、校验和重载服务，而不是手改产物；
16. 完成一次带端点、池化、异步可见性和双向计划切换的可重放演练。

## 前置与后续

前置：

- [第 18 章 PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) 已定义服务、SLO 和
  责任边界；
- [第 19 章 部署基线](/deployment-baseline/) 已固定 exact Pigsty
  v4.4.0 四机沙箱；
- [第 20 章 高可用](/high-availability/) 已解释 Patroni、timeline、
  计划切换与提交结果未知；
- [第 21 章 备份体系与恢复演练](/backup-recovery/) 已证明 HA、backup 和 service
  recovery 不能互相替名；
- 读者已掌握 Linux、SQL、事务、锁和基本网络连接概念。

后续：

- 第 23 章把身份、HBA、TLS、RLS、审计与池化上下文纳入安全模型；
- 第 24 章把端点合同、切换 SOP 和例外变成组织治理；
- 第 25、26、27 章分别补齐指标、容量压测与参数治理；
- 第 31、34 章会复用本章的 queue、timeout、reserve 与 reconnect 控制点
  处理事故和过载。

## 学习路径

```text
业务动作
  -> 一致性和会话要求
      -> 语义服务端点
          -> PostgreSQL backend 成本
              -> 全局连接与并发预算
                  -> PgBouncer 模式及兼容性
                      -> HAProxy/Patroni 角色路由
                          -> 断连、重试与结果判定
                              -> Pigsty 声明和渲染
                                  -> 端到端演练与生产差距
```

这条路径故意把“端口”放在后面。`5433` 不是 PostgreSQL 标准语义；只有
当声明、渲染配置、健康检查、池状态和 SQL 观察相互吻合时，它才是当前
环境里的主写服务。

## 五层连接证明

| 层 | 要回答的问题 | 本章证据 |
|---|---|---|
| 声明 | 服务本来应当选择什么 | Pigsty inventory/defaults、ADR |
| 渲染 | 实际代理与池配置是什么 | HAProxy service file、`SHOW CONFIG` |
| 运行 | 当前哪些 backend 合格、池是否排队 | Patroni、HAProxy health、`SHOW POOLS` |
| SQL | 客户端最终落到什么角色与会话 | recovery/read-only、PID、GUC、token |
| 故障 | 角色变化时确认/未知结果如何收敛 | client event、timeline、token reconcile |

任意一层单独通过都不够：

```text
Patroni 有 leader
  != 应用主写端点可用

HAProxy backend UP
  != PgBouncer 身份、会话语义正确

SHOW POOLS 有空位
  != 业务延迟和数据库并发安全

连接失败后重试成功
  != 上一次写入一定没有提交
```

## Pigsty 默认服务语义

本章 exact v4.4.0 沙箱保留四个服务：

| 名称 | 入口 | 目标 | Patroni 检查 | 本章用途 |
|---|---:|---|---|---|
| primary | 5433 | 当前主库 PgBouncer :6432 | `/primary` | 短 OLTP 读写 |
| replica | 5434 | 副本优先 PgBouncer :6432 | `/read-only` | 可容忍陈旧的只读 |
| default | 5436 | 当前主库 PostgreSQL :5432 | `/primary` | 管理、迁移、会话敏感工具 |
| offline | 5438 | 指定离线副本 PostgreSQL :5432 | `/replica` | 受控 OLAP/ETL |

`replica` 的 primary 是 backup，`offline` 的普通 replica 也是 backup。
因此名称表达“选择偏好与降级策略”，不是永恒承诺。客户端仍要用
`target_session_attrs`、只读事务和业务策略防止错误落点。

这些都是可修改的 Pigsty 默认值，不是 PostgreSQL 标准端口。实际系统必须
读取自己的声明与渲染产物。

## 正式实验

```text
target          pg36-l2-vagrant/pg-test
entry           10.10.10.11 HAProxy
Pigsty          v4.4.0
PostgreSQL      18.4
PgBouncer       1.25.2, transaction mode
HAProxy         3.4.2
fixture         database/user test/test, schema pg36_ch22
initial         pg-test-1 primary, timeline 9
forward         pg-test-2 primary, timeline 10
restored        pg-test-1 primary, timeline 11
```

池化实验临时把入口节点的默认 server pool 从：

```text
default_pool_size=50
reserve_pool_size=30
query_wait_timeout=120
```

改为：

```text
default_pool_size=2
reserve_pool_size=0
query_wait_timeout=5
```

所有值在角色切换前精确恢复。正式观测：

```text
endpoint semantics                      4 / 4 matched
concurrent clients                      12
maximum active PostgreSQL backends       2
maximum waiting clients                 10
fastest / slowest query              254 / 1519 ms

session SET stayed with backend          yes
same state leaked to another client      yes
original client got another backend      yes

protocol prepared iterations            12 / 12 correct
backend reassignment                     observed
SQL PREPARE after reassignment           SQLSTATE 26000

replica token visibility                 11.092 ms
interpretation                           one observation only

forward command                          2.774 s
restore command                          2.766 s
acknowledged writes                      339
unknown outcomes                         48, all absent after lookup
acknowledged missing                       0
duplicate token                            0
unreconciled unknown                       0
maximum conservative write gap          8.510 s
counterexamples rejected                  15
```

最重要的观测不是某个毫秒数字，而是一个跨层失配：

> `pg-test-2` 的 PostgreSQL 已经是只读副本，Patroni 和 HAProxy 健康检查
> 也正确，但 PgBouncer 的既有 pool 仍可能保留上一次角色周期的状态。
> `RECONNECT test` 让服务端连接重新发现当前角色，端点验证才重新通过。

正式切换因此把三节点 `RECONNECT test` 计入恢复路径，并要求刷新后出现新的
确认写入。它不是隐藏的实验准备，更不是生产 SLO。

## 结论边界

```text
four service paths on one entry          通过
two-slot queue and backpressure          通过
transaction-pool session hazard          通过
protocol prepared exact version pair     通过
SQL PREPARE cross-backend failure        通过
one async visibility observation         通过
two healthy planned switchovers          通过
token reconciliation                     通过
original pool settings/final leader       恢复

redundant HAProxy/VIP/DNS entry           未证明
client/server TLS                         未验收
representative production load           未测试
driver/ORM version matrix                 未测试
unplanned failover/fencing                未测试
bounded replica staleness                 未承诺
production approval                       pending
```

## 十四项例外

沿用第 19 章六项与第 20 章四项，本章新增：

```text
EX22-SINGLE-HAPROXY-ENTRY
  只从 10.10.10.11 进入；不能声称入口冗余。

EX22-ASYNC-READ-OBSERVATION
  只采样一个 token；不能声称 read-your-writes 或 bounded staleness。

EX22-SYNTHETIC-LOAD
  负载小且运行在 laptop sandbox；不能推出生产容量。

EX22-RUNTIME-POOL-OVERRIDE
  只临时改变一个 PgBouncer 进程并恢复；不是声明式生产策略验收。
```

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第四篇：规划——建设可交付的 PostgreSQL 服务
- 兼容入口：`/ch22/`、`/volume-2/connection-pooling-routing/`

## 本章目录

### [22.1 服务端点的语义](01/)

- [22.1.1 主写、只读、同步只读与直连管理端点](01/#item-22-1-1)
- [22.1.2 复制延迟、一致性与 read-your-writes](01/#item-22-1-2)
- [22.1.3 DNS、VIP、代理与客户端发现](01/#item-22-1-3)

### [22.2 连接的服务端成本](02/)

- [22.2.1 后端进程、内存、事务与会话状态](02/#item-22-2-1)
- [22.2.2 `max_connections` 不是容量规划答案](02/#item-22-2-2)
- [22.2.3 应用池、代理池与数据库预算](02/#item-22-2-3)

### [22.3 PgBouncer 池化模式](03/)

- [22.3.1 session、transaction、statement pooling](03/#item-22-3-1)
- [22.3.2 临时表、会话 GUC、监听与咨询锁](03/#item-22-3-2)
- [22.3.3 预备语句支持必须绑定 PgBouncer 与驱动版本](03/#item-22-3-3)
- [22.3.4 池等待、服务时间与背压](03/#item-22-3-4)

### [22.4 路由与故障切换](04/)

- [22.4.1 HAProxy 健康检查与角色判断](04/#item-22-4-1)
- [22.4.2 旧连接、重连风暴与客户端退避](04/#item-22-4-2)
- [22.4.3 故障切换中的 DNS、连接池和事务失败](04/#item-22-4-3)

### [22.5 连接预算与过载边界](05/)

- [22.5.1 按服务分配连接、并发与队列](05/#item-22-5-1)
- [22.5.2 超时层级、取消传播与熔断](05/#item-22-5-2)
- [22.5.3 为 ch34 的止血动作预留控制点](05/#item-22-5-3)

### [22.6 Pigsty 服务接入层](06/)

- [22.6.1 服务定义、角色选择与端口](06/#item-22-6-1)
- [22.6.2 PgBouncer、HAProxy 与数据库的证据链](06/#item-22-6-2)
- [22.6.3 配置变更、reload 与连接行为验证](06/#item-22-6-3)

### [22.7 实战：写入、只读与管理三类接入](07/)

- [22.7.1 为 `pg36_shop` 配置端点和连接预算](07/#item-22-7-1)
- [22.7.2 验证会话状态、预备语句与只读一致性](07/#item-22-7-2)
- [22.7.3 注入切换与连接风暴，观察退避和恢复](07/#item-22-7-3)

## 实验入口

- [`lab-contract.md`](/labs/ch22/lab-contract.md)：风险、动作、停机线与解释边界；
- [`requirements.json`](/labs/ch22/requirements.json)：机器验收合同；
- [`endpoint-contract.json`](/labs/ch22/endpoint-contract.json)：四类端点语义；
- [`routing-adr.md`](/labs/ch22/routing-adr.md)：路径、池化与切换决策；
- [`topology.mmd`](/labs/ch22/topology.mmd)：实验拓扑；
- [`task.sh`](/labs/ch22/task.sh)：唯一安全入口；
- [`connection-run.json`](/labs/ch22/connection-run.json)：正式参考结果；
- [`negative-cases.json`](/labs/ch22/negative-cases.json)：十五个反例。

`task.sh all` 只重验既有证据，不连接 fixture、不改配置、不切换角色，也不
删除对象。`drill:service` 和 `reset:fixture` 是两条独立、精确守卫的路径。

## 参考资料

- [PostgreSQL 18：连接与认证参数](https://www.postgresql.org/docs/18/runtime-config-connection.html)
- [PostgreSQL 18：libpq 连接参数与 target_session_attrs](https://www.postgresql.org/docs/18/libpq-connect.html)
- [PgBouncer：Configuration](https://www.pgbouncer.org/config.html)
- [PgBouncer：Feature map](https://www.pgbouncer.org/features.html)
- [PgBouncer：Administration console](https://www.pgbouncer.org/usage.html)
- [Pigsty：PostgreSQL Service](https://pigsty.io/docs/pgsql/service/)
- [HAProxy：Health checks](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/reliability/health-checks/)

---

[上一章：未雨绸缪：备份体系与恢复演练](/backup-recovery/) · [返回下卷导读](/lower-volume/) · [下一章：固若金汤：认证、授权与数据安全](/authentication-authorization-security/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
