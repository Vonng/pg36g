---
title: "22. 四通八达：服务接入与连接路由"
weight: 2200
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
在 `ch21` 已验证“可恢复”的前提下，本章把数据库做成“可稳定接入、可路由、可切换”的统一入口，并为 `ch23` 提供可落地的入口清单与连接基线。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 生成 `docs/ch22/00_access_scope.yaml`，且 `rw_endpoint/ro_endpoint/switch_order/max_switch_seconds` 字段完整率为 `100%`。  
2. 通过 SQL 验证：`RW` 入口 `pg_is_in_recovery = f`，`RO` 入口 `pg_is_in_recovery = t`。  
3. 在压测窗口内（如 `pgbench -T 300`），主线服务失败事务率 `<= 1%`，数据库连接峰值 `<= 连接预算`。  
4. 完成一次计划内切换演练，写流量中断时间 `<= max_switch_seconds`。  
5. 交付 `docs/ch22/ch23_input.yaml`，字段 `endpoints/route_rules/client_groups/timeout_profile` 完整率 `100%`。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 承接 `ch21` 交付，冻结服务接入目标与切换窗口。  
2. 建立统一 `RW/RO` 接入端点，避免应用直连节点。  
3. 落地最小可用路由规则（读写分离、会话亲和、回切顺序）。  
4. 建立连接池与连接预算，控制连接数与突发冲击。  
5. 设定连接超时与重试退避，避免故障期“卡死”。  
6. 执行接入连续性演练并形成可复验证据。  
7. 向 `ch23` 交付入口清单与客户端分组输入。  

- 本章明确不讲什么（3-5 条）
1. 不展开认证、授权、加密、审计策略细节（留给 `ch23`）。  
2. 不做代理/中间件工具横评与“全家桶”对比。  
3. 不讨论组织治理、值班流程、SLA 制度化（留给 `ch24`）。  
4. 不深挖内核网络栈与协议实现原理。  

## 4) 结构化细纲（6-8 节）
主线案例：`payment-service` 交易库。  
支线案例：`report-service` 报表只读库（低成本接入）。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 22.1 | 承接 ch21：冻结接入输入 | 恢复完成后接入参数分散、口径不一 | 接入端点、故障切换窗口、连接预算 | `yq e '.rw_endpoint,.ro_endpoint,.switch_order,.max_switch_seconds' docs/ch21/ch22_input.yaml` | `docs/ch22/00_access_scope.yaml` | S |
| 22.2 | 先可用：统一 RW/RO 入口发布 | 应用直连节点导致漂移与不可控切换 | 连接路由、健康检查、读写分离 | `pg_isready -h db-rw.service -p 5432`；`pg_isready -h db-ro.service -p 5432` | `docs/ch22/01_endpoint_plan.yaml` | S |
| 22.3 | 路由规则最小集 | 读写流量错路由，切换后行为不一致 | 读写分离、会话亲和、回切 | `psql "$RW_DSN" -c "select pg_is_in_recovery();"`；`psql "$RO_DSN" -c "select pg_is_in_recovery();"`；`psql "$RO_DSN" -c "create table t_err(i int);"`（应失败） | `docs/ch22/02_route_policy.yaml` | S |
| 22.4 | 连接池与连接预算落地 | 主线/支线连接争抢，触发连接风暴 | 连接池、连接预算、客户端分组 | `psql "$POOL_ADMIN_DSN" -c "show pools;"`；`psql "$RW_DSN" -c "select count(*) from pg_stat_activity;"` | `docs/ch22/03_pool_budget.yaml` | S |
| 22.5 | 超时与重试退避基线 | 故障期请求长时间悬挂、放大故障 | 连接超时、重试退避、健康检查 | `psql "$RW_DSN" -c "show statement_timeout; show lock_timeout;"`；`pgbench -n -c 20 -T 60 "$RW_DSN"` | `artifacts/ch22/04_timeout_retry.md` | A |
| 22.6 | 切换演练：连接连续性验证 | 切换时业务中断时长不可控 | 故障切换窗口、回切、连接路由 | 连续探测：`while true; do psql "$RW_DSN" -Atc "select now(),inet_server_addr(),pg_is_in_recovery()"; sleep 1; done`；执行一次主从切换并记录 `T0/T1` | `artifacts/ch22/05_failover_drill.md` | S |
| 22.7 | 章节验收与对 ch23 交付 | 无法把接入成果转为后续安全输入 | 接入端点、客户端分组、验收基线 | `yq e '.endpoints,.route_rules,.client_groups,.timeout_profile' docs/ch22/ch23_input.yaml` | `docs/ch22/ch23_input.yaml` | B |

## 5) 实战实验设计
实验 A（基础）  
目标：完成统一接入端点、读写路由、连接预算三件套。  
前置条件：`docs/ch21/ch22_input.yaml` 已存在；至少 `1` 主 `1` 从；`psql/pg_isready` 可用。  
步骤：
1. 读取并固化接入输入，生成 `docs/ch22/00_access_scope.yaml`。  
2. 发布 `db-rw.service` 与 `db-ro.service` 两个入口并做健康检查。  
3. 用 `pg_is_in_recovery()` 验证读写路由正确性。  
4. 配置主线与支线连接预算并记录池状态。  
5. 运行短压测并采集失败率与连接峰值。  
验收标准：
1. `RW/RO` 路由验证全部通过。  
2. 压测失败事务率 `<= 1%`。  
3. 数据库连接峰值 `<= 预算上限`。  
4. 形成 `01_endpoint_plan.yaml`、`02_route_policy.yaml`、`03_pool_budget.yaml`。  

实验 B（进阶）  
目标：验证切换期间连接连续性与回切可控性。  
前置条件：实验 A 通过；已批准演练窗口；具备一次计划内切换能力。  
步骤：
1. 启动持续读写探测，按秒记录连接命中节点与成功率。  
2. 记录 `T0`，执行一次主从切换。  
3. 记录 `T1`，统计写请求中断窗口。  
4. 执行回切并复测 `RW/RO` 路由正确性。  
5. 输出演练报告与 `ch23` 交付文件。  
验收标准：
1. 写流量中断时间 `<= max_switch_seconds`。  
2. 不修改应用连接串即可恢复业务。  
3. 回切后 `RW/RO` 路由再次验证通过。  
4. `artifacts/ch22/05_failover_drill.md` 含 `T0/T1/中断时长/失败率` 四项证据。  

## 6) 常见误区与纠偏（5 条）
1. 误区：应用直连数据库节点更简单。纠偏：统一接入端点是切换与扩容的前提，禁止业务侧保存节点 IP。  
2. 误区：读写分离只靠开发约定。纠偏：必须用入口与路由规则强约束，并用 SQL 验证。  
3. 误区：连接池越大越稳。纠偏：池过大只会挤爆后端，先定连接预算再配池。  
4. 误区：超时越长越安全。纠偏：故障期应“失败快返”，配合重试退避。  
5. 误区：切换演练看端口通就算通过。纠偏：必须看事务成功率与中断时长。  

## 7) 与前后章衔接
- 承接 ch21（2-3 条）
1. 直接消费 `docs/ch21/ch22_input.yaml` 的入口与切换窗口，不重复定义恢复目标。  
2. 以 `ch21` 演练结果作为本章接入连续性基线。  
3. 默认“可恢复”已成立，本章只解决“如何稳定接入与路由”。  

- 交付给 ch23（2-3 条）
1. 交付 `docs/ch22/ch23_input.yaml`：`endpoints/route_rules/client_groups/timeout_profile`。  
2. 交付切换演练证据，明确哪些入口需要优先纳入认证与权限策略。  
3. 冻结客户端分组与入口边界，供 `ch23` 直接套用认证授权设计。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch22`，未扩写其他章节正文。  
2. 章节编号与标题保持不变。  
3. 细纲节数为 `7`，满足 `6-8` 约束。  
4. 每节关键概念不超过 `3` 个。  
5. 每节都给了可执行动作（命令/SQL/检查/演练）。  
6. 案例数量为 `1` 主线 + `1` 支线。  
7. 学习标准与实验验收均可量化、可复验。  
8. 新术语首次引入控制在 `12` 个以内（本稿 11 个：接入端点、连接路由、读写分离、健康检查、会话亲和、连接池、连接预算、连接超时、重试退避、故障切换窗口、回切）。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 去掉了认证/加密/审计内容，避免提前侵入 `ch23`。  
2. 把原先“多路由模式并列讲解”收敛为“最小可用路由规则”，避免概念堆叠。  
3. 将多支线方案收敛为单一支线（`report-service`），保证学习路径不分叉。
