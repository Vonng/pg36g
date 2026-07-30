---
title: 第 14 章 博采众长：内核分支与扩展生态
linkTitle: 14 博采众长：内核分支与扩展生态
weight: 240
aliases:
- "/ch14/"
- "/volume-1/extensions-ecosystem/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch14
book_number: 14
book_part: part-3
book_status: draft
---

PostgreSQL 的扩展生态很强，但“有这个扩展”不是架构理由，“能够安装”也
不是生产结论。一个扩展进入数据库后，可能同时改变：

- 节点上的软件包、控制文件、SQL 脚本与动态库；
- 数据库里的类型、函数、操作符、访问方法和系统目录依赖；
- 主库、备库、备份恢复、逻辑订阅与大版本升级的前置条件；
- 安装、升级和删除所需的特权；
- 应用数据的可移植性、故障半径与退出成本。

因此本章不做“常用扩展清单”，而是建立一套可复用的治理方法：

> 先证明问题，再检查原生替代；先冻结版本与运行条件，再创建数据库对象；
> 先演练升级、恢复和退出，再允许业务依赖。

第 15–17 章会分别深入检索、时空与分析/分布式能力。本章负责给它们提供
同一把尺子，避免每遇到一个新扩展就重新发明评审标准。

## 本章完成后

你应当能够：

- 区分 PostgreSQL server、发行版/内核、OS 软件包、扩展支持文件与数据库
  扩展对象；
- 从 `.control`、版本 SQL、动态库与 `pg_extension` 解释一个扩展如何
  被发现、安装和拥有；
- 解释 `superuser`、`trusted`、`relocatable`、`requires` 与
  `shared_preload_libraries` 各控制什么；
- 用 `pg_available_extensions`、`pg_available_extension_versions`、
  `pg_extension_update_paths()` 与 `pg_depend` 取得原生证据；
- 不把“兼容 PostgreSQL”误解为扩展、目录、运维和故障语义都兼容；
- 用六个问题筛选扩展，而不是按热度、功能数量或安装便利度决策；
- 区分软件包版本与数据库对象版本，并设计受控的
  `ALTER EXTENSION UPDATE`；
- 把备份恢复、物理备库、逻辑复制与 `pg_upgrade` 纳入扩展生命周期；
- 在 Pigsty 中区分仓库下载、节点安装、预加载配置和数据库启用；
- 解释包别名 `pgvector` 与 SQL 扩展名 `vector` 为什么不能混用；
- 识别节点漂移、control file 缺失、动态库缺失、未预加载与对象版本漂移；
- 写出包含问题、成功标准、供应链、权限、升级、恢复和退出的扩展 ADR；
- 对同一批候选给出“接受、限域试点、当前拒绝”三种有证据的结论。

## 三层状态，四个动作

扩展治理首先要拆开三层状态：

```text
供应层
  repository/package/image
    └─ control + version SQL + shared library

进程层
  shared_preload_libraries / server restart / loadability
    └─ backend can load the module

数据库层
  pg_extension + member objects + extversion
    └─ this database can use the SQL interface
```

Pigsty 把典型流程组织成四个动作：

```text
Download -> Install -> Configure -> Enable
仓库下载     节点装包    预加载/参数    CREATE EXTENSION
```

四步并非每个扩展都全部需要：

- `pg_trgm` 有数据库对象，但不需要 shared preload；
- `vector` 有数据库对象和动态库，本章版本也不需要 shared preload；
- `wal2json` 是逻辑解码插件，装包后按插件名使用，并不要求
  `CREATE EXTENSION`；
- Citus、TimescaleDB 等扩展有额外预加载、拓扑或生命周期要求，必须查目标
  版本文档，不能类推。

反过来，完成最后一步也不能证明前面三层在所有节点一致。主库已经
`CREATE EXTENSION`，某台备库仍可能缺动态库；数据库目录显示 0.8.4，
OS 仓库却已经换成另一构建。每层都需要独立证据。

## 贯穿实验：三个候选，三种结论

本章围绕 `shop_ch14` 评审三个候选：

| 问题 | 候选 | 结论 | 核心理由 |
|---|---|---|---|
| 单字段拼写容错 | `pg_trgm` | **accept** | 问题有界、contrib、受信任、GIN 可证、退出不锁定列类型 |
| 语义近邻检索 | `vector` | **pilot** | 能力成立，但模型、质量、资源、恢复与退出仍需真实语料证明 |
| 分布式分片 | `citus` | **reject now** | 尚无单节点上限证据、分片键合同和跨分片事务设计 |

“拒绝”不表示 Citus 有缺陷。Pigsty 当前扩展目录提供 Citus，说明平台有
交付能力；本章仍拒绝它，是因为供应能力不能替代问题适配。

实验故意让权限差异可见：

```text
pg36_owner (non-superuser, database owner)
  ├─ CREATE EXTENSION pg_trgm VERSION '1.3'  -> success
  │    trusted=true, extension owner=pg36_owner
  └─ CREATE EXTENSION vector VERSION '0.8.4' -> SQLSTATE 42501
       trusted=false, admin approval required

postgres/admin
  └─ CREATE EXTENSION vector -> success
       extension owner remains a superuser

pg36_app
  ├─ SELECT reviewed tables and use operators -> success
  └─ ALTER EXTENSION pg_trgm UPDATE            -> SQLSTATE 42501
```

随后由 `pg36_owner` 把 `pg_trgm` 从 1.3 更新到 1.6。更新前后：

```text
trigram top ids = 1,5,2
vector top ids  = 1,2,5
trigram plan    = GIN bitmap index scan
vector plan     = HNSW index scan
```

这只证明固定五行夹具的机制与回归合同，不证明生产相关性、召回率或尾延迟。

## 实验资产

完整合同与入口：

- [实验合同](/labs/ch14/lab-contract.md)
- [三项 ADR 摘要](/labs/ch14/candidate-review.md)
- [可复用 ADR 模板](/labs/ch14/extension-adr-template.md)
- [基础安装](/labs/ch14/setup.sql)
- [管理员安装 vector](/labs/ch14/install-vector.sql)
- [候选可用性](/labs/ch14/available-candidates.sql)
- [数据库扩展目录](/labs/ch14/extension-inventory.sql)
- [扩展成员目录](/labs/ch14/member-catalog.sql)
- [版本与更新路径](/labs/ch14/update-paths.sql)
- [索引目录](/labs/ch14/index-catalog.sql)
- [升级脚本](/labs/ch14/upgrade.sql)
- [可移植文本导出](/labs/ch14/portable-export.sql)
- [最终状态](/labs/ch14/final-state.sql)
- [自动审校器](/labs/ch14/review.py)
- [精确复位](/labs/ch14/reset.sql)
- [Pigsty 4.4 声明片段](/labs/ch14/pigsty-declaration.example.yml)
- [v1.2 proposal](/labs/ch14/baseline-v1.2-proposal.json)

正式本地证据在 Homebrew PostgreSQL 18.4 上采集。正文把平台映射核对到
Pigsty 4.4，但没有在 Pigsty L1 主机上运行，因此输出明确记录：

```text
validation_path=direct-postgresql
pigsty_l1=not-run
```

这不是缺点掩饰，而是证据边界。读者在自己的 L1 上必须补采仓库、各节点
包版本、预加载和数据库对象状态。

## 快速运行

沿用前章受控的 libpq service：

```bash
export PGSERVICEFILE=/path/to/pg_service.conf
export PGSERVICE=pg36-admin

PG36_EVIDENCE_DIR="$PWD/evidence/ch14" \
  ./static/labs/ch14/task.sh all
```

`all` 会：

1. 验证数据库、角色、ch04-v1 模型和基础业务不变量；
2. 对目标 schema 与同名扩展执行 marker/owner/version 碰撞保护；
3. 以 owner 安装受信任的 `pg_trgm` 1.3；
4. 证明 owner 安装未受信任的 `vector` 返回 `42501`；
5. 由管理员安装 `vector` 0.8.4，建立 GIN 与 HNSW 夹具；
6. 采集可用版本、control 属性、成员、ACL、索引和更新路径；
7. 证明应用可查询但不能升级扩展；
8. 记录升级前查询与强制索引计划；
9. 把 `pg_trgm` 更新到 1.6，再次记录相同证据；
10. 对 control、安装/更新 SQL 与动态库生成 SHA-256；
11. 对比全库 schema dump 与 `--schema=shop_ch14` 选择性 dump；
12. 把向量转为文本导出，形成试点退出材料；
13. 验证错误 token、错误 target 和活跃 worker 下的 reset 拒绝；
14. 不使用 `CASCADE` 精确复位，再从零完整重建和复验。

成功摘要：

```text
status=ok
decision=pg_trgm:accept/vector:pilot/citus:reject
boundary=package+control+database-object
failure=42501-owner+42501-superuser
upgrade=pg_trgm:1.3->1.6-behavior-stable
index=gin+hnsw
dump=create-extension+selective-dependency-warning
exit=portable-text-export
pigsty_l1=not-run
release=1.2-proposal
release_candidate_checksum=6a4b74baec5f522eb098c868f1d4f1b441bf5b5f6708411588af0a8793f7f573
```

这个 proposal checksum 标识 ADR、版本、夹具和验收合同；运行时间、绝对
安装路径以及文件系统 inode 不进入业务 golden。

> **安全边界**
>
> `task.sh all` 会删除并重建专用 `shop_ch14`，并删除带本章精确 marker 的
> `pg_trgm` 与 `vector`。它只适合本书本地/开发夹具。生产安装和升级必须
> 使用分阶段迁移、备库检查、恢复演练、观察窗口和独立回退，不运行
> “先删后建”的教学入口。

## 学习路径

### [14.1 PostgreSQL 扩展机制](01/)

- [14.1.1 control、SQL 脚本、动态库与对象所有权](01/#item-14-1-1)
- [14.1.2 普通扩展、预加载库与超级用户需求](01/#item-14-1-2)
- [14.1.3 扩展依赖、版本与 `ALTER EXTENSION`](01/#item-14-1-3)

先把扩展还原为 PostgreSQL 原生对象和支持文件。不了解这层，就无法解释
为什么“包已安装”和“数据库可用”不是同一件事。

### [14.2 内核、发行版与托管服务](02/)

- [14.2.1 上游 PostgreSQL、补丁内核与兼容性承诺](02/#item-14-2-1)
- [14.2.2 包仓库、容器镜像与托管白名单](02/#item-14-2-2)
- [14.2.3 “兼容 PostgreSQL”需要逐层验证](02/#item-14-2-3)

再把扩展放回具体供应环境，建立 SQL、协议、目录、扩展与运维五层兼容矩阵。

### [14.3 扩展选型的六个问题](03/)

- [14.3.1 它解决的具体问题和原生替代是什么](03/#item-14-3-1)
- [14.3.2 数据格式是否锁定、能否导出和退出](03/#item-14-3-2)
- [14.3.3 维护活跃度、许可证与商业连续性](03/#item-14-3-3)
- [14.3.4 权限、崩溃面与供应链风险](03/#item-14-3-4)

这一节把“喜欢哪个扩展”转化为六个可反驳、可采证的问题。

### [14.4 生命周期与升级耦合](04/)

- [14.4.1 安装版本不等于数据库对象版本](04/#item-14-4-1)
- [14.4.2 大版本升级、备份恢复与逻辑复制兼容](04/#item-14-4-2)
- [14.4.3 依赖扩展不可用时的降级策略](04/#item-14-4-3)

安装只是生命周期起点。真正的承诺发生在升级、恢复、复制和退出时。

### [14.5 用 Pigsty 管理扩展可用性](05/)

- [14.5.1 包、仓库、模板与节点差异](05/#item-14-5-1)
- [14.5.2 声明安装与数据库内 `CREATE EXTENSION`](05/#item-14-5-2)
- [14.5.3 从监控和日志识别加载失败](05/#item-14-5-3)

把原生机制映射到 Pigsty 4.4，但始终回到节点文件、live 参数和系统目录
复核。

### [14.6 建立可复用扩展 ADR](06/)

- [14.6.1 问题、候选、假设与成功标准](06/#item-14-6-1)
- [14.6.2 最小 PoC、风险清单与退出路径](06/#item-14-6-2)
- [14.6.3 结论的版本范围和复审触发器](06/#item-14-6-3)

把讨论沉淀为能够被后续章节复用、被版本变化触发复审的决策记录。

### [14.7 实战：评审三个候选扩展](07/)

- [14.7.1 一个接受、一个试点、一个拒绝](07/#item-14-7-1)
- [14.7.2 在 L1 安装并验证原生对象与平台状态](07/#item-14-7-2)
- [14.7.3 产出供 ch15–ch17 复用的 ADR 模板](07/#item-14-7-3)

最后把包、权限、对象、查询、升级、dump、出口和复位压成一份可审计交付物。

## 版本与证据边界

本章原理以 PostgreSQL 14–18 为范围；可执行 baseline 固定
`pg_trgm` 1.3/1.6、`vector` 0.8.4，并在 PostgreSQL 18.4 上验证。目标环境
没有这些精确版本时，不应伪造通过，而应复制 ADR、更新版本范围和 golden，
重新评审。

Pigsty 内容按 4.4 文档在 2026-07-29 核验。扩展目录、包版本和支持矩阵会
持续变化，实际变更前必须查目标 Pigsty 版本与仓库。

权威入口：

- [PostgreSQL: Packaging Related Objects into an Extension](https://www.postgresql.org/docs/18/extend-extensions.html)
- [PostgreSQL: CREATE EXTENSION](https://www.postgresql.org/docs/18/sql-createextension.html)
- [PostgreSQL: ALTER EXTENSION](https://www.postgresql.org/docs/18/sql-alterextension.html)
- [PostgreSQL: `pg_available_extension_versions`](https://www.postgresql.org/docs/18/view-pg-available-extension-versions.html)
- [PostgreSQL: `pg_extension`](https://www.postgresql.org/docs/18/catalog-pg-extension.html)
- [PostgreSQL: pg_upgrade](https://www.postgresql.org/docs/18/pgupgrade.html)
- [Pigsty: Install Extensions](https://pigsty.io/docs/pgsql/ext/install/)
- [Pigsty: Create Extensions](https://pigsty.io/docs/pgsql/ext/create/)
- [Pigsty: Extension Package Aliases](https://pigsty.io/docs/pgsql/ext/pkg/)
- [Pigsty: Extension Catalog](https://pigsty.io/docs/ref/extension/)

本章明确区分三种陈述：

1. PostgreSQL/Pigsty 文档定义的机制；
2. 本章针对三个问题作出的架构选择；
3. 当前本地 evidence 实际证明的观察。

只有第三类能由 `/tmp/pg36-ch14-final` 或读者自己的 evidence 目录直接
复现。

---

[上一章：言出法随：函数、触发器与存储过程](/functions-triggers-procedures/) · [返回上卷导读](/upper-volume/) · [下一章：见微知著：全文、模糊与向量检索](/search/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
