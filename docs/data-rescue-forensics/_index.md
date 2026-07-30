---
title: 第 35 章 数据抢救与工程取证——起死回生
linkTitle: 35 数据抢救与工程取证——起死回生
weight: 450
aliases:
- "/ch35/"
- "/volume-2/data-rescue-forensics/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch35
book_number: 35
book_part: part-6
book_status: draft
---

当数据库报告 checksum failure、invalid page、索引不一致或 collation version mismatch，
目标不再是“让错误消失”，而是回答四个必须分开的问题：

```text
detect
  哪个对象、块或不变量出现异常？检测覆盖什么、没有覆盖什么？

preserve
  哪份是原始证据，哪份是可信恢复来源，怎样证明它们没有被改写？

recover
  应重建派生对象、从健康来源恢复，还是只能分段抽取可读数据？

validate
  数据库能启动之外，业务不变量、恢复链与故障域是否重新可信？
```

“起死回生”不是在唯一副本上尝试越来越危险的参数。专业抢救的第一动作通常是停止
新增写入、保存原始现场、制作可重复的操作副本，并让每次尝试都从同一个证据点分叉。

## 学习完成标准

完成本章后，读者应能：

1. 区分物理页/存储异常、索引/排序规则派生异常与业务语义损坏；
2. 解释 detection、repair、extraction、rebuild 为什么是四种不同工作；
3. 为停写、只读、storage snapshot、PostgreSQL backup 与 clone 写出一致性边界；
4. 用 SHA-256、只读介质、操作日志和副本树维护工程级 chain of custody；
5. 记录 system identifier、timeline、版本、extension、locale/ICU、硬件与最近变更；
6. 解释 data checksum 保护的是 data page，不覆盖 temp file、所有内部结构或业务语义；
7. 正确使用 `SHOW data_checksums` 与离线 `pg_checksums --check`；
8. 用日志中的 relation/block 线索和 `pg_relation_filepath` 定位对象，但不手改文件；
9. 判断存储、内存、内核或文件系统仍不可信时，应先修基础设施；
10. 区分 `bt_index_check`、`bt_index_parent_check`、`heapallindexed` 与 `verify_heapam`；
11. 评估 `amcheck` 的锁、I/O、CPU、内存、隐私与 hot-standby 限制；
12. 识别 collation provider/version drift，并按“重建依赖对象后刷新版本”处置；
13. 解释“索引可重建”为什么不能证明 heap 与业务数据安全；
14. 按备份、健康副本、逻辑来源、分段抽取的优先级选择恢复源；
15. 把 `ignore_checksum_failure`、`zero_damaged_pages`、`ignore_invalid_pages`、
    `pg_resetwal` 限定为克隆现场的最后手段；
16. 写出停止自救、升级厂商/文件系统/硬件/数据库专业支持的触发线；
17. 区分“能启动、能查询、结构一致、业务可信、可恢复”五个验收层次；
18. 为不可恢复范围、估计方法、法律/合规通知和客户沟通保留证据；
19. 在盲测中区分 1-bit heap page 异常与 collation-derived mismatch；
20. 把 `reset:host` 当作需独立审批的 L3 重建风险类别，而不是普通维护命令。

## 三类损坏，三种恢复来源

| 类别 | 典型证据 | 主要恢复来源 | 不应默认做 |
|---|---|---|---|
| 物理 | checksum、invalid page、I/O error、块读取失败 | 可信 backup、健康副本、存储 snapshot、可读抽取 | 原地改页、删文件、忽略错误继续写 |
| 派生 | `amcheck`、collation version、错误索引结果 | heap/源表 + 正确规则重建 | 把 REINDEX 当作 heap 已安全 |
| 语义 | 约束外不变量、ledger/事件/业务对账 | PITR、审计日志、上游事实、补偿 | 用物理工具“修”业务写错 |

分类可以重叠。一次坏内存写可能同时损坏 heap 和 index；错误 ICU 版本可能让结构在
不同节点上被不同比较规则解释；应用误写也可能生成完全合法的 page/checksum。遇到
冲突证据应扩大范围，不要强选最便宜的修法。

## 信任阶梯

```text
process started
  < SQL endpoint responds
  < physical/structural checks pass
  < relational and business invariants pass
  < replica/archive/backup lineage passes
  < observation window remains clean
```

每一层只能证明自己的命题。`pg_ctl start` 成功不能证明索引返回正确结果；
`pg_checksums` 全绿不能证明 collation、约束外余额或外部副作用正确；
业务抽样正确也不能证明每个 relation block 都可读。

## 正式实验

本章对 managed `pg-test` 只做 before/after L0 read-only capture。真实 fault 全部在
`pg-test-3` 的一次性 PostgreSQL 18.4 中：

```text
/tmp/pg36-ch35-forensics-<run-id>
private Unix socket
data_checksums=on
12,000-row deterministic fixture
stopped known-good snapshot
separate case and working copies
```

runner 随机安排两个 blind case，正式顺序为：

```text
COLLATION_METADATA -> PHYSICAL_HEAP_PAGE
```

第一例只在 disposable catalog 中把 exact ICU collation stored version 从 `153.121`
改为 run-specific fake value：

```text
offline bad checksums        0
amcheck structural pass   true
version mismatch          true
route       REINDEX_AND_REFRESH_COLLATION
repair order  REINDEX -> REFRESH VERSION
repair elapsed            267.719 ms
business invariants match true
```

它模拟的是**版本元数据不一致**，不冒充真实 ICU 排序语义升级。

第二例在 stopped clone 上只翻转 heap block 2 中一个 byte：

```text
bytes changed                 1
offline bad checksums         1
online sequential scan    XX001
route       RESTORE_FROM_KNOWN_GOOD_COPY
in-place repair           false
recovered bad checksums       0
business invariants match true
```

两个 mutated original case 在各自恢复期间保持逐文件 digest 不变，known-good snapshot
也保持不变；最后停止所有临时 postmaster 并删除 exact root。managed PGDATA、服务、
路由、Patroni/DCS 和 `reset:host` 均未触碰。

验证器构造并拒绝 35 个真实 mutant，包括打开生产/managed 边界、弱化 checksum 阈值、
blind evidence 泄露答案、原地修复、REFRESH 先于 REINDEX、业务 digest 漂移和谎报
清理成功。公开证据见 [`rescue-run.json`](/labs/ch35/rescue-run.json)。

## 本章边界

正式实验没有：

- 注入真实磁盘、控制器、内存、内核或文件系统故障；
- 模拟真实 ICU/libc 比较语义改变；
- 在唯一副本或 managed PGDATA 上改一个字节；
- 使用 `ignore_checksum_failure`、`zero_damaged_pages` 或 `pg_resetwal`；
- 执行 Pigsty host 移除、重装或生产恢复。

因此它证明的是机制与证据链，不是生产数据可恢复比例或 host rebuild RTO。最终门禁
保持 `production_ch35_gate=pending`。

## 所属位置

- 卷别：[下卷：运维管理](/lower-volume/)（独立导读页，不构成章节父目录）
- 教学分组：第六篇：出山——按响应目标演练恢复与改进
- 前置：[第 21 章 备份体系与恢复演练](/backup-recovery/)、
  [第 34 章 过载保护与资源故障判型](/overload-resource-incidents/)
- 后续：[第 36 章 事故复盘、控制固化与平台演进](/postmortem-platform-improvement/)
- 兼容入口：`/ch35/`、`/volume-2/data-rescue-forensics/`

## 本章目录

### [35.1 现场保护与操作边界](01/)

- [35.1.1 停写、只读、快照、克隆与证据哈希](01/#item-35-1-1)
- [35.1.2 记录硬件、内核、日志、版本和最近变更](01/#item-35-1-2)
- [35.1.3 不在唯一副本上反复试错](01/#item-35-1-3)
- [35.1.4 绝不手工删除 `pg_wal` 或原始损坏文件](01/#item-35-1-4)

### [35.2 先分类再抢救](02/)

- [35.2.1 物理页、存储与 checksum 错误](02/#item-35-2-1)
- [35.2.2 索引、排序规则与派生结构错误](02/#item-35-2-2)
- [35.2.3 逻辑不变量、应用写错与语义损坏](02/#item-35-2-3)
- [35.2.4 三类问题的恢复来源不同](02/#item-35-2-4)

### [35.3 页与 checksum 证据](03/)

- [35.3.1 checksum 是否启用及其检测边界](03/#item-35-3-1)
- [35.3.2 日志、块号、关系文件与物理定位](03/#item-35-3-2)
- [35.3.3 存储故障先修基础设施，再谈数据库重建](03/#item-35-3-3)

### [35.4 索引、collation 与 `amcheck`](04/)

- [35.4.1 `bt_index_check`、`heapallindexed` 与锁成本](04/#item-35-4-1)
- [35.4.2 collation 版本变化与索引顺序异常](04/#item-35-4-2)
- [35.4.3 索引可重建不意味着堆表数据安全](04/#item-35-4-3)

### [35.5 抽取、跳过与重建策略](05/)

- [35.5.1 优先从备份、健康副本或逻辑来源恢复](05/#item-35-5-1)
- [35.5.2 对可读数据做分段抽取和校验](05/#item-35-5-2)
- [35.5.3 危险恢复参数只在克隆现场、明确损失下使用](05/#item-35-5-3)
- [35.5.4 何时停止自救并升级到专业支持](05/#item-35-5-4)

### [35.6 工程取证与业务验证](06/)

- [35.6.1 保留原始证据、操作副本和完整时间线](06/#item-35-6-1)
- [35.6.2 区分“数据库能启动”与“业务数据可信”](06/#item-35-6-2)
- [35.6.3 记录不可恢复范围与合规沟通](06/#item-35-6-3)

### [35.7 实战：在克隆环境分类并恢复](07/)

- [35.7.1 仅在启用 checksum 的专用镜像注入可控页异常](07/#item-35-7-1)
- [35.7.2 另设索引或 collation 异常，随机隐藏故障类型](07/#item-35-7-2)
- [35.7.3 用备份、重建或抽取恢复并验证不变量](07/#item-35-7-3)
- [35.7.4 用 `reset:host` 重建 Pigsty L3，不复用损坏现场](07/#item-35-7-4)

## 权威参考

PostgreSQL：

- [Data Checksums](https://www.postgresql.org/docs/18/checksums.html)
- [`pg_checksums`](https://www.postgresql.org/docs/18/app-pgchecksums.html)
- [`amcheck`](https://www.postgresql.org/docs/18/amcheck.html)
- [Collation Support](https://www.postgresql.org/docs/18/collation.html)
- [Developer Options and damaged-page warnings](https://www.postgresql.org/docs/18/runtime-config-developer.html)
- [System Information Functions](https://www.postgresql.org/docs/18/functions-info.html)

Pigsty：

- [`pig` command overview and context](https://pigsty.io/docs/pig/cmd/)
- [Backup and Restore](https://pigsty.io/docs/pgsql/backup/)
- [Run Playbooks with Ansible](https://pigsty.io/docs/setup/playbook/)
- [Parameters and Infrastructure as Code](https://pigsty.io/docs/concept/iac/parameter)

---

[上一章：过载保护与资源故障判型——李代桃僵](/overload-resource-incidents/) · [返回下卷导读](/lower-volume/) · [下一章：事故复盘、控制固化与平台演进——举一反三](/postmortem-platform-improvement/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
