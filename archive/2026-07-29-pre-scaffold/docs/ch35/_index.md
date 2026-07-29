---
title: "35. 起死回生：极限数据抢救与取证"
weight: 3500
math: true
breadcrumbs: false
---

## 1) 章节定位（一句话）
承接 `ch34` 已完成止血，本章在受控时间窗内完成数据抢救、证据封存与根因定位，并交付可直接进入 `ch36` 复盘的事实材料。

## 2) 学习完成标准（3-5 条，必须可验证）
1. 能在 `10` 分钟内读取 `docs/ch34/ch35_input.yaml` 并完成证据封存，封存清单字段完整率 `100%`。  
2. 能在 `20` 分钟内产出事故时间窗内的可疑范围（库/表/业务键/记录数），对账基线可复算。  
3. 能构建差异集并完成一次控制式修复，事故窗内“缺失数=0、重复数=0、冲突项全部有处置记录”。  
4. 能输出不少于 `8` 条带时间戳的事件时间线，每条事件都可回溯到证据文件。  
5. 能生成 `docs/ch35/ch36_input.yaml`，包含 `timeline/root_cause/rescue_actions/residual_risk/improvement_candidates`，字段完整率 `100%`。  

## 3) 章节边界
- 本章要讲什么（5-7 条）
1. 如何承接 `ch34` 交接包并先封存证据再动数据。  
2. 如何锁定事故时间窗并圈定可疑范围。  
3. 如何在影子库构建差异集，分离“缺失/重复/冲突”。  
4. 如何执行控制式修复（小批验证后全量）。  
5. 如何用日志与 `WAL` 片段补齐事件时间线。  
6. 如何给出可复现、可证伪的根因结论。  
7. 如何形成面向 `ch36` 的交接包。  

- 本章明确不讲什么（3-5 条）
1. 不讲流量调度与服务降级编排细节（已在 `ch34`）。  
2. 不讲长期平台演进路线与组织治理设计（`ch36` 主体）。  
3. 不讲工具大全、概念大全、链接大全式罗列。  
4. 不讲司法流程细节，仅覆盖工程取证与技术根因定位。  

## 4) 结构化细纲（6-8 节）
主线案例：`ch34` 止血后核心服务可用，但订单链路在事故窗出现“少单+重单”，要求 `90` 分钟内完成抢救并给出根因。  
支线案例：数据库日志缺段，需用 `WAL` 片段补齐关键事件。

| 节次 | 节标题 | 要解决的问题 | 必讲概念（<=3） | 动手任务 | 产出物 | 详略级别（S/A/B） |
|---|---|---|---|---|---|---|
| 35.1 | 接棒 ch34：先封存再处置 | 如何避免二次破坏与证据污染 | 交接包、证据封存、事故时间窗 | `test -f docs/ch34/ch35_input.yaml`；`rg -n 'incident_window\|failed_actions\|suspect_scope\|evidence_manifest' docs/ch34/ch35_input.yaml`；`mkdir -p artifacts/ch35/evidence && cp docs/ch34/ch35_input.yaml artifacts/ch35/evidence/00_input.yaml` | `artifacts/ch35/01_intake.md` | S |
| 35.2 | 划定可疑范围：从怀疑到清单 | 哪些数据需要抢救，边界在哪里 | 可疑范围、对账校验、影子库 | `psql -h <rw> -Atqc "select min(ts),max(ts),count(*) from orders where ts between '<start>' and '<end>';"`；`psql -h <rw> -c "\\copy (select id,biz_key,amount,ts from orders where ts between '<start>' and '<end>') to 'artifacts/ch35/02_orders_window.csv' csv header"` | `artifacts/ch35/02_scope.csv` | S |
| 35.3 | 构建差异集：缺失/重复/冲突 | 如何一次性找全可修复项 | 差异集、影子库、对账校验 | `psql -h <shadow> -f sql/ch35_build_diff.sql`；`psql -h <shadow> -Atqc "select diff_type,count(*) from rescue_diff group by 1 order by 1;"` | `artifacts/ch35/03_diff_summary.txt` | S |
| 35.4 | 控制式修复：先小批后全量 | 如何降低修复本身的风险 | 修复闸门、差异集、回放验证 | `psql -h <rw> -f sql/ch35_fix_batch.sql`；通过后执行 `psql -h <rw> -f sql/ch35_fix_full.sql`；`psql -h <rw> -Atqc "select missing_cnt,dup_cnt,conflict_cnt from rescue_check_result;"` | `artifacts/ch35/04_fix_log.md` | S |
| 35.5 | 取证补全：日志与 WAL 拼时间线 | 日志不全时如何还原关键事实 | 事件时间线、WAL片段、证据封存 | `rg -n "ERROR|FATAL|timeout|read only" /var/log/postgresql/*.log > artifacts/ch35/05_log_hits.txt`；`pg_waldump --start=<lsn_start> --end=<lsn_end> $PGDATA/pg_wal > artifacts/ch35/05_wal_hits.txt` | `artifacts/ch35/05_timeline.csv` | A |
| 35.6 | 根因定位：给出唯一可验证结论 | 如何从现象走到根因并排除伪因 | 根因树、回放验证、事件时间线 | `psql -h <shadow> -f sql/ch35_replay_case.sql`；按“假设-证据-结果”模板填写 `artifacts/ch35/06_rca.md` 并执行核对项 | `artifacts/ch35/06_rca.md` | A |
| 35.7 | 封板交付：移交 ch36 复盘输入 | 本章结束条件是什么，交什么 | 交接包、根因树、修复闸门 | 生成 `docs/ch35/ch36_input.yaml`；`rg -n 'timeline\|root_cause\|rescue_actions\|residual_risk\|improvement_candidates' docs/ch35/ch36_input.yaml` | `docs/ch35/ch36_input.yaml`、`artifacts/ch35/07_handover.md` | A |

## 5) 实战实验设计
- 实验 A（基础）：目标、前置条件、步骤、验收标准  
目标：完成一次“差异识别 + 控制式修复 + 复核”闭环。  
前置条件：`docs/ch34/ch35_input.yaml` 已存在；`ch34` 核心路径已稳定 `15` 分钟；可创建影子库。  
步骤：  
1. 执行 `35.1` 完成证据封存与时间窗锁定。  
2. 执行 `35.2` 产出可疑范围清单。  
3. 执行 `35.3` 生成差异集并统计三类差异。  
4. 执行 `35.4` 先小批修复，验证通过后全量修复。  
5. 输出修复前后对账结果与操作日志。  
验收标准：  
1. 证据目录内必须包含 `00_input.yaml/02_scope.csv/03_diff_summary.txt/04_fix_log.md`。  
2. 事故窗内缺失数与重复数均为 `0`。  
3. 小批修复与全量修复的切换依据有明确记录。  
4. 全流程完成时间 `<= 90` 分钟。  

- 实验 B（进阶）：目标、前置条件、步骤、验收标准  
目标：在“日志缺段”场景完成取证补全与根因定位，并交付 `ch36` 输入。  
前置条件：实验 A 通过；可访问 `pg_wal`；允许执行回放验证 SQL。  
步骤：  
1. 模拟或注入日志缺段场景。  
2. 执行 `35.5`，用日志命中与 `WAL` 片段拼接时间线。  
3. 执行 `35.6`，形成根因树并做一次回放验证。  
4. 执行 `35.7`，输出 `docs/ch35/ch36_input.yaml`。  
验收标准：  
1. 时间线事件数 `>= 8`，且每条事件有证据文件路径。  
2. 根因结论唯一，且含“触发点+影响范围+证据编号”。  
3. 回放验证结果至少复现 `1` 个关键异常。  
4. `docs/ch35/ch36_input.yaml` 字段完整率 `100%`。  

## 6) 常见误区与纠偏（5 条）
1. 误区：先改生产数据再留证据。纠偏：先封存证据，后执行任何修复。  
2. 误区：不设事故时间窗，全库盲查。纠偏：先锁窗，再按业务键缩小范围。  
3. 误区：直接全量修复。纠偏：必须先小批验证，达闸门再放大全量。  
4. 误区：只有日志截图，没有可复算证据。纠偏：每个结论都绑定 SQL 结果或文件路径。  
5. 误区：根因写成“可能有多个”。纠偏：输出唯一主因，其他作为已排除假设记录。  

## 7) 与前后章衔接
- 承接 ch34（2-3 条）
1. 直接消费 `docs/ch34/ch35_input.yaml` 的 `incident_window/failed_actions/suspect_scope/evidence_manifest`。  
2. 默认前提是 `ch34` 已完成止血且核心服务稳定，本章不再讨论流量策略。  
3. 以 `ch34` 未解决的数据异常作为本章抢救入口，不重复切换与降级动作。  

- 交付给 ch36（2-3 条）
1. 交付可验证的事件时间线与唯一根因结论。  
2. 交付“已完成修复动作 + 残余风险量化”清单。  
3. 交付 `docs/ch35/ch36_input.yaml`，供 `ch36` 直接开展复盘改进与演进决策。  

## 8) 自检与修正
- 先给出自检清单（8 项）
1. 仅处理 `ch35`，未扩写其他章节正文。  
2. 保持章节编号与标题不变：`35. 起死回生：极限数据抢救与取证`。  
3. 细纲共 `7` 节，满足 `6-8` 节约束。  
4. 每节“必讲概念”均不超过 `3` 个。  
5. 每节均包含可执行动作（命令/SQL/检查项/演练步骤）。  
6. 案例数量为 `1` 主线 + `1` 支线。  
7. 新术语首次引入控制在 `12` 个内（本稿 `11` 个）：交接包、证据封存、事故时间窗、可疑范围、影子库、差异集、修复闸门、回放验证、事件时间线、根因树、WAL片段。  
8. 验收标准均量化可验证，无“尽快/基本/大概”类模糊结论。  

- 再给出本次细纲中你主动修正的 3 处问题
1. 删除了“平台长期演进路线”段落，避免提前侵入 `ch36`。  
2. 将原先两个支线合并为“日志缺段取证”单支线，保持主线聚焦。  
3. 把“完成修复/完成定位”改写为分钟、计数、字段完整率等硬指标。
