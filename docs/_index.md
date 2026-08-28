---
title: PG 三十六计
linkTitle: 首页
description: 从 SQL 到生产：PostgreSQL 与 Pigsty 实战
type: book
layout: landing
book_kind: book
book_status: reviewed
outputs: [HTML, print, markdown, LLMS]
search_exclude: true
sidebar_enabled: false
breadcrumbs: false
comments: false
cascade:
  type: book
---

《PG 三十六计》面向已经掌握 Linux 与通用 SQL、希望系统完成 PostgreSQL
应用开发和生产落地的读者。PostgreSQL 是核心知识对象；Pigsty 是统一实验载体、
观察窗口与生产参考实现。

全书分为应用开发与运维管理两卷，共六篇三十六章。正文从对象、模型、查询与并发
出发，经过发布、扩展、部署、HA、备份、可观测、容量与维护，最终进入事故响应、
恢复、取证和复盘改进。

## 阅读与查找

- [全书导读](/guide/)说明读者假设、安全公约、版本边界与实验合同。
- [完整编号目录](/toc/)定位全部章节、独立节页和稳定三级锚点。
- [索引中心](/indexes/)按角色、任务、技术边界、事故症状与分区触点查找内容。
- [第 0 章](/ch00/)准备可销毁的 Pigsty 实验环境；已有合适环境时可以跳过。

## 当前复现基线

正文与实验以 PostgreSQL 18.6、Pigsty v4.5.0 为当前基线。涉及其他受支持版本的
结论会就地说明适用范围。示例命令、示例输出和单次跑分都不能脱离目标、前提、
风险、证据、验收与复位链条单独使用。
