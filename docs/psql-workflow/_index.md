---
title: 第 2 章 手到擒来：psql 与可复现工作流
linkTitle: 02 手到擒来：psql 与可复现工作流
weight: 120
aliases:
- "/ch02/"
- "/volume-1/psql-workflow/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch02
book_number: 2
book_part: part-1
book_status: draft
---

会执行一条 SQL，不等于能可靠地完成一次数据库任务。真正可交付的操作必须知道自己连到了哪里，遇错立即停止，留下足够证据，允许安全重跑，并能证明失败没有留下半成品。本章把这些要求压缩成后续 34 章共同使用的最小工作流。

这里不会把 `psql` 写成命令手册，也不会假装一套脚本能消除所有变更风险。我们的目标更具体：把“登录服务器后临时敲几条命令”改造成一个输入明确、行为可审查、结果可验证、退出码可信的任务。

## 本章目标

完成本章后，读者应当能够：

- 用 URI、service file 与 passfile 分离目标、行为和秘密，并理解连接参数的覆盖顺序；
- 让提示符、`application_name` 与上下文快照共同暴露当前数据库、角色、端点和事务状态；
- 用 `psql` 元命令探索对象，同时回到系统目录验证其来源；
- 编写遇错即停、退出码可信、变量引用安全、事务边界明确的 SQL 脚本；
- 用确定性夹具、校验摘要与机器可读输出建立可复现输入；
- 运行一个最小 `pgbench` 工作负载，只验证执行链路，不偷渡性能结论；
- 完成一次可检查、可恢复、可验证的逻辑备份闭环；
- 把上述动作组合成带证据包的可重跑任务，并证明错误注入不会留下半成品。

## 开始之前

本章承接 [1.7 实战](/postgresql-pigsty-map/07/) 创建的 `pg36_shop`、`shop` 模式和三个角色。若环境尚未具备这些对象，先完成 ch01；若对象已经承载其他数据，不要用本章实验覆盖它们。

示例基线是 PostgreSQL 18.4 与 Pigsty v4.4。核心 `psql` 工作流适用于 PostgreSQL 14–18；`COPY ... ON_ERROR`、`REJECT_LIMIT` 等版本敏感能力会单独标出。实验使用 L1 的 Pigsty `default` 服务（默认端口 `5436`）执行管理任务，因为它跟随主库并直连 PostgreSQL；这不是 PostgreSQL 标准端口，也不代表所有平台都必须这样命名。

本章提供的可下载资产位于：

- [连接服务文件示例](/labs/ch02/pg_service.conf.example)
- [`psqlrc` 示例](/labs/ch02/psqlrc.example)
- [上下文保护脚本](/labs/ch02/context.sql)
- [确定性夹具脚本](/labs/ch02/setup.sql)
- [状态验证脚本](/labs/ch02/verify.sql)
- [最小 `pgbench` 工作负载](/labs/ch02/workload.sql)
- [故障注入脚本](/labs/ch02/broken.sql)
- [安全重置脚本](/labs/ch02/reset.sql)
- [综合任务入口](/labs/ch02/task.sh)

## 本章主线

```mermaid
flowchart LR
  A["连接参数<br/>目标与凭据"] --> B["上下文快照<br/>确认落点"]
  B --> C["探索与取证<br/>人读 + 机读"]
  C --> D["可靠脚本<br/>失败即停"]
  D --> E["确定性数据<br/>校验摘要"]
  E --> F["最小负载<br/>验证链路"]
  F --> G["逻辑备份<br/>恢复验证"]
  G --> H["综合任务<br/>证据 + 复位"]
```

这条路径有意先解决“正确地执行”，再碰性能与备份。一个无法可靠停止、重跑和复位的实验，即使偶然得到漂亮结果，也没有教学或工程价值。

## 本章目录

### [2.1 可靠连接与上下文保护](01/)

- [2.1.1 连接 URI、服务文件与环境变量](01/#item-2-1-1)
- [2.1.2 `application_name`、提示符与上下文快照](01/#item-2-1-2)
- [2.1.3 防止连错库、用错角色和改错模式](01/#item-2-1-3)

本节把连接信息拆成非秘密目标、秘密凭据与会话行为，并建立所有写操作之前都要执行的上下文保护。

### [2.2 用 psql 探索与取证](02/)

- [2.2.1 对象、权限和会话元命令](02/#item-2-2-1)
- [2.2.2 扩展显示、分页、计时与查询缓冲区](02/#item-2-2-2)
- [2.2.3 元命令与系统目录查询互相验证](02/#item-2-2-3)

本节区分交互式探索与自动化取证：前者追求快速理解，后者要求稳定字段、明确排序与可保存证据。

### [2.3 编写可靠 SQL 脚本](03/)

- [2.3.1 `ON_ERROR_STOP`、退出码与失败即停](03/#item-2-3-1)
- [2.3.2 变量、条件、包含文件与事务包装](03/#item-2-3-2)
- [2.3.3 幂等、重入与执行前预览](03/#item-2-3-3)
- [2.3.4 日志、清单与机器可读结果](03/#item-2-3-4)

本节建立本书的脚本协议：`-X`、`ON_ERROR_STOP`、安全变量引用、显式事务边界、标准输出与错误输出分离。

### [2.4 输入、输出与确定性数据](04/)

- [2.4.1 `COPY` 与 `\copy` 的权限和执行边界](04/#item-2-4-1)
- [2.4.2 CSV、文本与错误隔离](04/#item-2-4-2)
- [2.4.3 固定随机种子、规模档位与校验和](04/#item-2-4-3)

本节让实验输入可重建、输出可比较，并解释 PostgreSQL 18 容错导入与早期版本工作流的差异。

### [2.5 最小 pgbench 工作负载](05/)

- [2.5.1 初始化自定义脚本与参数](05/#item-2-5-1)
- [2.5.2 区分吞吐、延迟、错误与环境噪声](05/#item-2-5-2)
- [2.5.3 本节只建立可复现基线，不做性能结论](05/#item-2-5-3)

本节只证明工作负载能以确定输入完成预期事务数。硬件比较、容量模型与正式压测留给
[ch26《胸有成竹：容量规划与压测基线》](/capacity-benchmarking/)。

### [2.6 最小逻辑备份闭环](06/)

- [2.6.1 `pg_dump` 的对象、模式与自定义格式](06/#item-2-6-1)
- [2.6.2 `pg_restore` 的清单、选择性恢复与验证](06/#item-2-6-2)
- [2.6.3 与 ch21《未雨绸缪：备份体系与恢复演练》的边界](06/#item-2-6-3)

本节不以“生成了一个文件”为成功，而以“能检查清单、恢复到隔离目标并验证状态”为闭环。

### [2.7 实战：把人工操作变成可重跑任务](07/)

- [2.7.1 生成 `pg36_shop` 初始数据与校验摘要](07/#item-2-7-1)
- [2.7.2 从 Pigsty 服务端点执行并保存证据](07/#item-2-7-2)
- [2.7.3 注入脚本错误，验证停止、修复与复位](07/#item-2-7-3)

本节把前六节组合成 `task.sh all`：创建夹具、验证状态、运行最小负载、注入语法错误并检查回滚。重置从不包含在默认路径中。

## 本章产物与验收

完成综合实验后，证据目录至少应包含：

| 文件 | 证明什么 | 不证明什么 |
|---|---|---|
| `manifest.txt` | 客户端版本、服务端版本、数据库、脚本哈希与采集时间 | 不证明运行期间没有外部噪声 |
| `verify.txt` | 夹具行数、边界值和校验和符合预期 | 不证明业务模型正确 |
| `pgbench.txt` | 指定脚本完成 20/20 个事务且无失败 | 不证明环境具有某个生产 TPS |
| `broken.status` | 错误脚本返回 `3`，标记行数量为 `0` | 不证明所有失败模式都会自动回滚 |
| `*.stderr` | NOTICE、警告和错误没有被标准输出吞掉 | 空文件不等于服务端日志无事件 |

章节验收不是背命令，而是能解释以下问题：

1. 为什么 service file 适合保存端点，却不应默认保存密码？
2. 为什么漂亮的提示符不能替代执行前的 SQL 上下文断言？
3. 为什么没有设置 `ON_ERROR_STOP` 的 `psql -f` 可能在 SQL 报错后仍继续？
4. 幂等为什么不等于“所有语句前都加 `IF EXISTS`”？
5. 为什么固定随机种子仍不能固定延迟和 TPS？
6. 为什么 dump 文件只有在恢复并验证后才构成一次有效演练？

下一章会把本章生成的确定性夹具当作输入样本，但不会把它误当成业务模型。我们将从业务语言提取实体、事件与不变量，开始 [ch03《正本清源：从业务规则到关系模型》](/logical-data-model/)。

## 参考资料

- [PostgreSQL 18：psql](https://www.postgresql.org/docs/18/app-psql.html)
- [PostgreSQL 18：libpq 环境变量](https://www.postgresql.org/docs/18/libpq-envars.html)
- [PostgreSQL 18：连接服务文件](https://www.postgresql.org/docs/18/libpq-pgservice.html)
- [PostgreSQL 18：COPY](https://www.postgresql.org/docs/18/sql-copy.html)
- [PostgreSQL 18：pgbench](https://www.postgresql.org/docs/18/pgbench.html)
- [PostgreSQL 18：pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html)
- [PostgreSQL 18：pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html)
- [Pigsty v4.4：PostgreSQL 服务与接入](https://pigsty.io/docs/pgsql/service/)

---

[上一章：盲人摸象：PostgreSQL 与 Pigsty 全局地图](/postgresql-pigsty-map/) · [返回上卷导读](/upper-volume/) · [下一章：正本清源：从业务规则到关系模型](/logical-data-model/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
