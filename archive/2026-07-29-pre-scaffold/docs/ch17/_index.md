---
title: "17. 言出法随：函数、触发器与存储过程"
weight: 1700
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
承接 `ch16` 已定义的 `risk_*` 接口契约，本章把函数、触发器、存储过程落地为可验收实现，并明确“该进库/不该进库”的收益与风险边界。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 执行 `psql -f sql/ch17/01_contract_check.sql` 成功，`risk_eval` 函数、`risk_guard_trg` 触发器、`risk_apply` 存储过程均存在且可调用。  
2. 执行 `psql -f sql/ch17/02_function_tests.sql`，固定 20 条样例判定结果与期望一致，准确率 `100%`。  
3. 执行 `psql -f sql/ch17/03_trigger_tests.sql`，违规写入被拦截率 `100%`，合法写入成功率 `100%`。  
4. 执行 `psql -f sql/ch17/05_security_tests.sql`，应用角色可执行、只读角色不可执行，权限检查全部 `PASS`。  
5. 执行 `psql -f sql/ch17/06_regression.sql`，核心写入链路 `P95` 相比 `ch16` 基线回退不超过 `15%`。  

## 3) 章节边界
本章要讲什么（5-7 条）
1. 从 `ch16` 契约出发，明确函数、触发器、存储过程的职责分工。  
2. 用函数实现“纯计算判定”，避免副作用。  
3. 用触发器在写入口做强约束，保证规则不被绕过。  
4. 用存储过程封装多步数据库内编排与失败回滚。  
5. 建立执行权限与身份边界（谁能调、以谁身份调）。  
6. 用回归与性能基线验证收益，识别风险。  
7. 固化“进库/留应用层”清单，作为 `ch18` 平台化输入。  

本章明确不讲什么（3-5 条）
1. 不讲将全部业务逻辑下沉数据库。  
2. 不讲跨数据库中间件选型大全。  
3. 不讲运维侧高可用、容灾、故障处置细节。  
4. 不讲复杂工作流编排引擎的实现。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 同卡短时异地风控（承接 `ch16`）。  
支线案例：风控审计日志自动记录（仅用于权限与回滚演练）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 17.1 | 先定分工：契约到实现 | 三类数据库对象各做什么、不做什么 | 接口契约、函数、存储过程 | `psql -f sql/ch17/01_contract_check.sql`，填写 `docs/ch17/boundary_sheet.md` | `docs/ch17/boundary_sheet.md` | S |
| 17.2 | 函数落地：只做判定 | 如何把风控规则写成可复用且可测的纯计算 | 函数、幂等、异常处理 | `psql -f sql/ch17/02_function_impl.sql && psql -f sql/ch17/02_function_tests.sql` | `sql/ch17/risk_eval.sql`、`artifacts/ch17/function_test_report.md` | S |
| 17.3 | 触发器落地：把住写入口 | 如何保证违规数据无法绕过应用直写入库 | 触发时机、触发粒度、事务边界 | `psql -f sql/ch17/03_trigger_impl.sql && psql -f sql/ch17/03_trigger_tests.sql` | `sql/ch17/risk_guard_trigger.sql`、`artifacts/ch17/trigger_test_report.md` | S |
| 17.4 | 存储过程落地：多步编排 | 多步写入与日志记录如何一起成功或一起失败 | 存储过程、事务边界、异常处理 | `psql -f sql/ch17/04_procedure_impl.sql && psql -f sql/ch17/04_procedure_tests.sql` | `sql/ch17/risk_apply.sql`、`artifacts/ch17/procedure_test_report.md` | A |
| 17.5 | 安全边界：执行身份与权限 | 过程和函数应以谁身份执行，如何避免越权 | `SECURITY DEFINER`、`search_path`、最小权限 | `psql -f sql/ch17/05_security.sql && psql -f sql/ch17/05_security_tests.sql` | `docs/ch17/permission_matrix.md`、`artifacts/ch17/security_report.md` | S |
| 17.6 | 验收闭环：正确且不退化 | 逻辑正确后，性能是否可接受 | 回归测试、可观测性、性能基线 | `psql -f sql/ch17/06_regression.sql` | `artifacts/ch17/regression_report.md` | A |
| 17.7 | 边界落锤：交付平台化输入 | 哪些逻辑继续留库内，哪些上收平台层 | 收益/风险边界、接口版本、交付清单 | `psql -f sql/ch17/07_acceptance.sql`，更新 `docs/ch17/ch18_handoff.md` | `docs/ch17/ch18_handoff.md`、`artifacts/ch17/acceptance_report.md` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：基于主线案例完成函数与触发器最小闭环，做到“可判定、可拦截”。  
前置条件：已完成 `ch16`，`risk_*` 契约对象已创建，具备测试样例数据。  
步骤：  
1. 执行 `01_contract_check.sql`，确认契约对象齐全。  
2. 执行 `02_function_impl.sql` 与 `02_function_tests.sql`，完成并验证 `risk_eval`。  
3. 执行 `03_trigger_impl.sql` 与 `03_trigger_tests.sql`，把规则挂到写入口。  
4. 导出测试结果到 `artifacts/ch17/function_test_report.md` 与 `artifacts/ch17/trigger_test_report.md`。  
验收标准：  
1. `risk_eval` 判定样例准确率 `100%`。  
2. 违规写入拦截率 `100%`，合法写入成功率 `100%`。  
3. 触发器绕过测试（直接写表）失败，说明保护生效。  

实验 B（进阶）  
目标：加入存储过程编排与权限边界，完成性能回归验收。  
前置条件：实验 A 通过；具备应用角色与只读角色。  
步骤：  
1. 执行 `04_procedure_impl.sql` 与 `04_procedure_tests.sql`，验证成功/失败回滚路径。  
2. 执行 `05_security.sql` 与 `05_security_tests.sql`，完成角色授权与拒绝测试。  
3. 执行 `06_regression.sql`，对比 `ch16` 基线。  
4. 执行 `07_acceptance.sql`，生成最终验收与 `ch18` 交付清单。  
验收标准：  
1. 过程调用成功路径与回滚路径都可复现，结果与预期一致。  
2. 权限测试全部 `PASS`：应用角色可调、只读角色不可调。  
3. 核心写入链路 `P95` 回退 `<= 15%`。  
4. `ch18_handoff.md` 含接口版本、权限模型、验收脚本入口。  

## 6) 常见误区与纠偏（5 条）
1. 误区：函数里顺手写日志。纠偏：函数保持纯计算，副作用放触发器或存储过程。  
2. 误区：触发器“能写就行”。纠偏：先定触发时机与粒度，再上线。  
3. 误区：存储过程就是万能业务层。纠偏：只封装数据库内强一致步骤。  
4. 误区：`SECURITY DEFINER` 默认安全。纠偏：固定 `search_path`，并配最小权限。  
5. 误区：只看功能通过。纠偏：功能、权限、性能三类验收必须同时通过。  

## 7) 与前后章衔接
承接 ch16（2-3 条）
1. 直接复用 `ch16` 的 `risk_*` 接口命名与样例数据，不重做模型。  
2. 复用 `ch16` 的性能基线口径（`P95`）作为本章回归标准。  
3. 复用 `ch16` 的“边界先行”原则，先定职责再写实现。  

交付给 ch18（2-3 条）
1. 交付稳定接口版本与错误语义，作为平台化统一接入面。  
2. 交付权限矩阵与执行身份规则，作为平台权限治理输入。  
3. 交付自动化验收脚本入口，供 `ch18` 纳入标准发布流水线。  

## 8) 自检与修正
先给出自检清单（8 项）
1. 仅处理 `ch17`，未扩写其他章节正文。  
2. 章节名与编号保持不变。  
3. 总节数为 `7`，满足 `6-8` 节要求。  
4. 每节必讲概念不超过 `3` 个。  
5. 每节都给出可执行动作。  
6. 案例数量符合“1 主线 + 1 支线”上限。  
7. 学习目标与实验验收均可量化、可复验。  
8. 新术语控制在 `12` 个以内。  

再给出本次细纲中你主动修正的 3 处问题
1. 把“触发器自动写外部通知”从主线移除，避免越界成平台/中间件话题。  
2. 把早稿中的两个支线案例合并为一个，避免学习路径分叉。  
3. 把“效果更好”类表述改成准确率、拦截率、`P95` 回退等硬指标。
