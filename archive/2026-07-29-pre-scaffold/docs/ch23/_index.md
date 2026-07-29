---
title: "23. 固若金汤：认证授权与数据安全"
weight: 2300
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
在 `ch22` 已完成统一接入与路由的基础上，本章把“谁能连、能做什么、做了什么、数据是否被保护”落成可验证的安全控制基线，并产出可交给 `ch24` 的制度化输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `docs/ch23/00_security_scope.yaml`，`endpoints/client_groups/roles` 字段完整率为 `100%`。  
2. 认证基线通过：非白名单来源连接被拒绝；共享账号数量为 `0`；`password_encryption` 为启用状态。  
3. 授权基线通过：登录角色直接对象授权数为 `0`（仅通过角色继承权限）；`app_ro` 写操作失败率为 `100%`。  
4. 数据安全通过：两租户交叉查询泄露行数为 `0`；脱敏视图不出现明文敏感列。  
5. 审计与加密通过：登录成功/失败、DDL、GRANT 四类事件均可检索；TLS 连接验证通过；完成一次密钥轮换且旧凭据失效、新凭据可用。  

## 3) 章节边界
本章要讲什么（6 条）  
1. 承接 `ch22` 交付的 `endpoints/client_groups/route_rules`，建立安全对象清单。  
2. 认证落地：账号生命周期、入口规则、口令策略。  
3. 授权落地：角色分层与最小权限。  
4. 数据安全控制：行级安全（RLS）与列级脱敏。  
5. 审计落地：关键事件可追溯与证据留存。  
6. 加密与密钥轮换：传输加密、静态加密、轮换演练。  

本章明确不讲什么（4 条）  
1. 不讲容量压测模型与性能调参方法。  
2. 不讲故障恢复/PITR/集群重建实施细节。  
3. 不做安全工具大全或产品横评。  
4. 不展开法规条文逐条解读与法务流程。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 交易库（`app_rw/app_ro`，多租户表）。  
支线案例：`report-service` 报表只读账号（`report_ro`）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 23.1 | 承接 ch22：安全对象清单落地 | 已有接入端点，但未映射到认证/授权对象 | 认证、授权、角色 | `yq e '.endpoints,.client_groups,.route_rules' docs/ch22/ch23_input.yaml`，整理主线/支线账号与权限边界 | `docs/ch23/00_security_scope.yaml` | S |
| 23.2 | 认证基线：账号与入口规则 | 共享账号、弱口令、入口规则漂移 | 认证、角色、最小权限 | `psql -X -c "show password_encryption;"`；`psql -X -c "select line_number,type,database,user_name,address,auth_method,error from pg_hba_file_rules order by line_number;"`；执行 `01_auth_baseline.sql` | `docs/ch23/sql/01_auth_baseline.sql`、`docs/ch23/01_hba_baseline.conf` | S |
| 23.3 | 授权基线：角色分层与最小权限 | 直接给登录账号授权，权限不可控 | 授权、角色、最小权限 | 执行 `02_role_grant.sql`；`psql -X -c "select grantee,table_schema,table_name,privilege_type from information_schema.table_privileges where table_schema='app' order by 1,2,3;"` 校验只经角色授权 | `docs/ch23/02_access_matrix.csv` | S |
| 23.4 | 数据安全：RLS + 脱敏视图 | 多租户与敏感字段存在越权读取风险 | 行级安全（RLS）、列级脱敏、最小权限 | 执行 `03_data_guard.sql`（启用 RLS、创建策略、创建脱敏视图）；用 `APP_A_DSN/APP_B_DSN` 交叉查询验证隔离与脱敏 | `docs/ch23/sql/03_data_guard.sql`、`artifacts/ch23/03_data_guard_check.md` | S |
| 23.5 | 审计闭环：关键事件可追溯 | 发生越权后无证据链 | 审计日志、认证、授权 | `psql -X -c "show log_connections; show log_disconnections; show log_statement; show log_line_prefix;"`；执行一次失败登录、一次 DDL、一次 GRANT，并 `rg` 日志取证 | `artifacts/ch23/04_audit_evidence.md` | S |
| 23.6 | 加密与密钥轮换演练 | 传输明文或长期不换密钥导致暴露面扩大 | 传输加密、静态加密、密钥轮换 | `psql -X -c "show ssl;"`；`psql "sslmode=require ..." -X -c "select ssl,version,cipher from pg_stat_ssl where pid=pg_backend_pid();"`；轮换 `app_rw` 凭据并验证旧失败新成功 | `docs/ch23/05_crypto_rotation_runbook.md` | A |
| 23.7 | 章节验收与交付 ch24 | 技术控制未转化为治理输入 | 例外清单、审计日志、最小权限 | 执行 `99_acceptance_check.sql`；`yq e '.security_slo,.sop_checks,.exception_list,.evidence_refs' docs/ch23/ch24_input.yaml` | `docs/ch23/ch24_input.yaml`、`artifacts/ch23/99_acceptance_report.md` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：在主线案例完成“认证 + 授权 + 数据安全”最小闭环。  
前置条件：`docs/ch22/ch23_input.yaml` 已存在；有 `app` schema；准备两租户测试数据；可访问 `RW/RO` 入口。  
步骤：  
1. 从 `ch22` 输入生成 `00_security_scope.yaml`。  
2. 执行认证基线脚本，收敛账号与入口规则。  
3. 执行角色授权脚本，建立 `app_rw/app_ro/report_ro` 权限。  
4. 启用 RLS 与脱敏视图。  
5. 用主线与支线账号执行读写/越权测试。  
验收标准：  
1. 非白名单连接拒绝，白名单连接通过。  
2. `app_ro` 对业务表写入全部失败。  
3. 两租户交叉读取返回 `0` 行。  
4. 脱敏视图不出现明文敏感字段。  
5. 形成 `01_auth_baseline.sql`、`02_access_matrix.csv`、`03_data_guard_check.md`。  

实验 B（进阶）  
目标：完成一次“凭据泄露假设”下的审计追踪与密钥轮换演练。  
前置条件：实验 A 通过；有演练窗口；日志可检索。  
步骤：  
1. 模拟一次失败登录与一次越权操作尝试。  
2. 检索审计日志，定位用户、时间、动作。  
3. 执行凭据轮换（至少 `app_rw`），旧凭据置失效。  
4. 回归验证：应用连通、权限仍符合最小权限。  
5. 更新例外清单并输出交付文件。  
验收标准：  
1. 四类事件（登录成功/失败、DDL、GRANT）均可检索到。  
2. 轮换完成时长 `<= 15` 分钟。  
3. 旧凭据登录失败率 `100%`，新凭据登录成功率 `100%`。  
4. 轮换后越权写入仍失败。  
5. `docs/ch23/ch24_input.yaml` 字段完整率 `100%`。  

## 6) 常见误区与纠偏（5 条）
1. 误区：有了路由入口就等于安全。纠偏：入口只解决“能连到哪”，本章必须补齐“谁能连、能做什么”。  
2. 误区：给应用一个高权限账号最省事。纠偏：登录账号不直接持有对象权限，统一走角色继承。  
3. 误区：做了授权就不需要 RLS。纠偏：授权管对象，RLS 管行，两者必须叠加。  
4. 误区：只记录错误日志就算审计。纠偏：至少覆盖登录成功/失败、DDL、GRANT，且可检索。  
5. 误区：开启加密一次就结束。纠偏：必须有可执行的密钥轮换与回归验证。  

## 7) 与前后章衔接
承接 ch22（2-3 条）  
1. 直接消费 `ch22` 的 `endpoints/client_groups/route_rules`，不重复设计接入拓扑。  
2. 以 `RW/RO` 路由边界定义认证入口与角色映射。  
3. 沿用 `ch22` 的连通性基线，仅新增安全控制验证。  

交付给 ch24（2-3 条）  
1. 交付 `docs/ch23/ch24_input.yaml`：`security_slo/sop_checks/exception_list/evidence_refs`。  
2. 交付审计证据与轮换记录，作为 `SOP` 与值班检查项输入。  
3. 交付例外清单与责任人，作为治理闭环与复盘对象。  

## 8) 自检与修正
先给出自检清单（8 项）  
1. 仅处理 `ch23`，未扩写其他章节正文。  
2. 章节编号与标题保持 `23 固若金汤：认证授权与数据安全` 不变。  
3. 细纲共 `7` 节，满足 `6-8` 节约束。  
4. 每节必讲概念不超过 `3` 个。  
5. 每节都含可执行动作（命令/SQL/检查/演练）。  
6. 案例控制为 `1` 条主线 + `1` 条支线。  
7. 学习标准与实验验收均为可量化、可复验。  
8. 新术语首次引入控制在 `11` 个：认证、授权、角色、最小权限、行级安全（RLS）、列级脱敏、审计日志、传输加密、静态加密、密钥轮换、例外清单。  

再给出本次细纲中你主动修正的 3 处问题  
1. 删除了容量压测与连接性能模型内容，避免偏离本章边界。  
2. 删除了故障恢复实施细节，只保留与安全控制直接相关的验证动作。  
3. 将原本分散的多案例收敛为单主线单支线，避免学习路径分叉。
