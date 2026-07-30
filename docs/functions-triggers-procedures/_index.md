---
title: 第 13 章 言出法随：函数、触发器与存储过程
linkTitle: 13 言出法随：函数、触发器与存储过程
weight: 230
aliases:
- "/ch13/"
- "/volume-1/functions-triggers-procedures/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch13
book_number: 13
book_part: part-3
book_status: draft
---

数据库端逻辑最危险的误解，是把“PostgreSQL 能做”当成“应该放进
PostgreSQL”。函数、触发器和过程都能执行复杂逻辑，但三者不是更高级的
应用框架。它们首先是不同的数据库对象，各有调用方式、事务语义、规划
承诺、权限边界和可观测性。

本章只追问一个工程问题：

> 一条规则由谁负责，才能在所有写入口下保持正确，同时仍然能够测试、
> 发布、观测和回退？

答案不是“全部放应用”或“全部放数据库”。更可靠的分层是：

```text
单列与单行合法域
  └─ NOT NULL / CHECK / 类型

表间引用与可声明关系
  └─ UNIQUE / FOREIGN KEY / EXCLUDE

旧行到新行的数据库状态跃迁
  └─ BEFORE ROW trigger（确实无法声明时）

事务最终点的跨表断言
  └─ deferred constraint trigger（知道并发边界时）

应用可调用的窄数据库命令
  └─ SECURITY INVOKER / SECURITY DEFINER function

需要分批提交的数据库维护动作
  └─ top-level CALL + procedure

跨系统工作流、重试策略与调度
  └─ 应用、outbox、worker 与平台
```

越靠上越声明式、越容易由 PostgreSQL 自动维护；越靠下越需要显式协议。
触发器不是把跨系统工作流藏起来的捷径，过程也不是调度器。

## 本章完成后

你应当能够：

- 先用约束、普通 SQL 和事务表达规则，再判断是否真的需要例程；
- 区分 SQL function、PL/pgSQL function、trigger function 与 procedure；
- 设计标量、复合、集合返回和多态函数，并控制重载歧义；
- 把 `VOLATILE`、`STABLE`、`IMMUTABLE` 当成给优化器的承诺；
- 正确声明 `STRICT`、`PARALLEL SAFE/RESTRICTED/UNSAFE`、`COST` 与
  `ROWS`；
- 使用稳定 SQLSTATE、`DETAIL` 与 `HINT` 定义机器可消费的错误合同；
- 理解 `EXCEPTION` 块为什么形成子事务，以及它不能替代正常控制流；
- 区分行级、语句级、`BEFORE`、`AFTER` 与 `INSTEAD OF` 触发器；
- 用 transition table 对批量变更做一次集合处理；
- 解释 deferred constraint trigger 检查的是事务最终状态，而不是
  任意并发历史；
- 识别递归、触发顺序、每行放大与隐藏 I/O；
- 准确说明 function 与 procedure 的调用和事务控制边界；
- 让批处理可重入、可续跑、可限批，而不把过程误当作 scheduler；
- 安全编写 `SECURITY DEFINER`：NOLOGIN owner、固定 `search_path`、
  全限定对象名、撤销 `PUBLIC EXECUTE`、输入收窄与最小授权；
- 从 `pg_proc`、`pg_trigger`、ACL、SQLSTATE 和函数统计中取得证据；
- 在 Pigsty L1 中交付声明、SQL 变更、测试证据、观察窗口和回退入口。

## 贯穿实验：订单状态护栏

本章不使用只展示语法的零散对象，而是维护一个完整的
`shop_ch13` 实验：

| 规则 | 实现 | 为什么 |
|---|---|---|
| 金额为正、状态属于有限集合 | `CHECK` | 单行、可声明、目录可见 |
| `created → paid/canceled/expired` 等跃迁 | `BEFORE ROW` trigger | 必须比较 `OLD` 与 `NEW` |
| `paid` 时捕获金额等于订单金额 | deferred constraint trigger | 两张表在提交点同时成立 |
| 应用取消订单、捕获支付 | `SECURITY DEFINER` function | 应用没有底表 DML，只调用窄命令 |
| 多行更新写审计 | `AFTER STATEMENT` + transition tables | 三行更新只产生一条 statement audit |
| 过期五张陈旧订单 | `SECURITY INVOKER` procedure | 顶层 `CALL` 按 `2/2/1` 三批提交 |
| 邮件、HTTP、消息消费、定时启动 | 不放触发器或过程 | 属于外部系统和平台 |

夹具刻意让不同机制叠在同一事务里：

```text
pg36_app
  │ EXECUTE only
  ▼
capture_payment(...)
  ├─ lock order
  ├─ insert captured payment
  └─ update order: created -> paid
       ├─ BEFORE ROW validates edge + version
       ├─ AFTER STATEMENT writes row history + statement audit
       └─ deferred constraint triggers validate final payment total
            ▼
          COMMIT or SQLSTATE P3614
```

这条链路同时说明两个事实：

1. `SECURITY DEFINER` 不是绕开约束；提升后的命令仍然经过触发器和提交点
   验证；
2. 触发器只能参与当前 PostgreSQL 事务，不能证明外部副作用已经完成。

实验入口由 [ch13 实验合同](/labs/ch13/lab-contract.md) 统一说明：

- [实验合同](/labs/ch13/lab-contract.md)
- [对象与权限安装](/labs/ch13/setup.sql)
- [完整验收入口](/labs/ch13/task.sh)
- [例程目录证据](/labs/ch13/routine-catalog.sql)
- [触发器目录证据](/labs/ch13/trigger-catalog.sql)
- [ACL 证据](/labs/ch13/security-catalog.sql)
- [状态与校验和](/labs/ch13/final-state.sql)
- [自动审校器](/labs/ch13/review.py)
- [精确复位](/labs/ch13/reset.sql)
- [Pigsty 声明片段](/labs/ch13/pigsty-declaration.example.yml)
- [v1.1 proposal](/labs/ch13/baseline-v1.1-proposal.json)

正式实验在 PostgreSQL 18.4 直连路径运行，同时把适用范围限制为
PostgreSQL 14–18。它没有经过 PgBouncer，因此不能声称 pooler 路径已验证。

## 快速运行

沿用前章的受控管理 service：

```bash
export PGSERVICEFILE=/path/to/pg_service.conf
export PGSERVICE=pg36-admin

PG36_EVIDENCE_DIR="$PWD/evidence/ch13" \
  ./static/labs/ch13/task.sh all
```

`all` 会：

1. 验证 ch04-v1 模型与 ch05 业务 checksum；
2. 精确重建 `shop_ch13`；
3. 采集 `pg_proc`、`pg_trigger` 和 ACL；
4. 穷举七个状态的 49 个有序对，证明恰好六条合法边；
5. 以 `pg36_app` 调用成功命令；
6. 验证七个失败 case、六类 SQLSTATE；
7. 证明异常子事务、transition table 与函数计数；
8. 证明显式事务里的过程以 `2D000` 失败；
9. 顶层调用过程取得 `2/2/1`，重跑取得 0；
10. 拒绝错误 token、错误 target 和活跃 worker 下的 reset；
11. 精确复位，再完整重建和复验第二遍。

成功摘要为：

```text
status=ok
business=orders:13/payments:1/history:10/audit:6
boundary=check+before-row+deferred-constraint+security-definer
failure=42501/P3613/P3614/P3616/P3618/2D000
transaction=exception-subtransaction+commit-time-check+procedure-batches
observability=transition-table+function-stats+sqlstate
release=1.1-proposal
release_candidate_checksum=32377d82a7ce958aa50b0077ebe99c47d27672223c3c77fd9f91072d3745de9d
```

计时和生成的 identity 值不是 golden。验收比较状态分布、权限矩阵、
SQLSTATE、批次关系和 canonical proposal checksum。

## 失败合同

| SQLSTATE | 含义 | 谁产生 | 预期结果 |
|---|---|---|---|
| `42501` | 应用直接写底表 | PostgreSQL ACL | 没有任何业务变化 |
| `P3613` | 非法状态边 | `BEFORE` trigger | 行、历史和审计一起回滚 |
| `P3614` | 支付最终状态不一致 | deferred trigger | 到提交点拒绝整个事务 |
| `P3616` | 乐观版本不匹配 | command function | 调用方重新读取后决定是否重试 |
| `P3618` | 支付命令前置条件不成立 | command function | 不插支付、不改订单 |
| `2D000` | 显式事务块内试图结束事务 | procedure runtime | 该显式事务失败 |

自定义 `P36xx` 只属于本书实验合同；真实项目必须建立自己的错误注册表，
避免不同模块复用同一码位。调用方匹配 SQLSTATE，而不是匹配可能被翻译、
改写或补充上下文的 message。

## 学习路径

### [13.1 先决定逻辑放在哪里](01/)

- [13.1.1 数据不变量、批处理与接口封装](01/#item-13-1-1)
- [13.1.2 数据库内聚与应用可演进性的权衡](01/#item-13-1-2)
- [13.1.3 不用触发器隐藏跨系统工作流](01/#item-13-1-3)

先建立决策算法。如果跳过这一节，后面的语法很容易变成“看到锤子，到处
找钉子”。

### [13.2 SQL 与 PL/pgSQL 函数](02/)

- [13.2.1 参数、返回值、集合与多态](02/#item-13-2-1)
- [13.2.2 波动性、严格性、并行安全与规划影响](02/#item-13-2-2)
- [13.2.3 异常、子事务与错误契约](02/#item-13-2-3)

函数是查询表达式的一部分，因此必须同时理解类型系统、优化器承诺和
调用者事务。

### [13.3 触发器与约束触发器](03/)

- [13.3.1 行级、语句级与 transition table](03/#item-13-3-1)
- [13.3.2 BEFORE、AFTER 与 INSTEAD OF](03/#item-13-3-2)
- [13.3.3 递归、顺序、批量写入与隐藏成本](03/#item-13-3-3)

触发器要从“自动执行”还原为“写语句执行计划中隐藏的一段同步代码”。

### [13.4 过程、任务与事务控制](04/)

- [13.4.1 procedure 与 function 的边界](04/#item-13-4-1)
- [13.4.2 批处理、维护任务与显式事务](04/#item-13-4-2)
- [13.4.3 调度属于平台职责，不由过程本身解决](04/#item-13-4-3)

过程最独特的能力是受限的事务控制，不是“函数的加强版”。

### [13.5 安全、测试与观测](05/)

- [13.5.1 `SECURITY DEFINER`、固定 `search_path` 与最小权限](05/#item-13-5-1)
- [13.5.2 单元测试、属性测试与并发测试](05/#item-13-5-2)
- [13.5.3 函数级统计、日志与慢调用定位](05/#item-13-5-3)

例程一旦成为权限边界，就必须按 API 和安全敏感代码来发布，而不是当成
一段随手粘贴的 SQL。

### [13.6 实战：为订单状态建立数据库端护栏](06/)

- [13.6.1 比较约束、函数、触发器与应用实现](06/#item-13-6-1)
- [13.6.2 注入绕过应用的错误写入](06/#item-13-6-2)
- [13.6.3 在 Pigsty L1 输出实现选择、测试证据与回退脚本](06/#item-13-6-3)

最后把决策、对象、失败、证据、声明和回退压成一份可评审交付物。

## 版本与证据边界

本章使用 PostgreSQL 14–18 共有的核心能力；`anycompatible` 多态类型族从
14 开始，因此实验下限设为 14。PostgreSQL 18.4 是本次实际验证版本，
不是暗示 14–17 会自动通过所有环境差异。

权威语义以以下文档为准：

- [User-Defined Functions](https://www.postgresql.org/docs/18/xfunc.html)
- [CREATE FUNCTION](https://www.postgresql.org/docs/18/sql-createfunction.html)
- [Function Volatility Categories](https://www.postgresql.org/docs/18/xfunc-volatility.html)
- [Overview of Trigger Behavior](https://www.postgresql.org/docs/18/trigger-definition.html)
- [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html)
- [User-Defined Procedures](https://www.postgresql.org/docs/18/xproc.html)
- [PL/pgSQL Transaction Management](https://www.postgresql.org/docs/18/plpgsql-transactions.html)
- [Pigsty Monitoring System](https://pigsty.io/docs/concept/monitor/)

本章会明确区分“官方定义”“本章设计选择”和“本地实验观察”。只有第三类
结论能够由当前 evidence 目录证明。

---

[上一章：一气呵成：从数据库契约到后端服务](/database-to-service/) · [返回上卷导读](/upper-volume/) · [下一章：博采众长：内核分支与扩展生态](/extensions-ecosystem/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
