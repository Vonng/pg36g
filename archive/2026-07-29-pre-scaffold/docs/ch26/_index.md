---
title: "26. 胸有成竹：容量规划与压测基线"
weight: 2600
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
把 `ch25` 的观测数据转成可计算的容量模型与可复现的压测基线，明确扩容阈值，并向 `ch27` 交付可执行的调优输入。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 产出 `docs/ch26/01_capacity_model.yaml`，包含 `peak_qps/peak_conn/p95_latency/daily_growth_gb/cpu_headroom/io_headroom`，字段完整率 `100%`。  
2. 完成 `paydb` 阶梯压测（至少 `4` 档并发、每档 `>=10` 分钟），生成 `artifacts/ch26/bench_summary.csv`。  
3. 明确写出饱和点：并发提升 `20%` 时，`TPS` 增长 `<10%` 且 `P95` 上升 `>30%` 的首个档位。  
4. 产出 `docs/ch26/03_scale_threshold.yaml`，含 `warning/critical/window/owner`，并可通过 `yq e '.thresholds'` 读取。  
5. 产出 `docs/ch26/ch27_input.yaml`，至少包含 `bottleneck_rank`（前3项）与 `retest_baseline`。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 承接 `ch25` 输入，形成可用的负载画像。  
2. 建立最小容量模型（先可算、再精化）。  
3. 设计并执行压测基线（可复现）。  
4. 识别饱和点与瓶颈资源。  
5. 定义可触发的扩容阈值与检查规则。  
6. 形成章节验收门禁与交付清单。  

- 本章明确不讲什么（3-5 条）
1. 不讲参数值级别的细调方案（留给 `ch27`）。  
2. 不讲故障注入与应急响应流程（留给 `ch31/ch33`）。  
3. 不讲高可用拓扑改造与切换策略。  
4. 不做工具大全、概念大全式堆砌。  

## 4) 结构化细纲（6-8 节）

主线案例：`payment-service / paydb`  
支线案例：`report-service / reportdb`

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 26.1 | 承接 ch25：容量输入校验 | 观测数据有了，但容量输入不完整 | 负载画像、输入完整性、时间窗口 | 命令：`yq e '.capacity_inputs' docs/ch25/ch26_input.yaml`，核对 30 天峰值窗口 | `docs/ch26/00_input_check.md` | S |
| 26.2 | 最小容量模型：先算得出 | 无法把业务量映射成资源需求 | 容量模型、安全余量、资源上限 | SQL：`select datname,numbackends,xact_commit+xact_rollback as tx,blks_read,blks_hit from pg_stat_database where datname='paydb';` 并填模型模板 | `docs/ch26/01_capacity_model.yaml` | S |
| 26.3 | 压测基线设计 | 压测场景不统一，结果不可比 | 压测基线、阶梯负载、终止条件 | 命令：`pgbench -i -s 100 paydb`，制定并发档位与时长 | `docs/ch26/02_bench_plan.md` | S |
| 26.4 | 主线压测执行与采集 | 有压测但缺少可复验曲线 | 吞吐-时延曲线、饱和点、可重复性 | 命令：`for c in 50 100 150 200; do pgbench -n -r -P 10 -c $c -j 8 -T 600 paydb | tee artifacts/ch26/bench_c${c}.log; done` | `artifacts/ch26/bench_raw/*.log`、`artifacts/ch26/bench_summary.csv` | S |
| 26.5 | 支线混合负载验证 | 单场景结果无法覆盖真实争用 | 混合负载、资源争用、瓶颈资源 | 演练：在 `paydb` 压测同时执行 `reportdb` 报表查询；SQL：`select wait_event_type,wait_event,count(*) from pg_stat_activity where datname in ('paydb','reportdb') group by 1,2 order by 3 desc;` | `artifacts/ch26/mixed_load.md` | A |
| 26.6 | 扩容阈值落地 | “感觉要扩容”缺少数字触发条件 | 扩容阈值、触发窗口、安全余量 | 检查项：连续 `3` 个 `5` 分钟窗口满足 `CPU>=70%`、`P95` 超目标、`TPS` 增长停滞，即触发扩容评审 | `docs/ch26/03_scale_threshold.yaml` | S |
| 26.7 | 章节验收与交付 ch27 | 压测结论无法进入调优闭环 | 回归基线、验收门禁、调优输入 | 命令：`yq e 'has(\"bottleneck_rank\") and has(\"retest_baseline\")' docs/ch26/ch27_input.yaml` | `docs/ch26/ch27_input.yaml`、`artifacts/ch26/99_acceptance.md` | B |

## 5) 实战实验设计
- 实验 A（基础）：目标、前置条件、步骤、验收标准  
目标：完成 `paydb` 的最小容量模型与压测基线。  
前置条件：`docs/ch25/ch26_input.yaml` 已就绪；测试环境可用；`pgbench` 可执行。  
步骤：  
1. 校验 `ch25` 输入字段完整性。  
2. 初始化压测数据集并固定压测档位。  
3. 执行 `4` 档阶梯负载（每档 `>=10` 分钟）。  
4. 汇总 `TPS/P95/连接数` 曲线并识别饱和点。  
5. 生成容量模型与阈值文件。  
验收标准：  
1. `bench_raw` 日志覆盖全部档位。  
2. 饱和点按统一规则可复算。  
3. `01_capacity_model.yaml` 与 `03_scale_threshold.yaml` 字段完整率 `100%`。  

- 实验 B（进阶）：目标、前置条件、步骤、验收标准  
目标：验证混合负载下的扩容阈值，并交付 `ch27` 调优输入。  
前置条件：实验 A 通过；`reportdb` 支线查询脚本可执行。  
步骤：  
1. 将 `paydb` 负载拉到实验 A 饱和点的 `80%`。  
2. 并发执行 `reportdb` 报表查询 `20` 分钟。  
3. 记录 `paydb` 的 `TPS/P95/等待事件` 变化。  
4. 更新扩容阈值（写成具体数字与窗口）。  
5. 输出 `docs/ch26/ch27_input.yaml`。  
验收标准：  
1. 混合负载影响被量化记录（至少 `TPS` 与 `P95` 两项）。  
2. 扩容触发条件包含“指标值 + 时间窗口 + 责任人”。  
3. `ch27_input.yaml` 含前 `3` 个瓶颈项与回归基线。  

## 6) 常见误区与纠偏（5 条）
1. 误区：容量规划等于“买更大机器”。纠偏：先做模型与基线，再决定扩容方式。  
2. 误区：只跑一次压测就定结论。纠偏：至少分档执行并保留原始日志。  
3. 误区：只看 TPS 不看时延。纠偏：TPS 与 `P95` 必须同时作为判定条件。  
4. 误区：只测主链路，不测并行干扰。纠偏：必须做一次 `paydb+reportdb` 混合验证。  
5. 误区：阈值只设不复核。纠偏：每次基线更新后同步刷新阈值文件。  

## 7) 与前后章衔接
- 承接 ch25（2-3 条）
1. 直接消费 `ch25` 交付的 `peak_qps/peak_conn/p95_latency/daily_growth_gb`。  
2. 延续 `ch25` 观测窗口与指标口径，确保压测数据可对齐。  
3. 复用 `ch25` 的证据记录方式，保证容量结论可追溯。  

- 交付给 ch27（2-3 条）
1. 交付瓶颈优先级（CPU/IO/连接）与对应证据。  
2. 交付回归基线（压测档位、关键指标、阈值）。  
3. 交付调优入口清单（先调哪类参数、调后如何复测）。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch26`，未扩写其他章节正文。  
2. 未修改章节编号与标题。  
3. 结构为 `7` 节，满足 `6-8` 节约束。  
4. 每节“必讲概念”均 `<=3`。  
5. 每节都包含可执行动作（命令/SQL/检查项/演练）。  
6. 案例数量符合：`1` 主线（`paydb`）+ `1` 支线（`reportdb`）。  
7. 验收标准均为可验证、可复算的量化条件。  
8. 新术语首次引入控制在 `11` 个：负载画像、容量模型、压测基线、阶梯负载、饱和点、瓶颈资源、安全余量、扩容阈值、触发窗口、回归基线、验收门禁。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了“故障注入/应急处置”内容，避免偏离本章主题。  
2. 将原先分散的多案例收敛为“`paydb` 主线 + `reportdb` 支线”。  
3. 把“建议性表述”改成“命令/SQL + 文件产出 + 量化验收”，确保可直接写作与落地。
