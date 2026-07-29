---
title: "28. 除旧布新：VACUUM 与膨胀治理"
weight: 2800
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
把 `ch27` 的参数治理结果落到“数据清理执行面”，用 `VACUUM` 与膨胀治理把系统从“能跑”提升到“可长期稳定运行”，并为 `ch29` 提供干净、可同步的数据基础。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `artifacts/ch28/01_baseline.csv`，包含表/索引大小、`n_dead_tup`、`age(relfrozenxid)` 三类基线数据，字段完整率 100%。  
2. 主线表 `public.orders_txn` 完成两轮清理后：`n_dead_tup` 下降至少 80%，`dead_pct`（死元组占比）低于 5%。  
3. 至少 1 张高频写表完成每表 `autovacuum` 参数与 `fillfactor` 落地，并可通过 `pg_class.reloptions` 查到生效值。  
4. 至少 1 个高膨胀索引完成 `REINDEX CONCURRENTLY`，索引大小下降至少 20% 或扫描性能回到基线范围内（偏差不超过 10%）。  
5. 交付 `docs/ch28/ch29_input.yaml`，含“清理后对象清单、冻结安全状态、同步前注意事项”，缺失字段为 0。

## 3) 章节边界
本章要讲什么（5-7 条）
1. 如何从 `ch27` 输入中筛出膨胀治理优先级。  
2. 如何建立表/索引/冻结风险三类清理基线。  
3. 如何执行手动 `VACUUM` 首轮收敛并验证效果。  
4. 如何设置每表 `autovacuum` 阈值与 `fillfactor`。  
5. 如何治理索引膨胀并控制锁影响。  
6. 如何做 `freeze` 安全检查，避免高 `xid` 年龄风险。  
7. 如何输出可复验验收结果并交接给 `ch29`。  

本章明确不讲什么（3-5 条）
1. 不讲复制拓扑设计、迁移路线选择、异构同步实施细节（`ch29`）。  
2. 不讲大版本升级与回滚策略（`ch30`）。  
3. 不讲源码级 `VACUUM` 内核实现细节。  
4. 不做工具大全、参数大全、命令大全式堆砌。  

## 4) 结构化细纲（6-8 节）
主线案例：`public.orders_txn`（高频 `UPDATE/DELETE` 订单流水表）  
支线案例：`public.orders_txn_status_idx`（主线表上的高膨胀索引）

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 28.1 | 承接 ch27：清理优先级落地 | 已有调优结果，但不知道先清哪张表 | `dead tuple`、膨胀率、优先级 | 执行 SQL 排序 `n_dead_tup` 与表大小，选出 Top10 | `docs/ch28/00_backlog.md` | S |
| 28.2 | 建立治理基线：表、索引、冻结 | 没有统一“前后对比”基准 | `xid` 年龄、`freeze`、基线快照 | 采集 `pg_stat_user_tables`、`pg_stat_user_indexes`、`age(relfrozenxid)` | `artifacts/ch28/01_baseline.csv` | S |
| 28.3 | 主线首轮：手动 VACUUM 收敛 | 死元组堆积已影响查询与扫描成本 | `VACUUM`、`autovacuum`、`ANALYZE` | `VACUUM (ANALYZE, VERBOSE) public.orders_txn;` 并记录前后指标 | `artifacts/ch28/02_vacuum_round1.log` | S |
| 28.4 | 每表参数：阈值与 fillfactor | 全局参数不足以覆盖热点表特征 | 每表参数、`fillfactor`、`HOT` 更新 | `ALTER TABLE ... SET (autovacuum_*, fillfactor=90);` 并校验 `reloptions` | `docs/ch28/01_table_level_tuning.sql` | S |
| 28.5 | 支线：索引膨胀治理 | 表清理后索引仍膨胀，查询未恢复 | 索引膨胀、`REINDEX CONCURRENTLY`、锁影响 | 对 `public.orders_txn_status_idx` 执行并发重建并对比大小 | `artifacts/ch28/03_index_rebuild.csv` | A |
| 28.6 | 冻结安全：高龄对象处理 | 清理了膨胀但存在高 `xid` 年龄风险 | `freeze`、`xid` 年龄、`VACUUM FREEZE` | 筛出高龄对象并执行定向 `VACUUM (FREEZE)` | `artifacts/ch28/04_freeze_guard.csv` | A |
| 28.7 | 验收与交接：面向 ch29 | 治理后缺少可迁移可同步的交付物 | 验收阈值、回归对比、交接清单 | 执行验收 SQL 清单并生成交接文件 | `artifacts/ch28/99_acceptance.md`、`docs/ch28/ch29_input.yaml` | S |

## 5) 实战实验设计
实验 A（基础）  
目标：完成主线表 `orders_txn` 的“识别-清理-验证”闭环。  
前置条件：已拿到 `ch27` 输出参数与负载基线；具备 `VACUUM` 与 `ALTER TABLE` 权限。  
步骤：  
1. 采集主线表清理前指标（大小、`n_dead_tup`、`last_autovacuum`）。  
2. 执行 `VACUUM (ANALYZE, VERBOSE) public.orders_txn;`。  
3. 设置每表 `autovacuum` 阈值与 `fillfactor`。  
4. 间隔一个业务周期再次采集指标。  
5. 对比前后差异并记录。  
验收标准：  
1. `n_dead_tup` 下降至少 80%。  
2. `dead_pct` 低于 5%。  
3. `last_autovacuum` 在目标观察窗口内发生更新。  
4. 产出 `02_vacuum_round1.log` 与前后对比表。  

实验 B（进阶）  
目标：在业务持续写入下完成“索引膨胀 + 冻结风险”联合治理。  
前置条件：实验 A 通过；可在业务低峰执行并发索引重建。  
步骤：  
1. 识别主线表最膨胀索引并记录大小。  
2. 执行 `REINDEX INDEX CONCURRENTLY public.orders_txn_status_idx;`。  
3. 执行高龄对象筛查并对 TopN 执行 `VACUUM (FREEZE)`。  
4. 复测索引大小、`age(relfrozenxid)`、核心 SQL 延迟。  
5. 生成 `ch29` 交接清单。  
验收标准：  
1. 索引大小下降至少 20%。  
2. 高龄对象 `age(relfrozenxid)` 下降至少 30%。  
3. 业务核心 SQL `p95` 不劣化超过 10%。  
4. 交接文件字段完整率 100%。  

## 6) 常见误区与纠偏（5 条）
1. 误区：只跑一次 `VACUUM` 就宣布完成。纠偏：必须做“前后两轮采样 + 阈值验收”。  
2. 误区：只看表膨胀，不看索引膨胀。纠偏：表和索引分开验收，各自给出量化目标。  
3. 误区：全局调 `autovacuum`，忽略热点表差异。纠偏：优先落每表参数。  
4. 误区：看到高 `xid` 年龄不处理。纠偏：建立高龄对象清单并定向 `VACUUM (FREEZE)`。  
5. 误区：直接用 `VACUUM FULL` 处理线上热点表。纠偏：先常规 `VACUUM` + 并发索引重建，`VACUUM FULL` 仅在明确停机窗口使用。  

## 7) 与前后章衔接
承接 ch27（2-3 条）
1. 直接使用 `ch27` 交付的 `autovacuum` 参数现状与 `dead_tuple_top10` 作为本章输入。  
2. 继承 `ch27` 的变更纪律：单变量、可回退、可复验。  
3. 沿用 `ch27` 的资源预算边界，避免“清理动作反向打爆资源”。  

交付给 ch29（2-3 条）
1. 交付“清理后对象状态 + 冻结安全状态”，减少复制与迁移中的额外放大成本。  
2. 交付“需避峰处理对象清单”，为 `ch29` 的同步窗口规划提供依据。  
3. 交付“清理后体量基线”，作为迁移与同步速率估算输入。  

## 8) 自检与修正
自检清单（8 项）
1. 只处理 `ch28`，未扩写其他章节正文。  
2. 章节名与编号保持为 `28. 除旧布新：VACUUM 与膨胀治理`。  
3. 结构化细纲为 7 节，满足 6-8 节约束。  
4. 每节“必讲概念”均不超过 3 个。  
5. 每节都有可执行动作（SQL/命令/检查项）。  
6. 案例数量符合“1 条主线 + 1 条支线”。  
7. 学习完成标准与实验验收均为可量化、可复验口径。  
8. 新术语首次引入控制在 11 个：`VACUUM`、`autovacuum`、`dead tuple`、膨胀率、`freeze`、`xid` 年龄、`HOT` 更新、`fillfactor`、`REINDEX CONCURRENTLY`、`VACUUM FREEZE`、`VACUUM FULL`。  

本次细纲中你主动修正的 3 处问题
1. 删除了“复制/迁移实施步骤”，避免抢占 `ch29` 内容边界。  
2. 将原本可能分散的多个案例收敛为“1 主线 + 1 支线”。  
3. 把“定期观察效果”改为明确阈值（80%、5%、20%、30%、10%）的验收口径。
