---
title: 第 0 章（可跳过）扬帆起航——准备实验环境
linkTitle: 第 0 章 准备实验环境
weight: 3
aliases:
- "/ch0/"
- "/ch00/"
type: docs
breadcrumbs: true
comments: false
book_kind: chapter-zero
book_status: draft
---

> **可跳过说明**：本章只为尚未拥有实验环境的读者准备 Pigsty L1 沙箱，并完成首次
> PostgreSQL 连通。已有符合[版本契约](/appendices/a/)、且确认没有生产数据和流量的
> 独立环境，可以直接进入 [第 1 章](/postgresql-pigsty-map/)。

正文默认读者已经会 Linux、SSH 与 SQL；这里不补授操作系统、网络或 SQL 基础。本章
只建立后续实验共同需要的六项事实：

```text
exact Pigsty/PostgreSQL/OS version
non-production environment authority
node and service identity
safe network boundary
working PostgreSQL connection
redacted baseline evidence
```

本书冻结的写作基线是 Pigsty `v4.4.0`、PostgreSQL `18.4` 与 Ubuntu 24.04 LTS
reference environment。安装时固定 Pigsty release 与 PostgreSQL major，随后记录仓库
实际提供的 minor/build；不要为了伪造一致性降级已经修复安全问题的 minor release。

## 完成本章的标准

进入 ch01 前，读者应能：

1. 明确目标是可销毁、无生产数据与流量的 L1；
2. 记录 CPU、内存、磁盘、OS、架构、网络和成本边界；
3. 从官方来源获取并固定 Pigsty `v4.4.0`；
4. 在执行前审查生成的 `pigsty.yml`，保护其中的凭据与 CA key；
5. 完成单节点部署或验证一个等价的已有环境；
6. 分开 PostgreSQL、PgBouncer、HAProxy service 与 Web UI 入口；
7. 从 SQL 内部确认版本、数据库、角色、地址、端口与 recovery state；
8. 保存不含密码、token、private key 的环境摘要；
9. 知道安装失败时应保留日志、修复前置条件或重建 L1，而不是删除 PGDATA 猜测恢复。

## 本章目录

### [0.1 选择实验环境](01/)

- [0.1.1 本地虚拟机、开发服务器与已有 Pigsty 环境](01/#item-0-1-1)
- [0.1.2 L1 沙箱的最低资源、网络与磁盘要求](01/#item-0-1-2)
- [0.1.3 云主机的防火墙、入口与费用边界](01/#item-0-1-3)

### [0.2 安装单节点 Pigsty 沙箱](02/)

- [0.2.1 获取与核对版本](02/#item-0-2-1)
- [0.2.2 配置、部署与幂等重跑](02/#item-0-2-2)
- [0.2.3 检查 PostgreSQL、连接池与观察组件状态](02/#item-0-2-3)

### [0.3 完成首次连通](03/)

- [0.3.1 找到服务端点、数据库与实验凭据](03/#item-0-3-1)
- [0.3.2 执行 `SELECT version()` 与只读状态查询](03/#item-0-3-2)
- [0.3.3 确认编码、时区和扩展清单后进入 ch01](03/#item-0-3-3)

## 安全边界

- 单节点 L1 不提供生产高可用证明；
- 云端不把 PostgreSQL、PgBouncer、Patroni、DCS、监控或管理入口裸露到公网；
- `pigsty.yml` 与 `files/pki/ca/ca.key` 视为敏感材料；
- 本章不要求关闭 firewall/SELinux、使用默认密码或以 root 长期运行；
- 重装、清空数据和删除 cluster 都不是普通排错动作。

## 当前官方参考

- [Pigsty v4.4 documentation](https://pigsty.io/docs/)
- [Single-node setup](https://pigsty.io/docs/setup/)
- [Production install prerequisites](https://pigsty.io/docs/deploy/install/)
- [Supported Linux matrix](https://pigsty.io/docs/ref/linux/)
- [Setup security](https://pigsty.io/docs/setup/security/)

---

[返回全书导读](/guide/) · [下一章：PostgreSQL 与 Pigsty 全局地图](/postgresql-pigsty-map/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
