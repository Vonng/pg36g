---
title: 第 16 章 经天纬地：时序、空间与时空查询
linkTitle: 16 经天纬地：时序、空间与时空查询
weight: 260
aliases:
- "/ch16/"
- "/volume-1/spatiotemporal/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch16
book_number: 16
book_part: part-3
book_status: draft
---

“时间”与“空间”都很容易被压缩成错误的表结构：

```sql
created_at timestamp,
longitude  numeric,
latitude   numeric
```

这四个字段看起来够用，却没有回答最关键的问题：

```text
created_at 是事情发生、服务器接收，还是规则生效的时间？
timestamp 表示绝对时刻，还是某地墙上时间？
经纬度遵守哪个坐标参考系，顺序与单位是什么？
边界上的点算区域内还是区域外？
距离是角度、米，还是某个投影坐标系的单位？
历史查询应使用今天的围栏，还是当时生效的围栏版本？
```

一旦业务需要处理夏令时、迟到、乱序、重复写入、围栏换版或距离筛选，这些
未回答的问题就会从“数据建模细节”变成错误结果。

本章建立一条统一原则：

> 先固定时间与空间语义，再选择分区、扩展和索引；先证明逻辑答案，再证明
> 物理路径；最后才讨论容量和性能。

## 本章完成后

你应当能够：

- 区分事件时间、接收时间、处理时间和业务有效时间；
- 选择 `timestamptz` 与 `timestamp`，解释 PostgreSQL 的存储、输入和显示
  时区职责；
- 用一次夏令时跳变说明“墙上时间差”为什么不等于实际经过时间；
- 识别迟到、乱序和重复是三个不同问题，并分别设计水位线、重算与幂等合同；
- 用 `tstzrange` 和半开区间 `[)` 表达无歧义的有效期；
- 选择事件时间作为分区键，写出可裁剪的半开范围谓词；
- 从计划中区分“只访问一个分区”与“扫描所有分区后再过滤”；
- 解释原生分区、聚合与 TimescaleDB 解决的问题边界；
- 区分 PostGIS `geometry` 与 `geography` 的计算模型和单位；
- 说明 SRID 是坐标参考身份，`ST_SetSRID` 不会转换坐标；
- 在 `ST_Covers`、`ST_Contains`、`ST_Intersects`、`ST_DWithin`、
  `ST_Distance` 与 `<->` 之间按业务语义选择；
- 解释包围盒候选与精确几何判断的二阶段关系；
- 用 GiST/SP-GiST 计划证明路径存在，同时不把小表强制计划冒充性能基准；
- 把事件时间裁剪、围栏有效期与空间谓词组合成可审计的时空查询；
- 在 Pigsty 中区分扩展装包、preload、`CREATE EXTENSION`、版本核对与
  L1 节点一致性；
- 把 PostGIS 纳入备份恢复、大版本升级、WAL、索引和副本成本；
- 交付一个有冻结输入、反例、计划、权限、校验和、ADR 与精确复位路径的
  配送事件 PoC。

## 贯穿本章的配送事件

实验固定三种时间：

| 列 | 语义 | 用途 |
|---|---|---|
| `occurred_at` | 配送事件实际发生时刻 | 业务排序、分区、历史归属 |
| `received_at` | 该写入尝试被接收的时刻 | 迟到、乱序、重放审计 |
| `valid_during` | 围栏版本生效区间 | 历史时点连接 |

固定两种空间表示：

| 表示 | 本章职责 |
|---|---|
| `geometry(..., 4326)` | 拓扑谓词、边界判断、空间索引 |
| `geography(..., 4326)` | 以米为单位的距离判断 |

冻结 fixture 包含：

```text
13 ingest attempts
12 distinct delivery events
 4 geofence versions across 3 zones
 3 delivery hubs
 3 daily UTC partitions
```

13 次尝试中，`e003` 被发送两次；数据库保留尝试事实，再选出唯一规范事件。
三张日分区分别得到 `1 / 7 / 4` 行。`e008` 发生在
`2026-03-08 23:59:59Z`，`e009` 正好发生在次日 `00:00:00Z`，用来证明
半开分区边界。

## 一个十分钟却跨过两小时刻度的例子

纽约在 2026-03-08 进入夏令时。fixture 中：

| 事件 | UTC | `America/New_York` 显示 |
|---|---|---|
| `e002` | `06:55Z` | `01:55` |
| `e003` | `07:05Z` | `03:05` |

墙上时间从 01:55 跳到 03:05，看起来相隔 70 分钟；两个绝对时刻实际只相隔
600 秒。实验把两项都保存为证据：

```text
dst_e002_local=2026-03-08 01:55:00
dst_e003_local=2026-03-08 03:05:00
dst_elapsed_seconds=600
```

PostgreSQL 的日期时间类型与时区转换规则以官方
[Date/Time Types](https://www.postgresql.org/docs/18/datatype-datetime.html)
和
[Date/Time Functions](https://www.postgresql.org/docs/18/functions-datetime.html)
为准。应用程序不应自己维护一份简化时区规则。

## 围栏边界不是实现细节

`e003` 位于 `central v1` 的东边界，也位于 `east v1` 的西边界。固定结果是：

| 区域 | `ST_Covers` | `ST_Contains` | `ST_Touches` |
|---|---:|---:|---:|
| central v1 | true | false | true |
| east v1 | true | false | true |

本章选择 `ST_Covers`，所以边界算命中，`e003` 会同时属于两个区域。这是业务
合同，不是 PostGIS 替业务做出的唯一正确选择。若配送系统要求唯一归属，还要
增加优先级、分区化面集或确定性消歧。

另一个版本例子：

```text
central v1  [2026-03-07 00:00Z, 2026-03-08 12:00Z)
central v2  [2026-03-08 12:00Z, 2026-03-10 00:00Z)
```

`e004` 在扩张前位于旧围栏外；同一点的 `e005` 正好在 12:00 发生，按 `[)`
落入 v2 并位于新围栏内。同一 `zone_id` 的有效期由 `btree_gist` 排他约束
禁止重叠，重叠写入固定失败为 SQLSTATE `23P01`。

## 逻辑正确与物理路径分开

时间查询的正确写法是直接约束分区键：

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-03-08 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-03-09 00:00:00+00'
```

固定计划只出现：

```text
delivery_event_20260308
```

把列包进表达式：

```sql
WHERE (occurred_at AT TIME ZONE 'UTC')::date = DATE '2026-03-08'
```

逻辑答案仍是七行，但计划通过 `Append` 访问三张分区。PostgreSQL 官方分区
文档强调，裁剪依据是分区边界，而不是分区上的普通索引；写法必须让规划器或
执行器能够把谓词与分区键对应。参见
[Table Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)。

空间计划分别证明：

```text
ST_DWithin geography -> event_20260308_geog_gist_idx
ST_DWithin geometry  -> delivery_hub_location_spgist_idx
ST_Covers join       -> event_20260308_location_gist_idx
zone_id lookup       -> geofence_version_no_overlap
```

这些计划在 12 行 fixture 上关闭顺序扫描，仅证明路径可用。正常规划器选择
顺序扫描并不表示索引失效，更不能用强制计划声称生产更快。

## 实验资产

规范与决策：

- [实验合同](/labs/ch16/lab-contract.md)
- [时空 ADR](/labs/ch16/spatiotemporal-adr.md)
- [冻结夹具清单](/labs/ch16/fixture-manifest.json)
- [v1.4 proposal](/labs/ch16/baseline-v1.4-proposal.json)
- [Pigsty 4.4 声明片段](/labs/ch16/pigsty-declaration.example.yml)

冻结输入：

- [写入尝试](/labs/ch16/frozen-attempts.csv)
- [围栏版本](/labs/ch16/frozen-geofences.csv)
- [配送中心](/labs/ch16/frozen-hubs.csv)
- [确定性装载](/labs/ch16/fixture.sql)

实现与证据：

- [环境保护](/labs/ch16/context.sql)
- [建模、扩展、分区与索引](/labs/ch16/setup.sql)
- [时间事实](/labs/ch16/temporal-analysis.sql)
- [分区目录](/labs/ch16/partition-catalog.sql)
- [边界语义](/labs/ch16/boundary-semantics.sql)
- [距离语义](/labs/ch16/distance-semantics.sql)
- [索引目录](/labs/ch16/index-catalog.sql)
- [最终状态](/labs/ch16/final-state.sql)
- [完整验证](/labs/ch16/verify.sql)
- [自动审校器](/labs/ch16/review.py)
- [精确复位](/labs/ch16/reset.sql)

三份 CSV 不只是示例附件。自动化从数据库重新导出并逐字节比较；
`fixture-manifest.json` 还固定行数、SHA-256、时间合同、坐标合同和许可证
边界。

## 快速运行

本地开发数据库应先完成第 4 章的角色与物理模型：

```bash
export PGSERVICEFILE=/path/to/pg_service.conf
export PGSERVICE=pg36-admin

PG36_EVIDENCE_DIR="$PWD/evidence/ch16" \
  ./static/labs/ch16/task.sh all
```

`all` 会：

1. 验证数据库、可写状态、PostgreSQL 14–18、管理员、owner/app 角色和
   `ch04-v1` 模型；
2. 核对本机恰好可供应 PostGIS 3.6.4 与 `btree_gist` 1.8；
3. 只接管带精确 owner、marker、版本与扩展依赖的两个 schema；
4. 在单事务中安装扩展、创建三张日分区、四类数据表和 13 个管理索引；
5. 导入 13 次尝试，验证重复 payload 一致，再生成 12 个规范事件；
6. 从数据库回读三份冻结 CSV 并逐字节比较；
7. 采集 DST、迟到、乱序、分区路由、时间桶、围栏版本、边界和距离证据；
8. 采集扩展、索引、权限、对象体积和五份执行计划；
9. 证明混合 SRID、重叠有效期、应用写入分别以 `XX000`、`23P01`、
   `42501` 失败；
10. 运行 34 个关系对象、扩展依赖、数据事实、索引、权限与业务校验和的
    完整断言；
11. 证明错误 token、错误 target、活跃 worker 时 reset 分别以
    `P3660/P3661/P3663` 被拒绝；
12. 在单事务中不用 `CASCADE` 精确复位，确认第 14 章扩展保留，再完整
    重建第二次。

正式 Homebrew PostgreSQL 18.4 双周期证据得到：

```text
status=ok
fixture=frozen-byte-identical
time=event+ingest+validity+dst
space=geometry+geography+srid+boundary
plans=pruning+gist+spgist+joint
guards=P3660+P3661+P3663
extensions=btree_gist:1.8+postgis:3.6.4
pigsty_l1=not-run
release_candidate_checksum=13902984b3da92a66638d0d6e2f886d6d8ac5cb20ba89ec08b1527ae79d2b923
```

> **安全边界**
>
> `task.sh all` 会删除并重建带本章精确 marker 的 `shop_ch16`、
> `shop_ch16_ext` 和其中两项扩展，只适合本书本地/开发 fixture。生产环境
> 必须使用经过评审的扩展供应、在线分区与索引发布、备份恢复验证和回退流程。

## 学习路径

### [16.1 时间语义先于时序扩展](01/)

- [16.1.1 事件时间、处理时间与有效时间](01/#item-16-1-1)
- [16.1.2 时区、迟到、乱序与重复事件](01/#item-16-1-2)
- [16.1.3 范围类型、窗口与时间对齐](01/#item-16-1-3)

先学会给“时间”命名和验收。未固定语义时，引入任何时序扩展只会更快地得到
不确定答案。

### [16.2 时序表与时间分区](02/)

- [16.2.1 从 ch04 的分区 ADR 选择时间键](02/#item-16-2-1)
- [16.2.2 写入模式、冷热生命周期与保留](02/#item-16-2-2)
- [16.2.3 原生分区、聚合与可选时序扩展](02/#item-16-2-3)
- [16.2.4 不在本章重复在线分区化和维护细节](02/#item-16-2-4)

把事件时间落实到原生分区，理解裁剪、路由、生命周期和引入时序扩展的决策
门槛。

### [16.3 空间类型与坐标参考](03/)

- [16.3.1 geometry、geography 与测量语义](03/#item-16-3-1)
- [16.3.2 SRID、投影、单位与坐标转换](03/#item-16-3-2)
- [16.3.3 点、线、面、边界与有效几何](03/#item-16-3-3)

先固定坐标身份、表示与单位，再允许业务写空间谓词。

### [16.4 空间谓词与索引](04/)

- [16.4.1 包含、相交、邻近与最近邻](04/#item-16-4-1)
- [16.4.2 包围盒过滤与精确计算](04/#item-16-4-2)
- [16.4.3 GiST/SP-GiST 计划与选择率验证](04/#item-16-4-3)

从“问题是什么”推导谓词，再从谓词和数据分布推导索引，不反过来。

### [16.5 时空联合查询是本章收束目标](05/)

- [16.5.1 某时段、某区域内的配送事件](05/#item-16-5-1)
- [16.5.2 轨迹、停留、地理围栏与迟到修正](05/#item-16-5-2)
- [16.5.3 时间裁剪、空间索引与二阶段过滤](05/#item-16-5-3)

把事件时间、围栏有效时间和空间命中合成同一条可解释查询。

### [16.6 时空扩展的交付与观察](06/)

- [16.6.1 安装 PostGIS 与可选时序扩展](06/#item-16-6-1)
- [16.6.2 核对版本、依赖、备份和升级边界](06/#item-16-6-2)
- [16.6.3 观察分区、索引、写入与聚合成本](06/#item-16-6-3)

把本地 SQL 映射到 Pigsty 的装包、配置、建库、节点一致性和运行证据。

### [16.7 实战：配送事件的时空 PoC](07/)

- [16.7.1 生成确定性事件与地理数据](07/#item-16-7-1)
- [16.7.2 验证 SRID 错误、裁剪失效和空间索引](07/#item-16-7-2)
- [16.7.3 输出 ADR、PoC 证据与生产代价清单](07/#item-16-7-3)
- [16.7.4 超预算时先删扩展专属细节，不删基础判断力](07/#item-16-7-4)

最后完整执行两周期 PoC，并明确哪些结论已证明、哪些仍需生产规模测试。

## 权威参考

- PostgreSQL 18：
  [日期时间类型](https://www.postgresql.org/docs/18/datatype-datetime.html)、
  [日期时间函数](https://www.postgresql.org/docs/18/functions-datetime.html)、
  [范围类型](https://www.postgresql.org/docs/18/rangetypes.html)、
  [声明式分区](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- PostGIS：
  [数据管理与坐标参考](https://postgis.net/docs/using_postgis_dbmanagement.html)、
  [空间查询](https://postgis.net/docs/using_postgis_query.html)、
  [`ST_Covers`](https://postgis.net/docs/ST_Covers.html)、
  [`ST_DWithin`](https://postgis.net/docs/ST_DWithin.html)、
  [`ST_Transform`](https://postgis.net/docs/ST_Transform.html)
- Pigsty 4.4：
  [扩展概览](https://pigsty.io/docs/pgsql/ext/)、
  [包别名](https://pigsty.io/docs/pgsql/ext/pkg/)、
  [创建扩展](https://pigsty.io/docs/pgsql/ext/create/)、
  [PostGIS](https://pigsty.io/ext/e/postgis/)、
  [TimescaleDB](https://pigsty.io/ext/e/timescaledb/)

---

[上一章：见微知著：全文、模糊与向量检索](/search/) · [返回上卷导读](/upper-volume/) · [下一章：合纵连横：分析加速与分布式选型](/analytics-distributed/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
