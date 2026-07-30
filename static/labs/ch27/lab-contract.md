# 第 27 章参数调优实验合同

## 要回答的问题

第 26 章观察到：

- c8 的 server work ratio 约为 84%；
- load generator 没有先饱和；
- 使用 prepared protocol；
- 六个 cell 的 temp bytes 均为零；
- 只有 c1/c8，精确 knee 未知；
- production sustainable TPS 仍为 `null`。

这些事实支持一个**可以证伪**的问题：

> prepared OLTP mix 在 `plan_cache_mode=auto` 下是否仍承担了足以影响吞吐的
> custom planning 成本，以至于强制 generic plan 能获得至少 2% 的稳定收益？

它不证明答案是“是”。实验的成功标准是得到可信的接受或拒绝结论，而不是必须改参。

```text
chapter 26 evidence
  -> one mechanism hypothesis
      -> session-local A/B
          -> paired seeds + counterbalanced order
              -> raw latency and PostgreSQL deltas
                  -> plan-shape probes
                      -> predeclared decision rule
                          -> parameter ADR
```

## 为什么只测试一个参数

候选清单中：

| 参数 | 处理 | 原因 |
|---|---|---|
| `plan_cache_mode` | 测试 | prepared + CPU pressure 使 planning overhead 可证伪 |
| `work_mem` | 不测试 | ch26 没有 temp spill |
| `shared_buffers` | 不测试 | block read 不等于 I/O 瓶颈，且涉及 restart/memory |
| `max_connections` | 不测试 | connection slot 不是吞吐 |
| `synchronous_commit` | 拒绝 | 改变 durability contract |
| `wal_compression` | 不测试 | WAL I/O 未证实，且可能增加 CPU |

同时改两个参数会失去因果归属。

## 风险与作用域

| 动作 | 风险 | 行为 |
|---|---:|---|
| `lint` | L0 | 本地检查合同和 28 个反例 |
| `capture` | L0 | 只读采集 target、配置与上游证据 |
| `exercise` | L2 bounded | 创建、装载、压测并清理 disposable fixture |
| `verify` | L0 | 重算 evidence |
| `review` | L0 | 独立检查发布边界、权限与清理 |
| `all` | L2 bounded | 顺序执行以上动作 |

唯一参数变化通过连接环境注入：

```text
PGOPTIONS=-c plan_cache_mode=auto
PGOPTIONS=-c plan_cache_mode=force_generic_plan
```

它只影响相应 benchmark session。实验不使用：

```text
ALTER SYSTEM
Patroni DCS edit
postgresql.conf / postgresql.auto.conf edit
reload / restart / failover
statistics reset / cache drop
durability reduction
```

session 结束即回退。`settings_before` 与 `settings_after` 必须证明全局 effective
settings 和配置文件错误集合未变化。

## 目标与 fixture

```text
environment   pg36-l2-vagrant disposable teaching sandbox
client        pg-meta-1
server        pg-test-1, pg-test primary
database      pg36_tuning
role          dbuser_pg36tune, non-superuser
data          synthetic M scale only
```

database 与 role 必须在 preflight 时不存在。创建后写入：

```text
pg36-ch27-disposable-tuning-fixture-v1:<run-id>
```

建库时先以 `ALLOW_CONNECTIONS false` 创建，撤销 `PUBLIC CONNECT`、只授予一次性
benchmark role 后才开放连接，避免数据库自动发现型监控器在实验期间建立持久会话。

清理只有在 database/role marker 精确匹配且没有 session 时执行；不使用
`DROP DATABASE ... WITH (FORCE)`，不终止其他会话。

Pigsty HBA 通过平台角色组识别连接。一次性 login 只获得用于 HBA 匹配的 membership，
同时设置 `INHERIT FALSE` 与 `SET FALSE`，不能继承或切换为平台角色。

## A/B 设计

固定：

```text
scale              M: 80k customer, 16k product, 800k history
clients            8
jobs               2
protocol           prepared
arrival            closed-loop
mix                read-product 50 / read-order 30 / place-order 20
warm-up            5 seconds per arm
measured           12 seconds per run
repetitions        5 paired repetitions
latency limit      250 ms
retry              max-tries=1
```

每个 repetition 的 baseline/candidate 使用相同 seed，顺序为：

```text
r1  auto -> force
r2  force -> auto
r3  auto -> force
r4  force -> auto
r5  auto -> force
```

每次 measured run 前重置可写 fixture。p95 从每个 arm 的 raw transaction sample
合并后重算，不平均五个 p95。

## plan probes

实验还对 product/order 两类 prepared query 做 low/high key probe：

- 保存 plan shape，不发布 SQL；
- plan shape 只保留 node、relation、index、join/strategy；
- 对 shape 计算 SHA-256；
- 保存 `pg_prepared_statements.generic_plans/custom_plans`；
- 验证 candidate 没有悄悄改变代表性 plan shape。

几个 probe 不能证明所有参数值的 plan 都安全；它们只是本轮最小 non-regression
证据。

## 预声明决策规则

candidate 只有同时满足以下条件，才可进入**更大的 canary**：

```text
all failures/late/skipped = 0
representative plan shapes equal
global settings unchanged
candidate pooled p95 / baseline pooled p95 <= 1.05
paired TPS ratio bootstrap 95% lower bound >= 1.02
```

任一失败：

```text
decision = reject-persistent-change
```

即使全部通过：

```text
decision = candidate-worthy-for-larger-canary
production_ch27_gate = pending
```

短时沙箱 A/B 不能直接授权 production change。

## 证据与发布边界

私密 evidence：

```text
preflight-evidence.json
remote-experiment.log
remote/
  tuning-evidence.json
  runs/<run-id>/
    pgbench.stdout
    pgbench.stderr
    transactions.*
    stats-before.json
    stats-after.json
remote-cleanup.json
validation-report.json
negative-report.json
public-summary.json
review.txt
```

公共仓库只保存 allowlist 摘要 `tuning-run.json`。raw transaction log、配置文件路径、
SQL 文本、连接信息与 secret 不公开。

## 运行

静态检查：

```bash
static/labs/ch27/task.sh lint
```

完整实验：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch27-run
static/labs/ch27/task.sh all
```

分阶段：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch27-run
static/labs/ch27/task.sh capture
static/labs/ch27/task.sh exercise
static/labs/ch27/task.sh verify
static/labs/ch27/task.sh review
```

## 通过标准

- 上游 ch26 hash、run id 和 claim boundary 未变化；
- 只测试 `plan_cache_mode`；
- 参数只在 benchmark session 生效；
- 五个 repetition 配对、seed 相同且顺序 counterbalanced；
- 十次 measured run 的 raw log 完整；
- quantile 与 paired ratio 可重算；
- plan shape fingerprint 可重算；
- 全局配置无漂移，durability 未降低；
- 28 个对抗变体全部被拒绝；
- database、role、remote temp 均清理；
- 无论接受或拒绝 candidate，production gate 都保持 `pending`。
