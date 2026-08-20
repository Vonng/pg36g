# 《PostgreSQL 与 Pigsty：36 计》全书审阅台账

审阅日期：2026-07-30

## 目标与完成定义

目标不是把书稿“扫一遍”，而是从首次阅读者、应用开发者、DBA/SRE 和平台工程师四种
视角，逐文件检查：

1. 读者是否先理解 WHY，再获得 WHAT 与 HOW；
2. 原理、步骤、证据、验收和失败恢复是否形成闭环；
3. PostgreSQL/Pigsty 机制、版本边界、命令语义和公式是否准确；
4. 生产动作是否说明目标、authority、风险、停止线与恢复条件；
5. 章节编号、术语、目录、锚点和内部链接是否一致；
6. 页面是否存在编辑部口吻、重复内容、占位内容或影响渲染的 Markdown 错误。

完成定义：当前 `docs/` 下 301 个 Markdown 文件全部通读；发现的问题就地修订；章节
元数据同步；Hugo 构建、全书结构和内部链接检查通过。

## 总体判断

这本书最有价值的部分，不是覆盖面，而是反复要求读者把“机制、目标环境、动作、证据、
验收”连成工程闭环。它已经明显强于只罗列参数、SQL 和运维命令的 PostgreSQL 资料，
尤其是事务、发布、HA、恢复、事故与取证几条主线能够互相咬合。

原稿的主要问题也很集中：

- 首页、序言、导读和部分章首页混入写作状态、URL 层级和“样章”等编辑部信息，打断
  读者进入主题；
- 少数跨章引用仍指向旧目录，风险模型在 R0–R2 与 R0–R3 之间漂移；
- 个别技术表述把近似模型写成了机制事实，例如同步提交值、事务中止成本、autovacuum
  最大阈值、vacuum progress 字段和 `pg_rewind`/checksum 前提；
- 部分公式量纲不成立，或把必要条件误写成求和；
- 可观测性章节有大量列表缺少空格，Markdown 会把它们渲染成连续段落；
- 中英混排、产品名大小写和少量句子翻译腔影响流畅度。

本轮已修正上述问题。全书仍保留它原本的技术密度，没有为了“好读”删掉前提、反例、
风险边界或证据要求。

## 逐文件覆盖

记法：花括号中的文件均位于该行目录下；每个文件均已完整通读和校对。

| 范围 | 已审文件 | 数量 |
|---|---|---:|
| `docs/` | `_index.md`, `preface.md`, `upper-volume.md`, `lower-volume.md`, `toc.md` | 5 |
| `docs/guide/` | `_index.md` | 1 |
| `docs/ch00/` | `_index.md`, `01.md`, `02.md`, `03.md` | 4 |
| ch01 `docs/postgresql-pigsty-map/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch02 `docs/psql-workflow/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch03 `docs/logical-data-model/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch04 `docs/data-types-constraints/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch05 `docs/query-transaction-locks/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch06 `docs/development-standards/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch07 `docs/query-plans-statistics/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch08 `docs/slow-query-diagnosis/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch09 `docs/index-design/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch10 `docs/concurrency-isolation/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch11 `docs/schema-change-release/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch12 `docs/database-to-service/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch13 `docs/functions-triggers-procedures/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch14 `docs/extensions-ecosystem/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch15 `docs/search/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch16 `docs/spatiotemporal/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch17 `docs/analytics-distributed/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch18 `docs/data-platform-boundaries/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch19 `docs/deployment-baseline/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch20 `docs/high-availability/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch21 `docs/backup-recovery/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch22 `docs/connection-pooling-routing/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch23 `docs/authentication-authorization-security/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch24 `docs/slo-sop-governance/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch25 `docs/observability/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch26 `docs/capacity-benchmarking/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch27 `docs/configuration-tuning/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch28 `docs/vacuum-freeze-bloat/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch29 `docs/logical-replication-migration/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch30 `docs/version-upgrade/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch31 `docs/incident-response/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch32 `docs/pitr/` | `_index.md`, `01.md`–`06.md` | 7 |
| ch33 `docs/failover-rebuild/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch34 `docs/overload-resource-incidents/` | `_index.md`, `01.md`–`08.md` | 9 |
| ch35 `docs/data-rescue-forensics/` | `_index.md`, `01.md`–`07.md` | 8 |
| ch36 `docs/postmortem-platform-improvement/` | `_index.md`, `01.md`–`07.md` | 8 |
| `docs/indexes/` | `_index.md`, `capabilities.md`, `incidents.md`, `partition.md`, `roles.md`, `tasks.md` | 6 |
| `docs/appendices/` | `_index.md`, `a.md`, `b.md`, `c.md`, `d.md`, `e.md`, `f.md` | 7 |
| **合计** | **当前书稿全部 Markdown 文件** | **301** |

## 已完成的关键修订

### 读者路径

- 重写首页、序言和导读的进入方式，明确不同角色的阅读路径、章节价值和学习产出；
- 删除章首页中对普通读者无价值的“所属位置”、兼容 URL 和写作状态说明；
- 把“样章”“写作基线”“当前草稿”等编辑部口吻改成诊断方法、复现基线和验收方法；
- 保留高密度技术内容，但把重要结论放到机制、条件和验证步骤之后。

### 技术准确性

- 修正 `synchronous_commit` 的有效值与 `on` 的等待语义；
- 重写 cancel/terminate 后果：PostgreSQL 中止事务不会逐 tuple 做物理 undo；真正需要
  处理的是锁和资源释放、既有 WAL/脏页、复制追赶、dead tuples 与后续 vacuum；
- 修正 `plan_cache_mode=auto` 的前五次 custom plan 与后续成本比较逻辑；
- 修正 recoverability 公式、内存最坏并发公式和 latency SLI 分子；
- 修正 PostgreSQL 18 autovacuum 最大阈值 `-1` 的禁用语义及 SQL；
- 更新 PostgreSQL 18 `pg_stat_progress_vacuum` 字段；
- 明确 PostgreSQL 18 checksum 默认值、实际 control state 和 `filenode` 身份边界；
- 明确物理复制不会分发扩展二进制，补齐查询、启动、恢复和升主的不同失败条件。

### 跨章一致性与安全

- 统一 R0–R3：R2 是隔离、受控且恢复路径已验证的状态变更/演练；R3 是触及生产
  数据、流量、authority/lineage 或恢复昂贵的动作；
- 区分隔离 failover/PITR 与生产 authority 切换，不再给命令贴脱离环境的固定风险；
- 修正分区生命周期、发布章节和附录中的旧章节号；
- 同步 `data/chapters.yaml`、正文、章首页和全书目录中的标题；
- 保留生产动作的目标解析、独立复核、停止线、原件保护和业务验收要求。

### 语言与渲染

- 修正 PgBouncer 大小写、中英缺空格、翻译腔和不完整句；
- 修复 440 个代码块外的 Markdown 列表标记，其中可观测性章节占 435 个；
- 代码块中的 `-c`、`->`、搜索语法和负数未改动；
- 删除长篇重复导航说明，减少正文前的摩擦。

## 验收结果

- 301 个当前书稿文件全部完成逐文件通读；
- 36 章、242 个正式节页、772 个三级主题的脚手架一致；
- Hugo 构建成功；
- 5,053 条内部 Markdown 链接和锚点全部解析；
- 章节号与目标链接错配：0；
- 未闭合代码块、空标题、TODO/TBD/FIXME/占位内容：0；
- 跨文件重复长段落：0；
- 代码块外缺失空格的列表标记：0；
- `git diff --check` 通过。

## 后续版本的审校重点

下一次 PostgreSQL、Pigsty、Patroni、PgBouncer 或 pgBackRest 基线升级时，不应重新泛读
全书，而应先按附录 A 的版本增量流程重跑：默认值与系统目录、命令输出、服务路由、
恢复链和实验验收。外部产品文档变化优先回查 ch14–ch30；事故动作语义变化优先回查
ch31–ch35。
