---
title: "15. 经天纬地：时序与地理空间能力"
weight: 1500
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
`ch15` 的目标是把 `ch14` 的检索结果接入时间与空间维度，在单库内跑通“时序建模 + 空间建模 + 时空查询”的可验收闭环，并形成可交付 `ch16` 的基线。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 可执行 `sql/ch15/01_prepare.sql` 与 `sql/ch15/02_time_model.sql`，成功创建主线表、分区表与索引，SQL 错误数为 `0`。  
2. 在 `100万` 样本行下，时间窗口查询与时间分桶查询可复跑，`P95 <= 120ms`（同口径）。  
3. 空间近邻与区域查询结果可验证：越界数据为 `0`，且计划中不出现针对主表的全表 `Seq Scan`。  
4. 时空联合过滤规则（同卡短时异地）能输出固定测试样例中的目标事件 ID，命中率 `100%`。  
5. 可打包 `artifacts/ch15/ch16_handoff_pack.tgz`，包含 SQL、验收报表、回归脚本、数据字典四类文件，齐全率 `100%`。  

## 3) 章节边界
本章要讲什么（5-7 条）
1. 承接 `ch14` 结果集，补齐 `event_time` 与 `geom` 字段建模。  
2. 设计时间序列表及分区表策略。  
3. 建立时间分桶、时间窗口查询模板。  
4. 建立空间对象（`geometry`）与 `SRID` 约束。  
5. 建立 `GiST`/`BRIN` 索引与查询匹配关系。  
6. 完成时空联合过滤与规则化查询。  
7. 输出可复跑验收与 `ch16` 交接包。  

本章明确不讲什么（3-5 条）
1. 分布式部署、分片路由、跨节点事务。  
2. 大规模容量治理与运维调参专题。  
3. BI 可视化平台与地图前端开发。  
4. 多引擎横评与工具大全。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 风控事件（识别“同卡短时异地交易”）。  
支线案例：`fleet-service` 轨迹回放（仅用于对照时间分桶与区域查询写法）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 15.1 | 从 ch14 交接包启动时空场景 | 如何把上一章结果转成时空查询起点 | 事件时间、空间对象（geometry）、时空联合过滤 | `tar -xzf artifacts/ch14/ch15_handoff_pack.tgz -C artifacts/ch15/`；`psql -f sql/ch15/01_prepare.sql` | `docs/ch15/case_scope.md`、`artifacts/ch15/sample_check.csv` | S |
| 15.2 | 时间序列表与分区表落地 | 如何让时序数据可维护、可过滤 | 时间序列表、分区表、BRIN索引 | `psql -f sql/ch15/02_time_model.sql`；`psql -c "SELECT * FROM pg_partition_tree('payment_event');"` | `sql/ch15/ddl_time.sql`、`artifacts/ch15/time_model_report.txt` | S |
| 15.3 | 时间窗口与时间分桶查询 | 如何稳定做“最近N分钟/按小时统计” | 事件时间、时间分桶、BRIN索引 | `psql -f sql/ch15/03_time_query.sql`；`psql -f sql/ch15/03_time_explain.sql` | `artifacts/ch15/time_query_metrics.csv`、`artifacts/ch15/time_plan.txt` | S |
| 15.4 | 空间列、SRID 与索引策略 | 如何避免坐标混乱并保证查询可加速 | 空间对象（geometry）、SRID、GiST索引 | `psql -f sql/ch15/04_geo_model.sql`；`psql -c "SELECT Find_SRID('public','payment_event','geom');"` | `sql/ch15/ddl_geo.sql`、`artifacts/ch15/srid_check.txt` | S |
| 15.5 | 近邻与区域查询模板 | 如何写出可复用的空间查询 SQL | 近邻查询、区域查询、GiST索引 | `psql -f sql/ch15/05_geo_query.sql`；`psql -f sql/ch15/05_geo_explain.sql` | `artifacts/ch15/geo_query_metrics.csv`、`artifacts/ch15/geo_plan.txt` | A |
| 15.6 | 时空联合过滤与异常识别 | 如何把时间条件和空间条件合成一条规则 | 时空联合过滤、时间分桶、近邻查询 | `psql -f sql/ch15/06_spacetime_rule.sql`；`psql -c "SELECT count(*) FROM risk_alert;"` | `artifacts/ch15/risk_alert.csv`、`docs/ch15/rule_notes.md` | S |
| 15.7 | 章节验收与 ch16 交付 | 如何保证可复跑、可迁移到下一章 | 分区表、时间分桶、时空联合过滤 | `psql -f sql/ch15/07_acceptance.sql`；`tar -czf artifacts/ch15/ch16_handoff_pack.tgz artifacts/ch15 docs/ch15` | `artifacts/ch15/accept_report.md`、`artifacts/ch15/ch16_handoff_pack.tgz` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：跑通时序建模与时间查询闭环。  
前置条件：已完成 `ch14`；测试库可用；有 `payment_event` 样本数据。  
步骤：  
1. 执行 `01_prepare.sql` 初始化数据。  
2. 执行 `02_time_model.sql` 创建分区表与 `BRIN` 索引。  
3. 执行 `03_time_query.sql` 跑窗口查询与时间分桶。  
4. 执行 `03_time_explain.sql` 校验计划。  
验收标准：  
1. 分区树可查到预期分区数量（按脚本定义）。  
2. 最近 `15` 分钟查询结果与基准文件一致。  
3. 按小时分桶无缺桶（固定测试区间）。  
4. `P95 <= 120ms`，SQL 错误数 `0`。  

实验 B（进阶）  
目标：跑通空间查询与时空联合规则，识别“同卡短时异地交易”。  
前置条件：实验 A 通过；`postgis` 可创建；数据含经纬度。  
步骤：  
1. 执行 `04_geo_model.sql` 建立 `geometry` 列、`SRID` 校验与 `GiST` 索引。  
2. 执行 `05_geo_query.sql` 跑近邻查询与区域查询。  
3. 执行 `06_spacetime_rule.sql` 跑时空联合规则。  
4. 执行 `07_acceptance.sql` 汇总报告并打包交付。  
验收标准：  
1. 空间查询越界记录数为 `0`。  
2. 规则查询命中固定样例 ID 集合，准确率 `100%`。  
3. 针对主表的计划不出现全表 `Seq Scan`。  
4. 时空联合查询 `P95 <= 180ms`。  

## 6) 常见误区与纠偏（5 条）
1. 误区：把本地时间字符串直接入库。纠偏：统一存储 `事件时间`，并在入库时标准化时区。  
2. 误区：经纬度用文本或两个裸数列就够。纠偏：使用 `geometry` 列并固定 `SRID`。  
3. 误区：时序表只建普通 B-Tree。纠偏：按数据规模加分区表与 `BRIN`。  
4. 误区：空间查询先算全量距离再过滤。纠偏：优先使用近邻/区域模板并让 `GiST` 生效。  
5. 误区：时间与空间条件随意拼接。纠偏：固定“先时间后空间”的规则模板并用验收 SQL 回归。  

## 7) 与前后章衔接
承接 ch14（2-3 条）
1. 复用 `ch14` 结果集作为输入，不重做检索选型。  
2. 复用 `ch14` 的脚本化验收方式（固定查询集 + 指标输出）。  
3. 在 `ch14` 的过滤占位基础上，落成真实时空查询 SQL。  

交付给 ch16（2-3 条）
1. 交付时空查询分类与性能基线，作为分布式/分析扩展的选型输入。  
2. 交付明细表 + 时间分桶结果表模板，供 `ch16` 直接做跨节点与分析计算对接。  
3. 交付可复跑交接包，确保 `ch16` 先扩展算力、后复验结果。  

## 8) 自检与修正
先给出自检清单（8 项）
1. 仅处理 `ch15`，未扩写其他章节正文。  
2. 章节名与编号保持原样。  
3. 细纲共 `7` 节，满足 `6-8` 节约束。  
4. 每节关键概念不超过 `3` 个。  
5. 每节都给了可执行动作（命令/SQL/检查项）。  
6. 只保留 `1` 条主线案例与 `1` 条支线案例。  
7. 学习标准与实验均有量化验收阈值。  
8. 内容聚焦建模与查询策略，未展开分布式运维专题。  

再给出本次细纲中你主动修正的 3 处问题
1. 去掉了“多时空案例并行”草稿，收敛为单主线，避免学习分叉。  
2. 去掉了“分布式部署与容量治理”段落，防止越界到 `ch16`。  
3. 将“效果可接受”改为 `P95`、越界数、样例命中率等可验证指标。
