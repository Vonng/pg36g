---
title: 第 11 章 守正出奇：模式变更与安全发布
linkTitle: 11 守正出奇：模式变更与安全发布
weight: 210
aliases:
- "/ch11/"
- "/volume-1/schema-change-release/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch11
book_number: 11
book_part: part-2
book_status: draft
---

PostgreSQL 能在事务中执行许多 DDL，但“能回滚”不等于“能在线发布”。一次模式变更能否安全进入生产，至少同时取决于：

```text
logical compatibility
  × lock mode and lock duration
  × scan/rewrite/WAL/resource cost
  × old/new application coexistence
  × resumable data migration
  × observable switch and rollback window
  × explicit contract gate
```

所以本章不把 `ALTER TABLE` 写成命令速查。我们把变更拆成一个有状态、有停止线、有证据的发布协议：

```text
legacy
  → expand       add backward-compatible shape
  → migrate      bounded, restartable backfill
  → validate     prove old and new rows satisfy invariants
  → switch       move traffic while retaining rollback shape
  → observe      prove old readers/writers have disappeared
  → contract     remove old semantics only after a separate gate
```

任何箭头失败，都先问“当前已提交状态是什么、服务是否仍兼容、下一步是重试、暂停、回退流量还是前滚修复”，而不是下意识运行一份机械 `down.sql`。

## 本章目标

完成本章后，读者应当能够：

- 从 lock、scan、rewrite、WAL 与 application compatibility 五个维度评审 DDL；
- 说明元数据 fast path 为什么仍会等待 `ACCESS EXCLUSIVE`；
- 用 `lock_timeout` 把无限排队变成可识别的 `55P03`；
- 区分 non-volatile constant default 与 volatile default 的物理行为；
- 识别类型变更、约束验证、列删除和表重写的不同恢复语义；
- 设计 expand–migrate–validate–switch–contract 状态机；
- 为旧写入、新双写和影子读取定义兼容矩阵；
- 用 keyset 批次、原子 checkpoint 与停止线实现可中断回填；
- 解释为什么双写需要单一一致性权威，不能依赖两个独立写调用；
- 使用 `NOT VALID` 先保护新写入，再用 `VALIDATE CONSTRAINT` 检查历史行；
- 在 PostgreSQL 14–17 与 18 之间正确处理 `NOT NULL` 目录差异；
- 把 `CREATE INDEX CONCURRENTLY` 放在事务块外，并复用第 9 章的失败回收纪律；
- 预建可证明的 `CHECK`，降低 `ATTACH PARTITION` 的验证扫描风险；
- 说明 `ATTACH` 对父表和子表的实际锁，以及 default partition 的额外边界；
- 正确使用 PostgreSQL 14+ 的 `DETACH PARTITION CONCURRENTLY`；
- 在 Pigsty 中隔离发布连接，观察锁、WAL、复制、磁盘、连接和延迟；
- 区分 PostgreSQL 原生证据、Pigsty 平台证据与应用发布证据；
- 拒绝在旧依赖或观察窗口证据缺失时执行 contract；
- 为 `SAFE-MIGR-006` 与 `DEFAULT-VERS-010` 产出 v0.6 candidate evidence。

## 实验边界

实验基线为 PostgreSQL 18.4、Pigsty v4.4.0、Ubuntu 24.04 L1；主体发布路径面向 PostgreSQL 14–18。所有可重建对象都位于 `shop_private`，以 `ch11_` 开头并带固定 marker，不修改 `shop.*` 业务表：

```text
ch11_order                 50,000-row legacy order fixture
ch11_migration_state       monotonic phase and backfill checkpoint
ch11_default_probe         constant/volatile default A/B
ch11_default_probe_result  physical and WAL evidence
ch11_event                 range-partitioned parent
ch11_event_2025q1          preloaded standalone attach candidate
```

订单发布的最终自动验收故意停在：

```text
phase=switched
shipping_code NOT NULL and validated
shipping_method retained
compatibility bridge retained
contract not executed
```

这是设计结果，不是“少做一步”。本地脚本能证明目录、数据和 SQLSTATE，不能证明生产中的旧容器、离线作业、BI 查询和临时脚本已经退出，也不能把几秒钟等待冒充约定的回退观察期。

下载资产：

- [实验合同](/labs/ch11/lab-contract.md)
- [上下文 guard](/labs/ch11/context.sql)
- [legacy fixture](/labs/ch11/setup.sql)
- [默认值 fast path / rewrite A/B](/labs/ch11/default-probe.sql)
- [默认值目录证据](/labs/ch11/default-catalog.sql)
- [锁预算失败语句](/labs/ch11/lock-attempt.sql)
- [锁图协调器](/labs/ch11/run_lock_case.py)
- [兼容扩展 DDL](/labs/ch11/expand.sql)
- [事务块外并发索引入口](/labs/ch11/online-index.sh)
- [旧/新应用兼容反例](/labs/ch11/compatibility.sql)
- [可续跑回填器](/labs/ch11/backfill.py)
- [约束目录快照](/labs/ch11/constraint-catalog.sql)
- [验证与非空收紧](/labs/ch11/validate.sql)
- [流量切换探针](/labs/ch11/switch.sql)
- [contract 拒绝门](/labs/ch11/contract-gate.sql)
- [分区候选准备](/labs/ch11/partition-prepare.sql)
- [分区锁与并发摘除实验](/labs/ch11/partition_lab.py)
- [最终状态验收](/labs/ch11/verify.sql)
- [双 token reset](/labs/ch11/reset.sql)
- [证据审查器](/labs/ch11/review.py)
- [v0.6 规则提案](/labs/ch11/baseline-v0.6-proposal.json)
- [任务入口](/labs/ch11/task.sh)

## 本章目录

### [11.1 识别 DDL 的四类风险](01/)

- [11.1.1 锁等级与持锁时间](01/#item-11-1-1)
- [11.1.2 表重写、全表扫描与 WAL 放大](01/#item-11-1-2)
- [11.1.3 新旧应用版本的兼容窗口](01/#item-11-1-3)
- [11.1.4 数据回填的节奏与失败恢复](01/#item-11-1-4)

### [11.2 Expand–Migrate–Contract](02/)

- [11.2.1 先扩展兼容结构](02/#item-11-2-1)
- [11.2.2 分批迁移、双读校验与切换](02/#item-11-2-2)
- [11.2.3 观察稳定后再收缩旧结构](02/#item-11-2-3)

### [11.3 索引与约束的在线化路径](03/)

- [11.3.1 `CREATE INDEX CONCURRENTLY` 的阶段与失败残留](03/#item-11-3-1)
- [11.3.2 `NOT VALID`、`VALIDATE CONSTRAINT` 与验证扫描](03/#item-11-3-2)
- [11.3.3 默认值、非空与类型变更的版本边界](03/#item-11-3-3)

### [11.4 在线分区化](04/)

- [11.4.1 从 ch04 的分区 ADR 选择迁移路径](04/#item-11-4-1)
- [11.4.2 预建约束、`ATTACH` 与扫描规避](04/#item-11-4-2)
- [11.4.3 `DETACH`、并发能力与锁等级必须按版本说明](04/#item-11-4-3)
- [11.4.4 产出一次可回退的分区化发布](04/#item-11-4-4)

### [11.5 数据回填与流量切换](05/)

- [11.5.1 批次、限速、水位与断点续跑](05/#item-11-5-1)
- [11.5.2 影子读、双写的风险与一致性验证](05/#item-11-5-2)
- [11.5.3 何时暂停、回退或前滚](05/#item-11-5-3)

### [11.6 发布窗口中的平台观察](06/)

- [11.6.1 从服务入口隔离实验流量](06/#item-11-6-1)
- [11.6.2 观察锁、复制延迟、WAL 与资源水位](06/#item-11-6-2)
- [11.6.3 配置变更与模式变更分别留证](06/#item-11-6-3)

### [11.7 实战：无中断演进订单模式](07/)

- [11.7.1 加字段、回填、建约束与新旧版本共存](07/#item-11-7-1)
- [11.7.2 注入锁等待和回填中断，验证中止与恢复](07/#item-11-7-2)
- [11.7.3 把发布证据与新规则追加到规约](07/#item-11-7-3)

## 实测摘要

一次 PostgreSQL 18.4 全量验收得到：

```text
risk:
  ACCESS SHARE holder + ADD COLUMN
    → waiter requests AccessExclusiveLock
    → SQLSTATE 55P03
    → shipping_code remains absent

default:
  50,000 rows + constant 7
    → same relfilenode / atthasmissing=true / WAL ≈ 12 KB
  50,000 rows + clock_timestamp()
    → new relfilenode / atthasmissing=false / WAL ≈ 11.5 MB

compatibility:
  old insert → standard/STD
  old update → express/EXP
  new dual write → pickup/PUP
  mismatch → 23514 / named constraint identity

backfill:
  initial legacy nulls=49,999
  two × 5,000 batches → exit 75 / remaining 39,999
  resume eight batches → migrated 49,999 / remaining 0
  checkpoint total=10 batches / last_order_id=50,000

constraints:
  pair CHECK NOT VALID → VALIDATE
  non-null CHECK NOT VALID → VALIDATE → SET NOT NULL
  SET NOT NULL relfilenode unchanged
  PG18 relation NOT NULL appears in pg_constraint and pg_attribute

partition:
  ATTACH parent=ShareUpdateExclusiveLock
  ATTACH child=AccessExclusiveLock
  validated bound CHECK present before attach
  DETACH CONCURRENTLY outside transaction / rows retained=20,000
  child relfilenode unchanged / final reattached

release:
  phase=switched / contract=P3612 refused
  old column and bridge retained / worker=0
  business checksum=f8a7bfae59c6d16cd323abecfefe1014
```

WAL 字节、filenode OID、PID、毫秒和具体 lock backend 都不是跨环境 golden。稳定结论是 fast/rewrite 的相对关系、锁边、SQLSTATE、单调状态、批次原子性、零遗漏、数据保留和最终兼容边界。

## 章节验收

1. 变更说明同时回答 lock、scan/rewrite、WAL/space/lag 与兼容性；
2. `lock_timeout` 小于发布允许排队时间，`statement_timeout` 留出执行预算；
3. 55P03 被当作“未取得发布条件”，不是盲目无限重试；
4. constant/volatile default 的物理差异有目录与 WAL 证据；
5. expand 对所有仍受支持的旧版本保持可读写；
6. 双写只有一个一致性 authority，并有命名约束反例；
7. backfill 使用有界 keyset batch，不用巨型 OFFSET；
8. 数据更新与 checkpoint 同事务提交；
9. 受控中止能从精确水位继续，不能跳过低 key 遗留行；
10. `NOT VALID` 不被误写成“暂不执行约束”；
11. `VALIDATE CONSTRAINT` 的扫描和 lock budget 单独规划；
12. PostgreSQL 18 的关系级 `NOT NULL` catalog 差异已隔离；
13. concurrent index 命令位于事务块外，失败残留有 exact cleanup；
14. `ATTACH` 候选列定义完全匹配父表且 bound CHECK 已验证；
15. default partition 和 subpartition 的额外扫描边界已评审；
16. `DETACH CONCURRENTLY` 只在 PostgreSQL 14+ 且事务块外使用；
17. Pigsty 发布连接、应用流量和只读分析入口职责分离；
18. 锁、WAL、replication lag、disk、connection 与 SLI 同窗观察；
19. application deployment 与 database migration 各有独立 identity；
20. contract 需要旧读写依赖清零与真实观察期证据；
21. reset 的错误 token、错误 target 和 active-worker 反例全部拒绝；
22. 最终业务 checksum 不变，v0.6 仍是 candidate 而非已发布 baseline。

下一章 [ch12《一气呵成：从数据库契约到后端服务》](/database-to-service/) 将从数据库状态机继续走向 driver、连接池、应用发布和端到端验收。

## 参考资料

- [PostgreSQL 18：ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html)
- [PostgreSQL 18：Modifying Tables](https://www.postgresql.org/docs/18/ddl-alter.html)
- [PostgreSQL 18：Table Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [PostgreSQL 18 Release Notes：NOT NULL constraints](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 14 Release Notes：DETACH PARTITION CONCURRENTLY](https://www.postgresql.org/docs/14/release-14.html)
- [Pigsty：PostgreSQL Service](https://pigsty.io/docs/pgsql/service/)
- [Pigsty：PostgreSQL Dashboards](https://pigsty.io/docs/pgsql/dashboard/)

---

[上一章：顾此失彼：并发控制与隔离异常](/concurrency-isolation/) · [返回上卷导读](/upper-volume/) · [下一章：一气呵成：从数据库契约到后端服务](/database-to-service/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
