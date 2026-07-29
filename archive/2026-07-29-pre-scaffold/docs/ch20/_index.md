---
title: "20. 狡兔三窟：高可用拓扑与容灾目标"
weight: 2000
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
把 `ch19` 交付的部署基线输入，收敛为可验收的高可用拓扑与 `RTO/RPO` 目标，并产出 `ch21` 可直接使用的容灾演练输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `docs/ch20/01_target_matrix.yaml`，主线与支线都包含 `protection_level/rto_target/rpo_target`，缺失字段数为 `0`。  
2. 生成 `docs/ch20/02_fault_domain.csv`，节点 `az/rack/role` 三列完整率 `100%`。  
3. 生成 `docs/ch20/03_topology_decision.md`，至少包含 `3` 个候选拓扑、`1` 个最终选择、`>=3` 条取舍理由。  
4. 执行复制状态检查 SQL 后，主线案例满足：`sync_state='sync'` 节点数 `>=1`，总备库数 `>=2`。  
5. 完成 `artifacts/ch20/04_drill_report.md`，主线演练实测 `RTO <= 300s` 且 `RPO <= 30s`，并导出 `docs/ch20/ch21_input.yaml` 字段校验通过。

## 3) 章节边界
- 本章要讲什么（6 条）
1. 接收并冻结 `docs/ch19/ch20_input.yaml` 的拓扑输入与约束。  
2. 将业务分级落成 `RTO/RPO` 与保护级别。  
3. 做故障域盘点，形成候选高可用拓扑。  
4. 给出主线与支线各自的复制模式（同步复制/异步复制）与取舍。  
5. 在演练窗口内验证拓扑是否达成目标。  
6. 交付 `ch21` 所需的恢复目标与演练清单输入。  

- 本章明确不讲什么（4 条）
1. 不讲备份介质、备份工具与备份命令细节。  
2. 不讲 PITR 操作步骤与恢复脚本实现。  
3. 不讲流量调度、连接路由与降级策略。  
4. 不展开故障处置组织流程与应急指挥细节。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 交易库（目标：同城双可用区 + 异地容灾）。  
支线案例：`report-service` 报表库（目标：低成本异步保护）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 20.1 | 承接 ch19：输入冻结与目标对齐 | 现有部署基线无法直接变成容灾目标 | 高可用拓扑、RTO、RPO | `yq e '.topology_input,.resource_budget,.rollback_point' docs/ch19/ch20_input.yaml`，补齐缺项并冻结版本 | `docs/ch20/00_scope.yaml` | S |
| 20.2 | 业务分级到保护级别 | 同一目标套所有库，导致成本或风险失衡 | 保护级别、RTO、RPO | 建立目标矩阵并校验：`yq e '.services[].protection_level and .services[].rto_target and .services[].rpo_target' docs/ch20/01_target_matrix.yaml` | `docs/ch20/01_target_matrix.yaml` | S |
| 20.3 | 故障域盘点与候选拓扑 | 拓扑图好看但扛不住真实故障 | 故障域、同城双可用区、异地容灾 | 盘点节点标签：`ansible -i infra/hosts.yml all -m debug -a 'var=hostvars[inventory_hostname].az'`，输出故障域清单 | `docs/ch20/02_fault_domain.csv` | S |
| 20.4 | 主线拓扑定稿 | 主线交易库如何在目标内达成可用性与一致性 | 同步复制、异步复制、高可用拓扑 | 校验复制状态：`psql -c "show synchronous_standby_names;"` 与 `psql -c "select application_name,sync_state from pg_stat_replication;"` | `docs/ch20/03_main_topology.md` | S |
| 20.5 | 支线拓扑定稿 | 支线如何降成本且不越过风险底线 | 保护级别、异步复制、RPO | 评估延迟：`psql -c "select application_name,pg_wal_lsn_diff(pg_current_wal_lsn(),replay_lsn) as lag_bytes from pg_stat_replication;"` 并对照支线阈值 | `docs/ch20/04_branch_topology.md` | A |
| 20.6 | 演练窗口验证目标 | 纸面目标是否可达成 | 演练窗口、RTO、RPO | 执行一次受控切换演练（记录 `T0` 故障触发时间与 `T1` 恢复可写时间），并统计标记数据丢失量 | `artifacts/ch20/04_drill_report.md` | S |
| 20.7 | 向 ch21 交付输入包 | 下一章缺少恢复演练的明确目标 | 拓扑决策表、保护级别、演练窗口 | 导出并校验：`yq e '.protection_level and .rto_target and .rpo_target and .drill_window' docs/ch20/ch21_input.yaml` | `docs/ch20/ch21_input.yaml` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：完成主线/支线的保护级别定义与拓扑定稿。  
前置条件：`docs/ch19/ch20_input.yaml` 已通过字段校验；`stg` 环境有主从节点；具备 `psql/yq/ansible`。  
步骤：  
1. 读取并冻结 ch19 输入，输出 `00_scope.yaml`。  
2. 建立服务目标矩阵，给出主线/支线 `RTO/RPO`。  
3. 盘点故障域并绘制 `>=3` 个候选拓扑。  
4. 选定主线与支线最终拓扑，记录取舍理由。  
验收标准：  
1. `01_target_matrix.yaml` 字段完整率 `100%`。  
2. 主线拓扑满足“跨 `2` 个故障域 + `1` 同步复制 + `1` 异步复制”。  
3. 支线拓扑满足“异步复制 + 低成本”，且 `RPO` 目标明确为可测数字。  
4. `03_topology_decision.md` 含候选、结论、拒绝理由三部分，均非空。  

实验 B（进阶）  
目标：通过演练实测验证主线 `RTO/RPO`，并交付 ch21 输入。  
前置条件：实验 A 通过；已批准演练窗口；有可回退点。  
步骤：  
1. 创建演练标记表并持续写入标记数据。  
2. 记录 `T0`，触发一次受控主库故障场景。  
3. 提升备库并恢复写入，记录 `T1`，计算 `RTO = T1 - T0`。  
4. 对比演练前后标记数据，计算实际 `RPO`。  
5. 输出 `04_drill_report.md` 与 `ch21_input.yaml`。  
验收标准：  
1. 主线实测 `RTO <= 300s`。  
2. 主线实测 `RPO <= 30s`。  
3. 支线实测 `RPO <= 900s`。  
4. `ch21_input.yaml` 必填字段完整率 `100%`，且包含演练窗口与阈值。  

## 6) 常见误区与纠偏（5 条）
1. 误区：把高可用拓扑等同于备份。纠偏：本章只定拓扑与 `RTO/RPO`，备份实现留给 `ch21`。  
2. 误区：所有库都追求同一 `RTO/RPO`。纠偏：先按保护级别分层，再定目标。  
3. 误区：只看架构图不看故障域。纠偏：必须先做 `az/rack/role` 盘点再选拓扑。  
4. 误区：盲目追求全同步复制。纠偏：主线用“同步+异步”组合，支线按成本用异步。  
5. 误区：没有演练只写文档。纠偏：必须在演练窗口产出可复验的 `RTO/RPO` 实测值。  

## 7) 与前后章衔接
- 承接 ch19（2-3 条）
1. 直接使用 `docs/ch19/ch20_input.yaml` 的节点池、资源预算与回退点，不重复做环境规划。  
2. 复用 ch19 的准入检查与变更窗口，作为本章演练前门禁。  
3. 以 ch19 已验证的部署基线作为拓扑选择约束。  

- 交付给 ch21（2-3 条）
1. 交付 `docs/ch20/ch21_input.yaml`：保护级别、`RTO/RPO` 目标、演练窗口、拓扑决策表。  
2. 交付 `artifacts/ch20/04_drill_report.md`：实测指标与失败场景记录，作为恢复演练基线。  
3. 交付主线/支线差异化目标，供 ch21 设计分层恢复策略与验收阈值。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch20`，未扩写其他章节正文。  
2. 章节编号与标题保持不变。  
3. 结构化细纲为 `7` 节，满足 `6-8` 节要求。  
4. 每节必讲概念均不超过 `3` 个。  
5. 每节都包含可执行动作（命令/检查/演练步骤）。  
6. 案例数量符合 `1` 主线 + `1` 支线。  
7. 学习完成标准与实验验收均为可量化指标。  
8. 首次引入术语控制在 `<=12`（本稿 11 个：高可用拓扑、RTO、RPO、故障域、同城双可用区、异地容灾、同步复制、异步复制、保护级别、演练窗口、拓扑决策表）。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了早稿中的备份命令与恢复操作，避免越界到 `ch21`。  
2. 删除了流量调度相关段落，避免提前进入 `ch34`。  
3. 将原先分散的多案例收敛为单主线+单支线，保证学习路径不分叉。
