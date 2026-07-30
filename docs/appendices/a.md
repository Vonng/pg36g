---
title: 附录 A：版本矩阵与差异注记
linkTitle: 附录 A 版本矩阵与差异注记
weight: 10
type: docs
breadcrumbs: true
comments: false
book_kind: appendix
book_status: draft
---

本附录是全书的版本控制面。正文中的原理尽量保持跨小版本稳定，但命令、默认值、组件组合和界面必须绑定实际版本。读者复现实验时，先记录事实，再判断差异是否影响结论。

## A.1 PostgreSQL、Pigsty、OS、Patroni、PgBouncer、备份工具与扩展版本 {#appendix-a-1}

当前写作基线：

| 层次 | 基线 | 说明 |
|---|---|---|
| PostgreSQL 服务端 | 18.4 | 正式实验基线 |
| PostgreSQL 兼容阅读范围 | 14–18 | 仅在结论确实成立时采用；差异必须显式说明 |
| Pigsty | v4.4.0 | 2026-07-10 正式发布版本 |
| `pig` CLI | 1.5.1 | L2/L3 正式实验观察版本；与 Pigsty release 分开记录 |
| L1 参考 OS | Ubuntu 24.04.4 LTS | AMD64 与 ARM64 均可；记录实际补丁版本 |
| L2 正式环境 | Ubuntu 24.04 / aarch64 四 VM | 1×`pg-meta` + 3×`pg-test`；共享 hypervisor |
| L3 正式环境 | L2 host 上的私有 disposable PG18.4 clone | exact temporary root、Unix socket、无业务路由 |

L2 的三台 `pg-test` VM 在正式 run 中只有 1 vCPU、约 1.9 GiB RAM，是明确记录的
sandbox exception；它证明实验在该下限跑通，不构成生产 sizing。精确资源、网络和
限制见[附录 E](../e/)与
[`ch19/requirements.json`](/labs/ch19/requirements.json)。

Patroni、PgBouncer、HAProxy、pgBackRest 与扩展的小版本可能随操作系统仓库和离线包变化，因此不在正文中假定一个虚假的全平台统一值。进入实验节点后采样：

```bash
{
  printf 'captured_at=%s\n' "$(date -Is)"
  uname -a
  cat /etc/os-release
  postgres --version
  psql --version
  patronictl version
  pgbouncer --version
  haproxy -v
  pgbackrest version
} > component-versions.txt 2>&1
```

命令不存在或需要不同 PATH 时，保留失败输出并从软件包管理器补充，不得把“未采集”写成“未安装”。服务端 PostgreSQL 版本还要从连接内部复核：

```sql
SELECT
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num,
    version() AS build;
```

扩展分为“操作系统已提供”和“当前数据库已安装”两层。后者使用：

```sql
SELECT extname, extversion
FROM pg_catalog.pg_extension
ORDER BY extname;
```

不要用 `pg_available_extensions` 代替已安装清单，也不要假设一个数据库安装的扩展会自动出现在同实例的其他数据库中。

## A.2 强版本相关行为：并发 DDL、预备语句、排序规则、升级与恢复 {#appendix-a-2}

下列主题不得只写“PostgreSQL 支持”：

| 主题 | 必须绑定的版本或环境 |
|---|---|
| 并发 DDL、锁级别与快速默认值 | PostgreSQL 大版本、对象状态与表规模 |
| 驱动预备语句与 PgBouncer | 驱动、PgBouncer 版本和池化模式 |
| locale、collation 与索引一致性 | PostgreSQL、libc／ICU／builtin 提供者及操作系统 |
| `pg_upgrade` 与逻辑迁移 | 源／目标大版本、扩展二进制与排序规则 |
| 备份、WAL 与 PITR | PostgreSQL、pgBackRest、仓库格式与时间线 |
| 系统目录和统计视图列 | PostgreSQL 大版本 |
| Pigsty 参数、端口、Playbook 与面板 | Pigsty 发布版本与所用配置模板 |

强版本相关实验在正文中同时给出“本书基线的已验证路径”和“迁移到其他版本时要重新验证的观察点”。不能验证的行为明确标为未决，不用相近版本输出冒充。

## A.3 版本增量通过记录与勘误链接 {#appendix-a-3}

每次升级写作基线都执行一次版本增量通过：

1. 创建全新的 L1，记录安装制品校验值与全部版本；
2. 从 ch01 开始运行 setup、exercise、verify 与 reset；
3. 对比系统目录、命令输出、默认值和服务路由；
4. 将差异分为“输出变化”“行为变化”“安全边界变化”“实验失效”；
5. 修正文稿与脚本，并记录最小受影响版本范围；
6. 三种样章通过后，再推进全书回归。

勘误记录至少包含：

| 字段 | 含义 |
|---|---|
| 发现版本 | 问题出现在哪个 PostgreSQL、Pigsty 或组件版本 |
| 影响页面 | 稳定 URL 与小节编号 |
| 原结论 | 当时成立的版本和条件 |
| 修正结论 | 新版本行为与证据 |
| 读者动作 | 是否需要修改脚本、重建实验或采取安全措施 |
| 验证状态 | 未复现、已复现、已修正、已回归 |

版本更新不覆盖历史事实。若旧版行为在当时确实成立，应保留适用范围并补充新行为；只有事实本身错误时才作为勘误修正。
