---
title: 第 30 章 推陈出新：版本升级与回滚策略
linkTitle: 30 推陈出新：版本升级与回滚策略
weight: 400
aliases:
- "/ch30/"
- "/volume-2/version-upgrade/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch30
book_number: 30
book_part: part-5
book_status: draft
---

第 29 章已经把逻辑复制、全量校验、切流和回退组织成迁移状态机。版本升级是在这条主线
上再增加五个同时变化的维度：

```text
PostgreSQL server
  + data/catalog format
      + SQL behavior and defaults
          + extensions and native libraries
              + clients, pools, backups, exporters and automation
```

因此，升级不是“换个 RPM/DEB 再重启”，也不是 `pg_upgrade` 返回成功就结束。它是一项
有兼容性清单、隔离彩排、业务基线、发布门、写入分界和退出窗口的迁移项目。

## 学习完成标准

完成本章后，读者应能：

1. 区分 minor、安全修复和 major upgrade，并从 release notes 提取行为变化；
2. 在 `pg_upgrade`、逻辑复制和 dump/restore 之间按停机、空间、回退与重建目标选型；
3. 盘点扩展的包、动态库、SQL 对象、preload 和 update path；
4. 发现 collation version 漂移，并坚持先重建依赖对象、再刷新版本；
5. 用 catalog、checksum、`amcheck`、恢复证据、查询结果和业务不变量建立升级基线；
6. 在隔离环境复现完整升级，并把软件准备时间与业务不可写时间分开；
7. 在目标第一笔独占写入前证明回退，在其后切换为对账或前滚策略；
8. 输出含停止线、观察窗口、owner 与证据包的生产升级 runbook。

## 一张图看懂升级决策

```text
识别变化
  -> inventory 数据 / 配置 / 扩展 / 客户端 / collation
      -> 选择 pg_upgrade / logical / dump-restore
          -> 克隆与彩排
              -> compatibility gate
                  -> stop old writer
                      -> upgrade and rebuild
                          -> application-visible validation
                              -> rollback proof before target writes
                                  -> release and observe
```

任一门禁失败，都回到前一个可解释状态；不能用“先上线再看看”跨过 checksum、
collation、扩展或业务结果不一致。

## 本章目录

### [30.1 先识别变化类型](01/)

- [30.1.1 小版本、安全修复与大版本](01/#item-30-1-1)
- [30.1.2 SQL 行为、系统目录、参数和默认值](01/#item-30-1-2)
- [30.1.3 驱动、连接池、备份与观察组件兼容](01/#item-30-1-3)

### [30.2 三类大版本升级路径](02/)

- [30.2.1 `pg_upgrade` 与停机窗口](02/#item-30-2-1)
- [30.2.2 逻辑复制与渐进切换](02/#item-30-2-2)
- [30.2.3 dump/restore 与重建机会](02/#item-30-2-3)
- [30.2.4 没有一种路径天然“滚动无感”](02/#item-30-2-4)

### [30.3 扩展与依赖升级](03/)

- [30.3.1 二进制包、数据库对象和预加载顺序](03/#item-30-3-1)
- [30.3.2 扩展升级脚本与不可降级路径](03/#item-30-3-2)
- [30.3.3 从 ch14 ADR 获取退出与兼容信息](03/#item-30-3-3)

### [30.4 locale、collation 与索引风险](04/)

- [30.4.1 libc、ICU 与排序规则版本](04/#item-30-4-1)
- [30.4.2 排序变化对唯一性和索引顺序的影响](04/#item-30-4-2)
- [30.4.3 识别受影响对象并规划重建](04/#item-30-4-3)

### [30.5 升级前检查与业务验证](05/)

- [30.5.1 系统目录、无效对象与长事务](05/#item-30-5-1)
- [30.5.2 `amcheck`、checksum 状态与备份恢复证据](05/#item-30-5-2)
- [30.5.3 查询结果、计划、性能和业务不变量基线](05/#item-30-5-3)
- [30.5.4 `amcheck` 与 checksum 检测对象不同](05/#item-30-5-4)

### [30.6 用隔离环境完成升级彩排](06/)

- [30.6.1 克隆数据与版本化配置](06/#item-30-6-1)
- [30.6.2 执行升级、扩展更新和服务接入验证](06/#item-30-6-2)
- [30.6.3 比较 Pigsty 面板与原生证据的前后差异](06/#item-30-6-3)

### [30.7 实战：前滚、回退与发布决策](07/)

- [30.7.1 注入一个扩展或排序规则兼容问题](07/#item-30-7-1)
- [30.7.2 在业务写入恢复前验证回退路径](07/#item-30-7-2)
- [30.7.3 输出升级 runbook、决策门和观察窗口](07/#item-30-7-3)

## 写作与验收提示

本章提供一个真实、隔离的 PostgreSQL 17.10→18.4 参考实验。它在 Pigsty
`pg-meta` 主机的随机 `/tmp` 目录中创建两套 Unix-socket-only 临时集群，不接触
Pigsty 管理的数据目录与服务。正式证据证明：

```text
fixture rows before / after       10,000 / 10,000
ordered digest equal              true
stale ICU collation gate          blocked
REINDEX then REFRESH VERSION      passed
checksum-incompatible target      rejected
pg_upgrade method                 copy
amcheck and staged ANALYZE        passed
old PG17 restart before new write passed
forward canary                    order_id 10001
remote and fixture cleanup        verified
```

验证器拒绝了 30 个声明反例和 20 个现场证据变异。公开摘要位于
[`upgrade-run.json`](/labs/ch30/upgrade-run.json)，完整实验合同位于
[`lab-contract.md`](/labs/ch30/lab-contract.md)。

这次小型沙箱成功不预测生产停机时长，也不证明第三方扩展、驱动、备份体系或真实应用
已经兼容。`production_ch30_gate` 始终保持 `pending`；生产授权必须来自真实数据克隆、
业务彩排、备份恢复与变更审批。

## 参考资料

- [PostgreSQL 18：升级 PostgreSQL 集群](https://www.postgresql.org/docs/18/upgrading.html)
- [PostgreSQL 18：`pg_upgrade`](https://www.postgresql.org/docs/18/pgupgrade.html)
- [PostgreSQL 18：逻辑复制集群升级](https://www.postgresql.org/docs/18/logical-replication-upgrade.html)
- [PostgreSQL 18：`ALTER COLLATION`](https://www.postgresql.org/docs/18/sql-altercollation.html)
- [PostgreSQL 18：`pg_verifybackup`](https://www.postgresql.org/docs/18/app-pgverifybackup.html)
- [PostgreSQL 18：版本 18 发行说明](https://www.postgresql.org/docs/18/release-18.html)
- [Pigsty v4.4：PostgreSQL 大、小版本升级](https://pigsty.io/docs/pgsql/admin/upgrade/)
- [Pigsty v4.4：数据迁移](https://pigsty.io/docs/pgsql/migration/)

---

[上一章：移花接木：逻辑复制、迁移与异构同步](/logical-replication-migration/) · [返回下卷导读](/lower-volume/) · [下一章：事件分级、现场保护与应急决策——枕戈待旦](/incident-response/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
