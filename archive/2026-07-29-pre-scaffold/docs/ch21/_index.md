---
title: "21. 未雨绸缪：备份体系与恢复演练"
weight: 2100
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
在 `ch20` 已给定 `RTO/RPO` 与容灾目标的前提下，落地一套“可恢复、可演练、可验收”的备份体系，并产出 `ch22` 可直接消费的接入输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `docs/ch21/01_backup_policy.yaml`，必填字段（`full/incr/wal/retention/drill_window`）缺失数为 `0`。  
2. 主线案例完成 `1` 次全量 + `1` 次增量 + `1` 次 `WAL` 切换，`pgbackrest info` 显示最近备份状态为 `ok`。  
3. 完成一次恢复演练并输出 `artifacts/ch21/04_restore_drill.md`，含 `T0/T1`、实测 `RTO/RPO`、业务校验结果。  
4. 主线案例实测 `RTO <= docs/ch20/ch21_input.yaml` 中 `rto_target`，`RPO <= rpo_target`。  
5. 交付 `docs/ch21/ch22_input.yaml`，字段 `rw_endpoint/ro_endpoint/switch_order/max_switch_seconds` 完整率 `100%`。  

## 3) 章节边界
本章要讲什么（6 条）
1. 承接 `ch20` 目标，冻结本章恢复验收口径。  
2. 按主线/支线保护级别设计备份分层策略。  
3. 建立全量、增量、`WAL` 归档的可恢复链路。  
4. 定义备份质量门禁：成功、可读、可恢复。  
5. 设计并执行可复现的恢复演练流程。  
6. 交付恢复后服务接入所需参数给 `ch22`。  

本章明确不讲什么（4 条）
1. 不深挖高可用自动切换机制与选主算法。  
2. 不展开故障指挥、跨团队应急流程。  
3. 不做连接代理/路由实现细节（留给 `ch22`）。  
4. 不做工具横评或多工具并行方案大全。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 交易库。  
支线案例：`report-service` 报表库（低成本目标）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 21.1 | 承接 ch20：恢复口径冻结 | 目标有了，但恢复验收口径不统一 | `RTO`、`RPO`、恢复验收阈值 | `yq e '.rto_target,.rpo_target,.drill_window' docs/ch20/ch21_input.yaml` 并固化范围 | `docs/ch21/00_scope.yaml` | S |
| 21.2 | 备份策略分层设计 | 所有库一套策略，成本与风险失衡 | 备份分层、备份窗口、保留期 | 填写并校验策略：`yq e '.tiers[].full and .tiers[].incr and .tiers[].retention_days' docs/ch21/01_backup_policy.yaml` | `docs/ch21/01_backup_policy.yaml` | S |
| 21.3 | 备份链落地 | 有备份任务但无法保证可恢复 | 全量备份、增量备份、WAL归档 | `pgbackrest --stanza=<stanza> backup --type=full`；`pgbackrest --stanza=<stanza> backup --type=incr`；`psql -c "select pg_switch_wal();"` | `artifacts/ch21/02_backup_chain.log` | S |
| 21.4 | 备份质量门禁 | 只看“任务成功”，不看“能否恢复” | 恢复链、校验恢复、过期清理 | `pgbackrest --stanza=<stanza> check` 与 `pgbackrest --stanza=<stanza> expire --dry-run` | `artifacts/ch21/03_backup_gate.md` | A |
| 21.5 | 主线恢复演练流程 | 演练不可复现，结果不可量化 | 演练窗口、恢复时钟点、业务校验点 | 执行恢复 Runbook；校验：`psql -c "select pg_is_in_recovery();"`、`psql -c "select count(*) from drill_marker where drill_id='ch21-main';"` | `artifacts/ch21/04_restore_drill.md` | S |
| 21.6 | 支线低成本恢复策略 | 支线跟主线同标准导致过度投入 | 保护级别、成本上限、最小恢复要求 | 对 `report-service` 执行一次最小恢复演练并记录耗时/丢失窗口 | `docs/ch21/05_branch_policy.yaml` | A |
| 21.7 | 向 ch22 交付接入输入 | 恢复完成后接入层无明确参数 | 服务入口清单、读写角色标签、连接切换顺序 | 生成并校验：`yq e '.rw_endpoint and .ro_endpoint and .switch_order and .max_switch_seconds' docs/ch21/ch22_input.yaml` | `docs/ch21/ch22_input.yaml` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：完成主线/支线备份策略落地，并形成可恢复链。  
前置条件：`docs/ch20/ch21_input.yaml` 已存在；`pgbackrest` stanza 可用；有演练库权限。  
步骤：
1. 冻结恢复目标与演练窗口，输出 `00_scope.yaml`。  
2. 生成 `01_backup_policy.yaml`（主线与支线各一套频率与保留期）。  
3. 主线执行全量+增量备份，支线执行至少一次全量备份。  
4. 执行 `pg_switch_wal()`，确认归档链被推进。  
5. 执行 `check` 与 `expire --dry-run`，形成门禁记录。  
验收标准：
1. 策略文件必填字段完整率 `100%`。  
2. 主线存在 `full>=1`、`incr>=1`、WAL 已推进。  
3. `pgbackrest info` 最近一次状态为 `ok`。  
4. 门禁报告中无“恢复链断裂”项。  

实验 B（进阶）  
目标：完成可量化恢复演练，验证目标并交付 `ch22` 接入输入。  
前置条件：实验 A 通过；已批准演练窗口；恢复目标机可用。  
步骤：
1. 创建并持续写入 `drill_marker`（主线），记录写入时间序列。  
2. 记录 `T0`，停止主线写入并启动恢复流程。  
3. 基于最近备份+WAL 完成恢复，恢复后记录 `T1`。  
4. 执行业务校验 SQL，统计丢失窗口并计算实测 `RPO`。  
5. 计算 `RTO=T1-T0`，与目标比对并记录偏差原因。  
6. 输出 `04_restore_drill.md` 与 `ch22_input.yaml`。  
验收标准：
1. 主线 `RTO <= rto_target`。  
2. 主线 `RPO <= rpo_target`。  
3. 主线业务校验点（至少 3 项）全部通过。  
4. `ch22_input.yaml` 关键字段完整率 `100%`。  

## 6) 常见误区与纠偏（5 条）
1. 误区：有高可用就不需要备份。纠偏：高可用保可用性，备份保可恢复性，验收口径不同。  
2. 误区：备份任务成功就等于可恢复。纠偏：必须有定期校验恢复与恢复链检查。  
3. 误区：只保留全量，不管 WAL。纠偏：没有 WAL 链就无法满足较小 `RPO`。  
4. 误区：演练只看数据库能启动。纠偏：必须加业务校验点与 `RTO/RPO` 实测。  
5. 误区：恢复后接入默认可用。纠偏：必须交付读写角色标签与切换顺序给接入层。  

## 7) 与前后章衔接
承接 ch20（2-3 条）
1. 直接消费 `docs/ch20/ch21_input.yaml` 的 `RTO/RPO`、保护级别、演练窗口。  
2. 延续 ch20 的主线/支线分级，不重新定义业务优先级。  
3. 使用 ch20 的拓扑前提作为恢复演练边界，不扩展到切换机制深挖。  

交付给 ch22（2-3 条）
1. 交付 `docs/ch21/ch22_input.yaml`：`rw_endpoint/ro_endpoint/switch_order/max_switch_seconds`。  
2. 交付 `artifacts/ch21/04_restore_drill.md`：恢复后可接入时间点与验证证据。  
3. 交付主线/支线接入差异约束（读写分离、允许切换时长、回切条件）。  

## 8) 自检与修正
先给出自检清单（8 项）
1. 仅处理 `ch21`，未扩写其他章节正文。  
2. 章节编号与标题保持不变。  
3. 细纲共 `7` 节，满足 `6-8` 节约束。  
4. 每节必讲概念不超过 `3` 个。  
5. 每节都提供了可执行动作（命令/SQL/检查/演练步骤）。  
6. 案例数量为 `1` 主线 + `1` 支线。  
7. 学习完成标准与实验验收均为可量化、可复验。  
8. 新术语首次引入控制在 `12` 个以内（本稿 12 个：备份分层、备份窗口、全量备份、增量备份、WAL归档、保留期、恢复链、校验恢复、演练窗口、恢复验收阈值、读写角色标签、连接切换顺序）。  

再给出本次细纲中你主动修正的 3 处问题
1. 删除了“高可用切换机制细节”段落，避免与本章边界冲突。  
2. 将原本多工具并列方案收敛为单链路落地，避免“工具大全化”。  
3. 把原先两条支线案例合并为一条，确保学习路径不分叉。
