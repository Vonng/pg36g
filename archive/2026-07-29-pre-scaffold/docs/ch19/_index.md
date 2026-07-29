---
title: "19. 开天辟地：环境规划与部署基线"
weight: 1900
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
把 `ch18` 的平台化替代结论落成“可部署、可验收、可交接”的环境分层与部署基线，为 `ch20` 的高可用拓扑设计提供输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `docs/ch19/01_scope.yaml`，`resource_profile/acceptance_gate/rollback_point` 三组字段缺失数为 `0`。  
2. 生成 `docs/ch19/02_env_matrix.yaml`，`dev/stg/prod` 三环境均包含 `owner/变更窗口/资源配额`，完整率 `100%`。  
3. 生成 `artifacts/ch19/03_resource_plan.csv`，主线库 CPU/内存/存储/连接数均给出基线值，且容量水位预留 `>=30%`。  
4. 执行准入检查命令后，强制项通过率 `100%`（例如 `18/18`）。  
5. 生成 `docs/ch19/ch20_input.yaml` 并通过字段校验：`topology_input/resource_budget/rollback_point` 全部为非空。  

## 3) 章节边界
本章要讲什么（6 条）
1. 如何接收并冻结 `ch18` 交付输入。  
2. 如何建立 `dev/stg/prod` 环境分层与命名规则。  
3. 如何做资源配额与容量水位起算。  
4. 如何定义可复用的部署基线（主机、网络、时钟、目录、参数）。  
5. 如何做部署前准入检查与最小部署演练。  
6. 如何输出 `ch20` 可直接消费的拓扑输入与交付清单。  

本章明确不讲什么（4 条）
1. 不讲故障切换、应急处置、集群重建实操。  
2. 不讲备份恢复流程细节（留给 `ch21/ch32`）。  
3. 不做参数调优深挖（留给 `ch27`）。  
4. 不做工具大全/方案大全式罗列。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 风控库，从 `ch18` 替代结论落地到三环境部署基线。  
支线案例：`report-service` 报表库，仅做资源配额对照，不进入部署演练。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 19.1 | 接棒 ch18：输入冻结 | 替代结论无法直接指导部署 | 环境分层、交付清单、回退点 | `yq e '.resource_profile,.acceptance_gate,.rollback_point' docs/ch18/ch19_input.yaml`，补全缺失项 | `docs/ch19/01_scope.yaml` | S |
| 19.2 | 三环境分层与命名基线 | 环境职责混乱，变更不可控 | 环境分层、命名规范、变更窗口 | 建立 `dev/stg/prod` 矩阵并执行字段检查：`rg -n 'owner|change_window|quota' docs/ch19/02_env_matrix.yaml` | `docs/ch19/02_env_matrix.yaml` | S |
| 19.3 | 资源配额与容量水位 | 不知道要多少资源、余量多少 | 资源配额、容量水位、增长系数 | 采样当前负载：`psql -c "select datname,numbackends,xact_commit+xact_rollback as tps from pg_stat_database;"` + 主机采样 `nproc/free -g/df -h` | `artifacts/ch19/03_resource_plan.csv` | S |
| 19.4 | 部署基线四件套 | 同一套配置在不同节点不一致 | 部署基线、准入检查、配置漂移 | 批量检查：`ansible -i infra/hosts.yml all -m shell -a 'timedatectl show -p NTPSynchronized; ulimit -n; sysctl vm.swappiness'` | `artifacts/ch19/04_baseline_check.md` | S |
| 19.5 | 清单与参数模板落地 | 规划文档不能直接执行 | 参数模板、部署清单、一致性校验 | `ansible-inventory -i infra/hosts.yml --graph`；`ansible-playbook -i infra/hosts.yml playbooks/validate.yml --check` | `infra/hosts.yml`、`infra/pg_env.yml` | A |
| 19.6 | 最小部署演练与验收门禁 | 不知道基线是否真能跑起来 | 最小可用集、准入检查、回退点 | `ansible-playbook -i infra/hosts.yml playbooks/site.yml --tags precheck,install --limit stg`；冒烟 SQL：`select 1;` | `artifacts/ch19/06_drill_report.md` | S |
| 19.7 | 交付 ch20：拓扑输入包 | 下一章缺少可直接设计 HA 的输入 | 拓扑输入、资源配额、交付清单 | 生成并校验：`yq e '.topology_input and .resource_budget and .rollback_point' docs/ch19/ch20_input.yaml` | `docs/ch19/ch20_input.yaml` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：完成主线案例的环境分层、资源规划、部署基线。  
前置条件：`docs/ch18/ch19_input.yaml` 已存在；可访问目标主机；可执行 `psql/ansible`。  
步骤：  
1. 读取并冻结 `ch18` 输入，产出 `01_scope.yaml`。  
2. 建立 `dev/stg/prod` 环境矩阵并补齐责任字段。  
3. 采样数据库与主机负载，计算资源配额与容量水位。  
4. 运行主机基线准入检查，记录不合格项。  
验收标准：  
1. `01_scope.yaml` 必填字段缺失 `0`。  
2. `02_env_matrix.yaml` 三环境字段完整率 `100%`。  
3. `03_resource_plan.csv` 主线对象覆盖率 `100%`，容量预留 `>=30%`。  
4. 基线检查强制项通过率 `100%`。  

实验 B（进阶）  
目标：完成最小部署演练并交付 `ch20` 输入包。  
前置条件：实验 A 通过；`infra/hosts.yml` 与参数模板已完成一致性检查。  
步骤：  
1. 执行部署前校验（`--check`）并修正差异。  
2. 在 `stg` 环境执行最小部署演练。  
3. 执行 6 项冒烟检查（连通、认证、建表、写入、查询、回退点记录）。  
4. 导出 `ch20_input.yaml`，填充拓扑输入与资源预算。  
5. 支线案例仅执行资源配额对照，不进入部署演练。  
验收标准：  
1. 校验任务失败数 `0`。  
2. 最小部署演练完成且强制检查项通过率 `100%`。  
3. 冒烟检查通过 `6/6`。  
4. `ch20_input.yaml` 字段校验为 `true`，并包含回退点。  

## 6) 常见误区与纠偏（5 条）
1. 误区：把环境分层当成“改名字”。纠偏：必须绑定 `owner/变更窗口/资源配额` 三要素。  
2. 误区：先上生产再补测试。纠偏：先 `stg` 最小可用集演练，通过后再进入生产变更窗口。  
3. 误区：按机器规格拍脑袋定资源。纠偏：先采样真实负载，再按容量水位倒推配额。  
4. 误区：准入检查只跑一次。纠偏：在部署前和变更前各跑一次，防止配置漂移。  
5. 误区：本章提前展开故障恢复细节。纠偏：本章只交付拓扑输入与基线，不做应急实操。  

## 7) 与前后章衔接
承接 ch18（2-3 条）
1. 直接接收 `docs/ch18/ch19_input.yaml`，不重复做平台替代决策。  
2. 使用 `ch18` 的验收门禁结果作为本章准入阈值起点。  
3. 使用 `ch18` 的回退点定义，保证部署演练可撤回。  

交付给 ch20（2-3 条）
1. 交付 `docs/ch19/ch20_input.yaml`：节点池候选、资源预算、回退点。  
2. 交付已验证的环境分层与部署基线，作为 HA 拓扑约束输入。  
3. 交付变更窗口与准入检查记录，供 `ch20` 评估容灾目标可落地性。  

## 8) 自检与修正
先给出自检清单（8 项）
1. 仅处理 `ch19`，未扩写其他章节正文。  
2. 章节编号与标题保持 `ch19 开天辟地：环境规划与部署基线` 不变。  
3. 结构化细纲为 `7` 节，满足 `6-8` 节要求。  
4. 每节必讲概念均 `<=3`。  
5. 每节都有可执行动作（命令/检查/演练步骤）。  
6. 案例数量符合 `1` 主线 + `1` 支线。  
7. 学习标准与实验验收均可量化复验。  
8. 首次引入术语控制在 `<=12`（本稿 11 个）。  

再给出本次细纲中你主动修正的 3 处问题
1. 初稿把“容灾切换步骤”写进本章，已删除并留给 `ch20/ch33`。  
2. 初稿拆成 9 节导致学习路径过碎，已收敛为 7 节并按“先做后懂”重排。  
3. 初稿术语过多，已压缩并统一为 11 个核心术语反复复用。
