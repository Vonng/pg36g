---
title: 第 4 章 量体裁衣：数据类型、约束与可靠数据表达
linkTitle: 04 量体裁衣：数据类型、约束与可靠数据表达
weight: 140
aliases:
- "/ch04/"
- "/volume-1/data-types-constraints/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch04
book_number: 4
book_part: part-1
book_status: draft
---

逻辑模型说明“系统要保存什么事实”，物理模式则必须回答“这些事实允许以什么二进制表示、何时判错、怎样迁移、付出多少读写成本”。把 `price numeric`、`status text` 和 `created_at timestamptz` 写进表，只是选了类型类别；若没有精度、值域、时区、状态转换和失败语义，它们仍不是可靠的数据合同。

本章把 [ch03 的逻辑模型 v0](/logical-data-model/) 原地迁移为 `ch04-v1`。范围内四项未决被关闭：人民币金额改用“分”的整数表示，事件瞬间统一为 `timestamptz(3)`，内部键接入 identity 序列，订单与支付状态改由查找表、迁移图和伴随字段共同约束。与此同时，本章明确留下两条边界：支付总额与订单总额等跨表不变量将在后续事务/数据库逻辑章节处理；当前没有体量和生命周期证据，因此不预先分区。

## 本章目标

完成本章后，读者应当能够：

- 根据业务精度、范围、运算与序列化合同选择整数、`numeric` 或其他数值类型；
- 区分文本的存储、比较、排序、大小写折叠与 Unicode 正规化语义；
- 区分瞬间、当地民事时间、业务日期与持续时间，正确使用 `timestamptz`；
- 为内部键、业务键、外部引用和公开标识选择不同生成策略；
- 在布尔、枚举、`CHECK`、查找表和状态机之间作有证据的选择；
- 明确 SQL `NULL`、JSON `null`、缺席与不适用的差别；
- 正确使用 default、identity、sequence 与 stored generated column；
- 用命名 PK/UK/FK/CHECK/EXCLUDE 表达不变量，并读懂对应 SQLSTATE；
- 只对支持的约束使用 `DEFERRABLE`，理解延迟检查与 `ON CONFLICT` 的冲突；
- 从行宽、TOAST、索引和写放大评估类型/约束的物理成本；
- 通过体量、生命周期或裁剪证据进入分区决策，而不是把分区当默认模板；
- 在 Pigsty L1 完成 v0→v1 事务迁移、反例审查、复位和 `verify:state` 取证。

## 开始之前

本章的升级路径要求已经运行 ch03 的 `setup + seed`，当前摘要应为：

```text
model_version=ch03-v0
relation_checksum=cd7daa66543a6b5e0a5d7fc269558a6c
```

沿用 ch02 的私有 `PGSERVICEFILE` 与 `pg36-admin` service。实验基线是 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04；本章实际使用的 DDL 保持 PostgreSQL 14–18 可用。PG18 新增但旧版本没有的能力会单独标注，不能倒推成全版本事实。

下载资产：

- [物理决策登记](/labs/ch04/physical-decisions.md)
- [新环境 schema-v1 入口](/labs/ch04/schema-v1.sql)
- [v0→v1 事务迁移](/labs/ch04/migrate-v0-to-v1.sql)
- [v1 确定性样例](/labs/ch04/seed-v1.sql)
- [v1 状态验证](/labs/ch04/verify-v1.sql)
- [类型与约束反例](/labs/ch04/negative-cases.sql)
- [排他/可延迟约束实验](/labs/ch04/constraint-lab.sql)
- [分区 ADR](/labs/ch04/partition-adr.md)
- [v1 Mermaid 模型源文件](/labs/ch04/model-v1.mmd)
- [安全复位](/labs/ch04/reset.sql)
- [综合任务入口](/labs/ch04/task.sh)

## 从 v0 到 v1

| 决策面 | ch03-v0 | ch04-v1 | 仍未解决 |
|---|---|---|---|
| 金额 | unconstrained `numeric` | `currency_code='CNY'` + `bigint` 分 | 多币种、退款、税费 |
| 时间 | 无显式精度的 `timestamptz` | 事件 `timestamptz(3)`；UTC 验证；状态时间一致性 | 地方日程/长期时区规则 |
| 内部标识 | 手工 `bigint` | `BY DEFAULT AS IDENTITY` + PK | 多写者公开 UUID |
| 状态值 | 任意 `text` | owner-only catalog + FK | 新状态发布流程 |
| 状态转换 | 任意覆盖 | transition table + guard trigger | 金额等跨表转换前置条件 |
| 派生事实 | view 中临时相乘 | stored `line_total_minor` | 跨行聚合 |
| 文本键 | 只做唯一 | ASCII 格式与规范写入 | 全球化身份匹配 |
| 分区 | 未决定 | ADR 接受“暂不分区” | ch26 量级复查 |

```mermaid
flowchart LR
  A["ch03-v0<br/>逻辑关系可运行"] --> B["迁移前证明<br/>可表示、无越界"]
  B --> C["事务 DDL<br/>类型 + 约束 + 序列"]
  C --> D["反例<br/>错误类型与约束名"]
  D --> E["verify:state<br/>ch04-v1"]
  E --> F["ADR<br/>暂不分区"]
```

v1 的“可靠”是有范围的：它保证本章登记的行内、值域、引用与状态边规则；它不声称一个本地约束能够证明外部支付真实发生，也没有把“订单至少一行、已付金额等于应付金额”伪装成普通 `CHECK`。

## 所属位置

- 卷别：[上卷：应用开发](/upper-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第一篇：筑基——建立 PostgreSQL 工程认知
- 兼容入口：`/ch04/`、`/volume-1/data-types-constraints/`

## 本章目录

### [4.1 金额、文本与时间](01/)

- [4.1.1 整数、`numeric` 与金额精度](01/#item-4-1-1)
- [4.1.2 `text`、排序规则与大小写语义](01/#item-4-1-2)
- [4.1.3 `date`、`timestamptz`、时区与业务时间](01/#item-4-1-3)

先定义单位、比较和时间语义，再选类型名；本章案例把 CNY 金额闭合到整数“分”，把事件瞬间闭合到毫秒精度。

### [4.2 标识、状态与半结构化数据](02/)

- [4.2.1 `bigint`、UUID 与标识生成](02/#item-4-2-1)
- [4.2.2 布尔、枚举、查找表与状态机](02/#item-4-2-2)
- [4.2.3 数组、范围、JSONB 与拆表边界](02/#item-4-2-3)

内部引用键、外部标识和状态码不是同一种数据；半结构化类型也不能代替需要独立约束与生命周期的关系事实。

### [4.3 NULL、默认值与生成值](03/)

- [4.3.1 “未知”“不存在”与空值语义](03/#item-4-3-1)
- [4.3.2 默认值、身份列与序列](03/#item-4-3-2)
- [4.3.3 生成列与数据库派生事实](03/#item-4-3-3)

默认值、identity 与生成列分别回答“缺省输入”“键生成”和“行内派生”，不能互换。

### [4.4 用约束表达不变量](04/)

- [4.4.1 主键、唯一、外键与检查约束](04/#item-4-4-1)
- [4.4.2 排他约束与 `btree_gist` 的适用条件](04/#item-4-4-2)
- [4.4.3 仅对支持类型使用 DEFERRABLE，并说明事务末校验代价](04/#item-4-4-3)

命名约束既是数据库防线，也是稳定的错误定位和目录审计接口；实验会实际验证 EXCLUDE 与延迟唯一检查。

### [4.5 类型与约束的物理代价](05/)

- [4.5.1 行宽、对齐、TOAST 与更新成本](05/#item-4-5-1)
- [4.5.2 隐式转换、操作符与索引可用性](05/#item-4-5-2)
- [4.5.3 约束、索引与写放大的关系](05/#item-4-5-3)

类型与约束会改变行宽、索引数量、TOAST 访问和每次写入的工作量；可靠性设计必须把这些成本显式记账。

### [4.6 分区决策门](06/)

- [4.6.1 先证明生命周期、体量或裁剪需求再决定分区](06/#item-4-6-1)
- [4.6.2 分区键与主键、唯一约束必须共同设计](06/#item-4-6-2)
- [4.6.3 外键、引用方式与未来在线改造代价](06/#item-4-6-3)
- [4.6.4 产出“现在分区 / 暂不分区”的可复查 ADR](06/#item-4-6-4)

分区是一项针对大表生命周期和访问路径的物理决策。当前模型选择不分区，并保留可触发复查的证据门槛。

### [4.7 实战：把逻辑模型落成可靠物理模式](07/)

- [4.7.1 闭合金额与时间表达](07/#item-4-7-1)
- [4.7.2 闭合状态与标识生成](07/#item-4-7-2)
- [4.7.3 用反例验证类型、约束与错误语义](07/#item-4-7-3)
- [4.7.4 在 Pigsty L1 输出可靠 DDL、分区决策与 `verify:state`](07/#item-4-7-4)

升级路径从真实 v0 数据出发，迁移前拒绝无法无损转成“分”的金额，迁移后逐项验证错误语义、应用角色路径、可重入和安全复位。

## 章节产物

`task.sh all` 在已经存在 ch03-v0 时执行：

```text
manifest → migrate → verify → negative → constraint-lab
```

新环境可用 `task.sh install` 通过同一条迁移链建立空 v1、加载确定性 v1 样例并执行全部审查。两条路径最终必须得到同一摘要：

```text
status=ok
model_version=ch04-v1
money_unit=CNY-fen
session_timezone=UTC
customer_count=2
product_count=3
order_count=2
item_count=3
payment_count=2
order_transition_count=4
partition_decision=not-now
relation_checksum=f8a7bfae59c6d16cd323abecfefe1014
```

迁移已在 PostgreSQL 18.4 实测以下路径：首次升级、重复升级跳过、复位后从 v0 重建、空库 fresh install、fresh install 重跑、应用角色生成 identity 与执行状态转换、两位以上金额迁移前拒绝且事务完整回滚。

## 章节验收

1. 能解释为什么本案例选择整数“分”，也能说出何时应改用 `numeric(p,s)`；
2. 能证明 `timestamptz` 保存瞬间但不保存原始 zone name，并复现 DST 双重 01:30；
3. 能区分 identity、sequence 与 PK 的责任，迁移后不会产生键碰撞；
4. 非法状态值、非法转换和缺少伴随时间分别由不同规则拒绝；
5. 能说明 array、range、JSONB 与拆表的边界，而不是统一套用“灵活”；
6. 能从 `pg_constraint` 识别约束类型、是否验证和是否可延迟；
7. 能复现排他冲突和事务内唯一值交换；
8. 能列出 v1 新增的隐式/显式索引及写放大；
9. 分区决定有数据、生命周期和查询证据门，而不是凭行数拍脑袋；
10. `all`、`install`、拒绝路径与 reset 都有独立证据，最终 checksum 一致；
11. 明确 v1 尚未关闭的跨表/外部事实，不把本章 DDL夸大为完整电商生产模型。

下一章 [ch05《运筹帷幄：查询、事务与锁的核心心智模型》](/query-transaction-locks/) 将在这套可靠类型合同上建立查询执行、并发可见性与锁等待的共同原理地图；ch10 与 ch13 再处理并发状态转换和跨表数据库逻辑。

## 参考资料

- [PostgreSQL 18：数值类型](https://www.postgresql.org/docs/18/datatype-numeric.html)
- [PostgreSQL 18：日期/时间类型](https://www.postgresql.org/docs/18/datatype-datetime.html)
- [PostgreSQL 18：identity column](https://www.postgresql.org/docs/18/ddl-identity-columns.html)
- [PostgreSQL 18：generated column](https://www.postgresql.org/docs/18/ddl-generated-columns.html)
- [PostgreSQL 18：约束](https://www.postgresql.org/docs/18/ddl-constraints.html)
- [PostgreSQL 18：表分区](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [Pigsty v4.4：默认 meta 模板](https://pigsty.io/docs/conf/meta/)

---

[上一章：正本清源：从业务规则到关系模型](/logical-data-model/) · [返回上卷导读](/upper-volume/) · [下一章：运筹帷幄：查询、事务与锁的核心心智模型](/query-transaction-locks/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
