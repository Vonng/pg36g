---
title: 附录与速查
linkTitle: 附录
weight: 900
type: docs
breadcrumbs: true
comments: false
book_kind: appendices
---

附录用于快速定位版本、证据、症状、分区、实验安全和术语边界。它们不替代正文中的
机制与实验：遇到事故先按附录 C 找到首个安全动作，再进入目标章节完成证据分类。

## [附录 A：版本矩阵与差异注记](a/)

冻结 PostgreSQL 18.4、Pigsty v4.4.0、`pig` 1.5.1 与正式 L1/L2/L3 基线；说明哪些
结论必须按版本重验，以及勘误如何保留历史适用范围。

## [附录 B：对象、视图、命令与证据速查](b/)

按连接、对象、事务、锁、计划、复制、WAL、backup、vacuum 和容量定位首选证据；
每个动作同时标注风险、前置与 after 验收。

## [附录 C：症状与首个安全动作索引](c/)

从误操作、主库/DCS、复制、连接/锁、资源、XID、WAL 和完整性症状路由到 ch31～ch35；
明确第一步和绝不能做的捷径。

## [附录 D：分区能力索引](d/)

串联 ch04 决策、ch07 裁剪、ch11 在线迁移、ch16 时间语义与 ch28 生命周期。

## [附录 E：实验拓扑、风险与复位手册](e/)

定义 L1/L2/L3 规格，区分 R0–R3 风险，解释 `reset:sql`、`reset:cluster`、
`reset:host` 以及 snapshot/checksum/evidence 合同。

## [附录 F：术语与技术边界表](f/)

区分 PostgreSQL、Pigsty、Patroni、DCS、PgBouncer、HAProxy、实例、两种 cluster 与
service endpoint，并对照 RDS、自建和 Operator 的责任。

---

[返回全书导读](/guide/) · [查看全书目录](/toc/) · [查看索引中心](/indexes/)
