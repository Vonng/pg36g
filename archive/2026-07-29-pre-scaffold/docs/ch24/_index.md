---
title: "24. 纲举目张：SLA、SOP 与组织治理"
weight: 2400
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
把 `ch23` 的安全控制结果升级为可执行的服务治理体系：用 `SLA/SLO` 约定目标，用 `SOP` 固化动作，用组织协作机制保证持续执行，并产出可直接接入 `ch25` 的监控需求输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 产出 `docs/ch24/01_sla_draft.yaml`，至少包含 `payment-service`（主线）与 `report-service`（支线）两类服务承诺，字段完整率 `100%`（`service/tier/availability_target/change_window/owner`）。  
2. 产出 `docs/ch24/02_sli_catalog.yaml`，至少定义 `3` 个 `SLI`（可用性、延迟、错误率），每个都包含 `name/formula/source/window/target/owner`。  
3. 产出 `docs/ch24/sop/` 下 `3` 份最小 `SOP`（日检、变更、故障），每份都含 `触发条件/步骤/回滚点/记录项/责任人`。  
4. 产出 `docs/ch24/05_raci_matrix.csv` 与 `docs/ch24/05_oncall_roster.md`，覆盖 `4` 个角色（DBA、开发、值班经理、业务负责人）并明确升级时限。  
5. 产出 `docs/ch24/ch25_input.yaml`，通过章节验收检查（关键布尔项全为 `true`），可直接作为 `ch25` 监控实施输入。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 如何从 `ch23` 安全交付物抽取治理对象与责任边界。  
2. 如何给服务分级并形成可落地 `SLA` 草案。  
3. 如何定义 `SLO/SLI` 与统计口径，避免“只写目标不算数”。  
4. 如何用错误预算与例外机制处理“目标达不成”场景。  
5. 如何设计最小可执行 `SOP`，保证值班时按步骤操作。  
6. 如何建立 `RACI`、值班轮值与升级路径，形成组织协作闭环。  
7. 如何把本章产出结构化交付给 `ch25` 监控体系。  

- 本章明确不讲什么（3-5 条）
1. 不讲数据库参数调优清单与性能调参细节。  
2. 不讲监控平台部署与可视化实现细节（留给 `ch25`）。  
3. 不讲故障切换与集群重建操作细节（留给 `ch33`）。  
4. 不做工具大全、制度大全、模板大全式堆砌。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service / paydb`（交易核心库）  
支线案例：`report-service / reportdb`（报表只读库）

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 24.1 | 承接 ch23：治理对象盘点 | 安全措施有了，但谁负责、管什么还不清楚 | SLA、SOP、例外单 | 命令：`yq e '.security_slo,.sop_checks,.exception_list,.evidence_refs' docs/ch23/ch24_input.yaml`；检查项：补齐服务、责任人、边界 | `docs/ch24/00_governance_scope.yaml` | S |
| 24.2 | 服务分级与 SLA 草案 | 业务预期与运维承诺不一致 | 服务分级、SLA、变更窗口 | 检查项：按“核心/非核心”分级并填目标；命令：`yq e '.services[] | [.service,.tier,.availability_target,.change_window,.owner] | @csv' docs/ch24/01_sla_draft.yaml` | `docs/ch24/01_sla_draft.yaml` | S |
| 24.3 | SLO/SLI 与统计口径 | 目标写了但无法量化验证 | SLO、SLI、统计窗口 | SQL：`psql -X -d postgres -c "select datname,numbackends,xact_commit+xact_rollback as tx_total from pg_stat_database where datname='paydb';"`；检查项：为 3 个 SLI 填公式与数据源 | `docs/ch24/02_sli_catalog.yaml` | S |
| 24.4 | 错误预算与例外机制 | 指标超标后没有统一决策方式 | 错误预算、例外单、升级路径 | 演练：模拟 20 分钟服务降级，计算预算消耗并触发例外审批；检查项：是否有到期时间与责任人 | `docs/ch24/03_error_budget.md`、`docs/ch24/03_exception_ticket.yaml` | A |
| 24.5 | SOP 最小集合落地 | 值班靠经验，动作不一致 | SOP、回滚点、记录项 | 演练：按“变更 SOP”走一遍干跑；检查项：步骤可执行、失败可回滚、记录可追溯 | `docs/ch24/sop/01_daily_check.md`、`docs/ch24/sop/02_change.md`、`docs/ch24/sop/03_incident.md` | S |
| 24.6 | 组织协作治理：RACI 与轮值 | 故障时多人在场但无人负责 | RACI、值班轮值、升级路径 | 演练：30 分钟桌面演练，按 T+5/T+15/T+30 完成分工与升级 | `docs/ch24/05_raci_matrix.csv`、`docs/ch24/05_oncall_roster.md`、`artifacts/ch24/05_drill_log.md` | A |
| 24.7 | 章节验收与交付 ch25 | 治理文档未转成监控实施输入 | 验收门禁、监控需求、交付清单 | 命令：`yq e '.slis[] | has("name") and has("formula") and has("source") and has("window") and has("target") and has("owner")' docs/ch24/02_sli_catalog.yaml`；检查项：不通过即不交付 | `docs/ch24/ch25_input.yaml`、`artifacts/ch24/99_acceptance_report.md` | B |

## 5) 实战实验设计
- 实验 A（基础）
目标：完成一套最小治理闭环（`SLA/SLO + 3 份 SOP + RACI`）。  
前置条件：`docs/ch23/ch24_input.yaml` 已存在；近 7 天运行记录可访问；主线服务可读写验证。  
步骤：  
1. 执行 `24.1`，生成治理对象清单。  
2. 执行 `24.2`，完成服务分级与 `SLA` 草案。  
3. 执行 `24.3`，定义并落地 3 个 `SLI`。  
4. 执行 `24.5`，产出并干跑 3 份 `SOP`。  
5. 执行 `24.6`，完成一次组织协作桌面演练。  
验收标准：  
1. `01_sla_draft.yaml` 至少 2 个服务、5 个必填字段齐全。  
2. `02_sli_catalog.yaml` 至少 3 个 `SLI` 且必填字段齐全。  
3. `sop/` 下恰好 3 份文档，且每份都有回滚点。  
4. `05_raci_matrix.csv` 覆盖 4 角色，升级时限明确。  
5. 形成 `artifacts/ch24/05_drill_log.md`，记录时间线完整。  

- 实验 B（进阶）
目标：在“安全事件引发可用性波动”场景下，跑通错误预算决策与跨团队协作，并输出 `ch25` 输入。  
前置条件：实验 A 通过；主线与支线责任人已确认；值班轮值表生效。  
步骤：  
1. 注入场景：模拟证书更新失误导致连接间歇失败。  
2. 按故障 `SOP` 执行定位、止损、升级。  
3. 计算错误预算消耗并决定是否冻结变更。  
4. 生成例外单（含到期时间、补救动作、责任人）。  
5. 输出监控需求清单并写入 `ch25_input.yaml`。  
验收标准：  
1. 事件分级与责任人确认时间 `<=10` 分钟。  
2. 例外单创建并审批完成时间 `<=30` 分钟。  
3. 错误预算计算结果与场景损失一致（偏差 `0`）。  
4. 演练日志包含决策点、执行人、时间戳三要素。  
5. `ch25_input.yaml` 至少包含 `5` 条监控需求（指标+阈值+责任人）。  

## 6) 常见误区与纠偏（5 条）
1. 误区：`SLA` 只写口号。纠偏：必须绑定数值目标、统计窗口、责任人。  
2. 误区：`SLO` 直接照抄行业默认值。纠偏：先采样基线，再定目标。  
3. 误区：`SOP` 写成“知识文档”。纠偏：改成值班可直接执行的步骤清单。  
4. 误区：故障只看技术动作。纠偏：同步明确 `RACI` 与升级时限。  
5. 误区：指标超标后继续照常发布。纠偏：用错误预算驱动“冻结/放行”决策。  

## 7) 与前后章衔接
- 承接 ch23（2-3 条）
1. 直接消费 `docs/ch23/ch24_input.yaml` 中的 `security_slo/sop_checks/exception_list/evidence_refs`。  
2. 将 `ch23` 的审计证据要求纳入本章 `SOP` 记录项与验收门禁。  
3. 将最小权限与账号变更要求纳入“变更 SOP”的必检项。  

- 交付给 ch25（2-3 条）
1. 交付 `02_sli_catalog.yaml` 作为监控指标与采集口径源。  
2. 交付错误预算阈值与升级路径，作为告警分级输入。  
3. 交付 `ch25_input.yaml`（指标、阈值、窗口、责任人），用于监控落地。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch24`，未扩写其他章节正文。  
2. 保持章节编号与标题不变：`24. 纲举目张：SLA、SOP 与组织治理`。  
3. 细纲为 `7` 节，满足 `6-8` 节约束。  
4. 每节关键概念均 `<=3`。  
5. 每节都包含可执行动作（命令/SQL/检查项/演练）。  
6. 案例数量符合：`1` 主线 + `1` 支线。  
7. 验收标准均可量化、可复验。  
8. 新术语首次引入控制在 `11` 个：`SLA`、`SLO`、`SLI`、错误预算、`SOP`、`RACI`、值班轮值、升级路径、变更窗口、例外单、验收门禁。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了参数调优与工具比较内容，避免偏离治理主线。  
2. 把原先分散案例收敛为“支付主线 + 报表支线”，降低学习分叉。  
3. 将“原则性描述”改成“文件产出 + 命令校验 + 时间阈值”，确保可执行与可验收。
