# 慢请求诊断记录

## 1. 事件边界

- 事件编号：
- 负责人：
- UTC 时间窗（起止）：
- 用户可见症状：
- 受影响服务、路由、实例、数据库：
- SLI/SLO：延迟分位数、样本数、吞吐、并发、错误率：
- 最近一次已知正常时间窗：
- 最近变更：

## 2. 时间分解

| 阶段 | 开始/结束证据 | 耗时或排队量 | 证据来源 |
|---|---|---:|---|
| 客户端/网关 |  |  |  |
| 应用队列/连接池 |  |  |  |
| 获得数据库连接 |  |  |  |
| PostgreSQL 执行 |  |  |  |
| 结果传输/客户端消费 |  |  |  |

## 3. 身份与查询族

- service / cluster / instance / role：
- database / user / application：
- PID + backend_start（仅实时动作使用）：
- queryid / 查询指纹及其适用版本：
- 归一化 SQL：
- 代表参数（脱敏）：
- calls / rows / total time / mean time / temp / WAL：

## 4. 原生证据

- `pg_stat_activity` state / wait_event_type / wait_event：
- `pg_blocking_pids()` 与阻塞边：
- 机器可读计划：estimate / actual / loops / buffers / WAL / settings：
- PostgreSQL 日志与 SQLSTATE：
- 主机 CPU / I/O / memory / pressure：
- PostgreSQL、客户端、Pigsty 版本：
- 数据、统计、配置与 source hash：

## 5. 假设树

| 排名 | 可证伪假设 | 支持证据 | 冲突证据 | 最小实验 | 退出/回退条件 |
|---:|---|---|---|---|---|
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |

## 6. 单变量对照

- 保持不变：
- 唯一改变：
- cache、并发、参数、数据规模控制：
- 重复次数与汇总方法：
- 修复前：
- 修复后：
- 未改善时的反证结论：
- 新增副作用：

## 7. 结论与动作

- 已证明的根因：
- 被排除但未证明不可能的替代解释：
- 即时缓解：
- 永久修复：
- 风险等级、审批人与执行窗口：
- 回退结果：
- 监控或规则补强：
- 证据包位置与保留期限：
