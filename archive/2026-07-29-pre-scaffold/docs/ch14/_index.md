---
title: "14. 见微知著：全文检索与向量检索"
weight: 1400
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
`ch14` 的目标是把 `ch13` 已选定的扩展路线落成一套可验收的“全文检索 + 向量检索 + 混合检索”实现闭环，并产出可直接进入 `ch15` 的查询模板与基线。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 能执行 `sql/ch14/01_prepare.sql` 与 `sql/ch14/01_baseline.sql`，产出 `artifacts/ch14/baseline_metrics.csv`，且基线查询成功率为 `100%`。  
2. 能分别跑通全文检索与向量检索 SQL，`Top-10` 结果均非空，且查询错误数为 `0`。  
3. 能执行混合检索脚本并产出 `artifacts/ch14/hybrid_topk.csv`，`Top-K 命中率 >= 0.85`。  
4. 能执行性能验收脚本，得到 `P95 延迟 <= 120ms`（同一测试口径）。  
5. 能打包 `artifacts/ch14/ch15_handoff_pack.tgz`，交接清单文件齐全率 `100%`。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 从 `ch13` 交接包直接启动主线案例，不重做选型。  
2. 在同一业务数据上先跑通全文检索最小闭环。  
3. 在同一业务数据上再跑通向量检索最小闭环。  
4. 将两路结果合并为一条混合检索 SQL 管线。  
5. 用统一指标做质量与性能双验收。  
6. 把流程固化为可回归的脚本与检查项。  
7. 预留 `ch15` 的时间与空间过滤入口（仅模板，不展开时空专题）。  

- 本章明确不讲什么（3-5 条）
1. 大模型训练、微调、蒸馏流程。  
2. 向量数据库横向评测与产品排行榜。  
3. 分布式检索系统架构设计。  
4. RAG 全栈应用工程实现。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 的“交易备注检索 + 相似请求召回”。  
支线案例（仅 1 条）：`profile-service` 的“姓名模糊检索”（只做轻量对照，不展开）。  

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 14.1 | 从 ch13 交接包启动检索工程 | 如何把上一章结论转成可运行起点 | 基线查询、验收口径、词典配置 | `tar -xzf artifacts/ch13/ch14_handoff_pack.tgz -C artifacts/ch14/`；`psql -f sql/ch14/01_prepare.sql`；`psql -f sql/ch14/01_baseline.sql` | `docs/ch14/case_scope.md`、`artifacts/ch14/baseline_metrics.csv` | S |
| 14.2 | 全文检索最小闭环 | 如何让中文/短文本先可搜、再可评估 | `tsvector`、`tsquery`、`GIN` | `psql -f sql/ch14/02_fts.sql`；`psql -f sql/ch14/02_fts_check.sql` | `artifacts/ch14/fts_topk.csv`、`artifacts/ch14/fts_plan.txt` | S |
| 14.3 | 向量检索最小闭环 | 如何让语义相似检索可落地 | 嵌入向量、`IVFFlat`、余弦距离 | `psql -f sql/ch14/03_vector.sql`；`psql -f sql/ch14/03_vector_check.sql` | `artifacts/ch14/vector_topk.csv`、`artifacts/ch14/vector_plan.txt` | S |
| 14.4 | 混合检索一条 SQL 跑通 | 如何融合关键词命中与语义相似 | 候选集、重排、混合得分 | `psql -f sql/ch14/04_hybrid.sql`；`psql -f sql/ch14/04_hybrid_check.sql` | `artifacts/ch14/hybrid_topk.csv`、`docs/ch14/hybrid_formula.md` | S |
| 14.5 | 质量与性能双验收 | 如何判断“能用”而不是“看起来能用” | `Top-K 命中率`、`P95 延迟`、验收阈值 | `psql -f sql/ch14/05_quality.sql`；`pgbench -n -c 16 -T 120 -f sql/ch14/05_latency.sql` | `artifacts/ch14/accept_report.md` | S |
| 14.6 | 数据变化下的稳定性 | 数据增量后如何保持效果不漂移 | 词典配置、`IVFFlat`、`Top-K 命中率` | `psql -f sql/ch14/06_incremental_refresh.sql`；`psql -f sql/ch14/06_regression.sql` | `artifacts/ch14/regression_report.csv`、`docs/ch14/runbook.md` | A |
| 14.7 | 交付 ch15 的过滤模板 | 如何把检索主线自然接入时间/空间条件 | 候选集、混合得分、`P95 延迟` | `psql -f sql/ch14/07_time_geo_stub.sql`；`tar -czf artifacts/ch14/ch15_handoff_pack.tgz docs/ch14 artifacts/ch14` | `artifacts/ch14/ch15_handoff_pack.tgz` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：完成“全文 + 向量 + 混合”三段闭环并通过统一验收。  
前置条件：已具备 `ch13` 交接包、可用测试库、`vector` 扩展可创建。  
步骤：  
1. 执行 `01_prepare.sql` 与 `01_baseline.sql`。  
2. 执行 `02_fts.sql` 与 `02_fts_check.sql`。  
3. 执行 `03_vector.sql` 与 `03_vector_check.sql`。  
4. 执行 `04_hybrid.sql` 与 `04_hybrid_check.sql`。  
5. 执行 `05_quality.sql` 与 `05_latency.sql`。  
验收标准：  
1. `fts_topk.csv`、`vector_topk.csv`、`hybrid_topk.csv` 全部生成。  
2. 混合检索 `Top-K 命中率 >= 0.85`。  
3. 混合检索命中率较单路最优方案提升 `>= 8%`。  
4. `P95 延迟 <= 120ms`，SQL 错误数 `= 0`。  

实验 B（进阶）  
目标：在混合检索中加入时间窗口与空间边界占位过滤，为 `ch15` 做接口预热。  
前置条件：实验 A 通过；样本数据包含 `event_time`、`lon/lat` 字段。  
步骤：  
1. 执行 `07_time_geo_stub.sql` 生成参数化查询模板。  
2. 在同一查询集下分别跑“无过滤/时间过滤/时间+空间过滤”三组。  
3. 复跑 `05_quality.sql` 与 `05_latency.sql`，记录差异。  
4. 打包 `ch15_handoff_pack.tgz`。  
验收标准：  
1. 过滤后结果不出现越界数据（时间窗外、空间框外均为 `0` 条）。  
2. 过滤版 `P95` 相对无过滤版劣化不超过 `30%`。  
3. 过滤版 `Top-K 命中率 >= 0.75`。  
4. 交接包包含模板 SQL、指标报表、回归脚本、运行说明 4 类文件。  

## 6) 常见误区与纠偏（5 条）
1. 误区：`LIKE '%词%'` 就算全文检索。纠偏：必须落到 `tsvector + tsquery + GIN` 可验收闭环。  
2. 误区：向量分数越高就一定可用。纠偏：必须与关键词结果做混合重排。  
3. 误区：看几条样例“感觉不错”就上线。纠偏：必须跑固定查询集并看 `Top-K` 与 `P95`。  
4. 误区：只建索引，不做增量更新策略。纠偏：必须提供增量刷新与回归脚本。  
5. 误区：本章直接展开时空高级能力。纠偏：本章只交付过滤模板，深挖放在 `ch15`。  

## 7) 与前后章衔接
- 承接 ch13（2-3 条）
1. 直接复用 `ch13` 已收敛的分支与扩展组合，不再重新选型。  
2. 复用 `ch13` 的验收口径与基线数据，保证指标可对比。  
3. 复用 `ch13` 的退出/回退意识：每一步都留可回滚脚本。  

- 交付给 ch15（2-3 条）
1. 交付“候选集 -> 重排 -> 验收”的统一检索骨架，`ch15` 只需追加时空算子。  
2. 交付时间窗口与空间边界参数化模板，减少 `ch15` 前置准备。  
3. 交付可复跑的质量与延迟基线，作为 `ch15` 的回归对照。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch14`，未扩写其他章节正文。  
2. 章节编号与章节名保持不变。  
3. 结构化细纲为 7 节，满足 6-8 节要求。  
4. 每节必讲概念不超过 3 个。  
5. 每节均给出可执行动作（命令或 SQL）。  
6. 仅保留 1 条主线案例与 1 条支线案例。  
7. 学习标准与实验均提供量化验收阈值。  
8. 内容聚焦检索实战，未偏向模型训练或横评。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了“向量模型训练流程”草稿段，避免偏离本章边界。  
2. 将“多案例并行”收敛为“单主线 + 单支线”，降低学习分叉。  
3. 把“效果更好/性能可接受”改为 `Top-K` 与 `P95` 的明确阈值。
