---
title: "16. 合纵连横：分布式与分析计算扩展"
weight: 1600
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
在 `ch15` 时空单库基线上，本章用最小可运行 PoC 对比分布式扩展与分析扩展，完成可量化的方案决策，并交付 `ch17` 可直接接入的数据库内接口契约。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 可执行 `sql/ch16/01_replay_ch15.sql` 与 `sql/ch16/02_collect_profile.sql`，生成 `artifacts/ch16/baseline_latency.csv` 与 `artifacts/ch16/hot_queries.txt`，SQL 错误数为 `0`。  
2. 完成分布式候选 PoC 后，`artifacts/ch16/shard_skew.csv` 可计算出分片倾斜率（最大分片行数/最小分片行数）`<= 1.5`。  
3. 完成分析候选 PoC 后，核心聚合查询 `P95` 相比 `ch15` 基线下降 `>= 40%`，且写入 `P95` 回退 `<= 20%`。  
4. 输出 `artifacts/ch16/decision_matrix.md`，包含门槛、评分、入选方案、淘汰原因（不少于 3 条）。  
5. 执行 `sql/ch16/08_ch17_contract.sql` 成功创建接口对象，`SELECT count(*) FROM pg_proc WHERE proname LIKE 'risk_%';` 返回值 `>= 3`。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 复跑 `ch15` 结果，建立 `ch16` 性能基线与扩展触发点。  
2. 将需求拆成实时链路与分析链路，明确扩展边界。  
3. 用最小分布式 PoC 验证分片键是否可用。  
4. 用最小分析 PoC 验证列存/物化视图收益。  
5. 定义在线库与分析库的数据边界和新鲜度门槛。  
6. 用决策矩阵固化选型结论与验收条件。  
7. 输出 `ch17` 需要的存储过程接口契约（不展开实现细节）。  

- 本章明确不讲什么（3-5 条）
1. 生产级高可用拓扑与故障切换实施。  
2. 灾备、跨机房应急、值班响应流程。  
3. BI 前端建模与可视化平台搭建。  
4. 各类数据库/工具横评大全。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 同卡短时异地风控（承接 `ch15` 时空规则）。  
支线案例：`ops-dashboard` 小时级城市风险看板（仅用于对照分析链路收益）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 16.1 | 先复跑：把 ch15 基线量化出来 | 现有单库到底慢在哪、瓶颈是否稳定复现 | 工作负载画像、性能基线、扩展边界 | `psql -f sql/ch16/01_replay_ch15.sql && psql -f sql/ch16/02_collect_profile.sql` | `artifacts/ch16/baseline_latency.csv`、`artifacts/ch16/hot_queries.txt` | S |
| 16.2 | 目标拆分：实时链路与分析链路 | 为什么不能用一套策略同时满足两类目标 | 扩展边界、数据新鲜度SLA、决策矩阵 | `psql -f sql/ch16/03_sla_snapshot.sql` 并填写 `artifacts/ch16/decision_matrix.md` 初稿 | `artifacts/ch16/sla_snapshot.csv`、`artifacts/ch16/decision_matrix.md`（v1） | S |
| 16.3 | 分布式候选 PoC：先验分片键 | 分片后是否均衡、是否影响核心查询 | 分片键、分布式表、协调节点 | `psql -f sql/ch16/04_dist_poc.sql && psql -f sql/ch16/04_dist_skew_check.sql` | `artifacts/ch16/shard_skew.csv`、`artifacts/ch16/dist_query_metrics.csv` | S |
| 16.4 | 分析候选 PoC：列存与物化视图 | 聚合分析能提速多少，代价是什么 | 列存、物化视图、数据新鲜度SLA | `psql -f sql/ch16/05_analytic_poc.sql; psql -c "REFRESH MATERIALIZED VIEW CONCURRENTLY risk_hourly_mv;"` | `artifacts/ch16/analytic_query_metrics.csv`、`artifacts/ch16/mv_refresh_cost.csv` | A |
| 16.5 | 组合边界：在线库与分析库怎么分工 | 哪些数据留在线库，哪些进入分析链路 | 扩展边界、数据新鲜度SLA、性能基线 | `psql -f sql/ch16/06_boundary_lag.sql` | `artifacts/ch16/data_boundary.md`、`artifacts/ch16/lag_report.csv` | A |
| 16.6 | 方案定稿：用决策矩阵落锤 | 如何避免拍脑袋选型并可复验 | 决策矩阵、性能基线、扩展边界 | `psql -f sql/ch16/07_scorecard.sql && psql -f sql/ch16/07_acceptance.sql` | `artifacts/ch16/decision_matrix.md`（v2） 、`artifacts/ch16/acceptance_report.md` | S |
| 16.7 | 交付 ch17：接口契约先行 | 下一章如何直接进入函数/触发器实现 | 存储过程接口、决策矩阵、数据新鲜度SLA | `psql -f sql/ch16/08_ch17_contract.sql` | `sql/ch16/ch17_contract.sql`、`docs/ch16/ch17_handoff.md` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：在单环境内完成“分布式候选 vs 分析候选”的最小对比，并形成初版决策。  
前置条件：已完成 `ch15`；测试库含风控事件样本；可执行 `sql/ch16` 脚本。  
步骤：  
1. 执行 `01_replay_ch15.sql`、`02_collect_profile.sql` 得到基线。  
2. 执行 `04_dist_poc.sql`、`04_dist_skew_check.sql` 得到分布式候选结果。  
3. 执行 `05_analytic_poc.sql` 并刷新物化视图，得到分析候选结果。  
4. 执行 `03_sla_snapshot.sql`，填写 `decision_matrix.md` 初稿。  
验收标准：  
1. 三类结果文件齐全：基线、分布式候选、分析候选。  
2. 分片倾斜率 `<= 1.5`。  
3. 聚合查询 `P95` 提升 `>= 40%`。  
4. `decision_matrix.md` 含明确“选/不选”结论与量化依据。  

实验 B（进阶）  
目标：落地组合方案并交付 `ch17` 接口契约，跑通端到端验证。  
前置条件：实验 A 通过；已确定目标方案；可创建数据库对象。  
步骤：  
1. 执行 `06_boundary_lag.sql` 固化数据边界与延迟检查。  
2. 执行 `07_scorecard.sql`、`07_acceptance.sql` 输出最终验收。  
3. 执行 `08_ch17_contract.sql` 创建 `risk_*` 接口对象。  
4. 插入一组固定测试事件，验证实时结果与小时聚合结果。  
验收标准：  
1. `acceptance_report.md` 全部检查项为 `PASS`。  
2. 数据新鲜度延迟满足章节门槛（例如 `<= 5 分钟`）。  
3. `risk_*` 接口对象数量 `>= 3` 且可调用。  
4. 主线案例固定样例命中率 `100%`。  

## 6) 常见误区与纠偏（5 条）
1. 误区：只要分布式就一定更快。纠偏：先看基线瓶颈是否来自单机算力、数据量还是查询写法。  
2. 误区：先建分布式表再想分片键。纠偏：先做分片键试算，先过倾斜率门槛再建表。  
3. 误区：把实时查询和重聚合查询混在同一路径。纠偏：按实时链路/分析链路拆目标与 SLA。  
4. 误区：只看平均耗时。纠偏：统一看 `P95`、写入回退比例、刷新成本。  
5. 误区：选型只写结论。纠偏：决策矩阵必须写门槛、得分、淘汰原因与回退条件。  

## 7) 与前后章衔接
- 承接 ch15（2-3 条）
1. 直接复用 `ch15` 的时空表结构与规则 SQL，不重建业务模型。  
2. 直接复用 `ch15` 的验收方式（固定样例 + 量化指标）。  
3. 以 `ch15` 的性能报告作为 `ch16` 扩展触发基线。  

- 交付给 ch17（2-3 条）
1. 输出 `risk_*` 函数/过程接口签名，`ch17` 直接实现函数体与触发逻辑。  
2. 输出“哪些逻辑进库、哪些留应用层”的边界说明，避免 `ch17` 返工。  
3. 输出可复跑验收脚本，`ch17` 可在同口径下验证逻辑正确性。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch16`，未扩写其他章节正文。  
2. 章节编号与标题保持不变。  
3. 总节数为 `7`，满足 `6-8` 节约束。  
4. 每节关键概念不超过 `3` 个。  
5. 每节都有可执行动作（命令/SQL/检查）。  
6. 仅保留 `1` 条主线案例与 `1` 条支线案例。  
7. 学习标准、实验、验收均为可量化指标。  
8. 新术语控制在 `11` 个以内（未超过 `12`）。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了“高可用与故障切换细节”草稿内容，避免越界到下卷运维章节。  
2. 将“多案例并行”收敛为单主线 + 单支线，保证学习路径单线推进。  
3. 把“效果更好/可行”类表述改成 `P95`、倾斜率、延迟、命中率等硬指标。
