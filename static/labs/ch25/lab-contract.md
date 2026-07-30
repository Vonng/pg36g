# 第 25 章可观测性实验合同

## 目标

本实验把第 24 章的观察合同落实为一组**候选**记录规则、告警规则、离线路由、
覆盖矩阵和诊断包合同，并回答四个不同的问题：

```text
live baseline
  -> 当前 Pigsty / PostgreSQL 观察链真实提供了什么
isolated rule test
  -> 给定合成时间序列，规则会不会在预期时刻触发与恢复
offline route test
  -> 给定标签，Alertmanager 会解析到哪个空 receiver
coverage review
  -> 哪些用户 SLI、控制信号和真实通知仍然不存在
```

“规则测试通过”不等于“规则已经上线”，“路由解析正确”不等于“真实通知已经
送达”，“面板可访问”也不等于“根因已经证明”。

## 风险与动作

| 动作 | 风险 | 远端行为 | 数据库行为 |
|---|---:|---|---|
| `lint` | L0 | 无 | 无 |
| `capture` | L0 | 只读 HTTP、SSH 和 SQL | 只读统计查询 |
| `exercise` | L1-ephemeral | 沙箱元节点 `/tmp/pg36-ch25.*` 内启动 loopback 测试进程并清理 | 无 |
| `verify` | L0 | 无 | 无 |
| `review` | L0 | 无 | 无 |
| `all` | L1-ephemeral | `capture` 加 `exercise` | 只读 |

`exercise` 不会修改在线 VictoriaMetrics、VMAlert 或 Alertmanager，不会向在线
Alertmanager 提交合成告警，不会创建 silence，也不会装载真实通知 receiver。
上传内容只包含本目录中的规则和测试，远端临时目录必须匹配
`/tmp/pg36-ch25.*` 才允许清理。

## 访问路径身份

工作站 SSH 配置可能把不同逻辑地址映射到端口转发。正式采集先进入
`10.10.10.10` 元节点，再从沙箱网络连接 `10.10.10.11`，并同时验证：

- 远端主机名是 `pg-test-1`；
- PostgreSQL `cluster_name` 是 `pg-test`；
- 当前节点不是恢复节点；
- `pg_stat_replication` 能看到两条复制流。

仅凭 SSH alias、IP 字符串或“命令成功”都不能证明观察的是目标主库。

## 只读边界

采集明确禁止：

- `EXPLAIN ANALYZE`、压测和故障注入；
- `pg_stat_reset`、`pg_stat_statements_reset` 或任何统计重置；
- `VACUUM`、`CHECKPOINT`、切换、重启、恢复和配置 reload；
- 读取或导出 SQL 文本、绑定参数、日志正文、客户端地址和凭据；
- 把瞬时样本写成事故结论。

SQL 设置 `statement_timeout=5s`、`lock_timeout=500ms`、只读取系统统计。证据只
保留聚合、版本、计数、时间戳和脱敏身份。

## 私密证据

正式运行要求一个不存在或为空的新目录：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch25-run
static/labs/ch25/task.sh all
```

目录为 `0700`、文件为 `0600`。公共仓库只保留 allowlist 摘要，不保留原始
HTTP 响应、SQL 文本、日志正文、真实通知配置或 inventory。

## 运行

只检查静态合同：

```bash
static/labs/ch25/task.sh lint
```

只读采集：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch25-run
static/labs/ch25/task.sh capture
```

隔离演练和完整验证：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch25-run
static/labs/ch25/task.sh all
```

重验已有 evidence：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/existing/ch25-run
static/labs/ch25/task.sh verify
static/labs/ch25/task.sh review
```

## 通过标准

- 第 24 章七条 accepted alert 均有同名规则，窗口、燃烧率、`for`、owner、
  runbook 和首个安全动作不漂移；
- 延迟、恢复、归档、长事务和冻结规则明确标为 proposed，只能进入测试 sink；
- 记录规则与依赖它们的告警规则位于不同 group；
- 合成序列覆盖正常、pending、firing、recovery、missing 和控制失败；
- 离线路由只包含空 receiver，page、ticket、diagnostic 和 proposed 均落到
  预期 sink；
- fast burn 只抑制同一服务和目标的慢告警；观察链故障只抑制派生 missing，
  不抑制独立用户症状和正确性告警；
- 在线 VMAlert 无规则错误，当前规则和告警数量被保存为基线而非永恒事实；
- `pg_stat_statements` 的 preload、扩展、reset 边界和只读聚合被记录，不导出
  query text；
- 归档判断同时使用增量和最近成功时间，不把历史 `failed_count > 0` 当作当前
  故障；
- 应用 SLI、reconciliation、restore metric、真实通知和生产批准的盲区保持
  明示；
- 对抗性变体全部被拒绝，`production_ch25_gate` 保持 `pending`。
