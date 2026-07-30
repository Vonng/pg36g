# 第 26 章容量实验合同

## 目标

本实验测量的是一个**声明完整、范围有限**的问题：

> 在记录过的 Pigsty 教学沙箱上，`pg36_shop` 的一组 50/30/20
> 读写混合，面对三档合成数据量和一、八两个并发档位时，吞吐、事务延迟、
> CPU、I/O、WAL、锁等待与空间增长怎样变化？

它不是“PostgreSQL 每秒能跑多少事务”，也不是生产容量审批。

```text
business workload contract
  -> isolated disposable database
      -> three dataset scales
          -> two client populations
              -> five counterbalanced repetitions
                  -> client transaction distribution
                  -> PostgreSQL counter deltas
                  -> PostgreSQL wait samples
                  -> client/server operating-system samples
                  -> Pigsty time-series corroboration
                      -> sandbox-only demand estimate
                      -> production gate remains pending
```

## 目标与连接路径

正式参考运行固定为：

| 职责 | 身份 |
|---|---|
| load generator | `pg-meta-1` / `10.10.10.10` / 2 vCPU |
| database server | `pg-test-1` / `10.10.10.11` / primary / 1 vCPU |
| database | `pg36_capacity` |
| login | `dbuser_pg36bench`, non-superuser |
| path | direct PostgreSQL `5432`, persistent prepared sessions |
| data | synthetic only |

load generator 与 server 必须是不同主机。直连主库是刻意的：本章先测
PostgreSQL engine baseline；HAProxy、PgBouncer 和应用入口的容量必须另做
service-path baseline，不能混在这里又不标注。

Pigsty 当前 HBA 通过 `+dbrole_readonly` 角色组识别内网业务连接。
runner 不修改 HBA，而是把一次性账号加入 `dbrole_readwrite`；后者已经是
`dbrole_readonly` 的成员。该临时 membership 同时设置 `INHERIT FALSE` 与
`SET FALSE`，只用于 HBA membership 判断，不让 benchmark login 继承或切换到
平台角色。账号随 fixture 一起删除。

## 风险等级与动作

| 动作 | 风险 | 远端行为 | 数据库行为 |
|---|---:|---|---|
| `lint` | L0 | 无 | 无 |
| `capture` | L0 | 只读 SSH、HTTP、SQL | 只读身份与资源检查 |
| `exercise` | L2 bounded | 在元节点运行有界负载 | 创建、装载、写入并删除专用 fixture |
| `verify` | L0 | 无 | 无 |
| `review` | L0 | 无 | 无 |
| `all` | L2 bounded | 以上全部 | 以上全部 |

`exercise` 会制造 CPU、I/O、WAL、复制与归档负载，不能在生产环境运行。
它只允许目标：

```text
cluster       pg-test
primary       pg-test-1 / 10.10.10.11
database      pg36_capacity
role          dbuser_pg36bench
environment   pg36-l2-vagrant disposable teaching sandbox
```

库或角色若已经存在，runner 一律拒绝覆盖。创建后写入 shared-object comment
marker；清理只有在 marker 精确匹配、没有其他会话时才执行。它不使用
`DROP DATABASE ... WITH (FORCE)`，不终止任何非本章会话。

## 工作负载

三类事务：

| operation | 权重 | 分布 | 主要动作 |
|---|---:|---|---|
| `read-product` | 50 | product Zipf 1.15 | product + inventory 点查 |
| `read-order` | 30 | customer Zipf 1.08 | 最近五个历史订单 |
| `place-order` | 20 | customer uniform, product Zipf 1.10 | inventory 行锁、更新、订单追加 |

数据档位：

| scale | factor | customer | product | historical order |
|---|---:|---:|---:|---:|
| S | 1 | 10,000 | 2,000 | 100,000 |
| M | 8 | 80,000 | 16,000 | 800,000 |
| L | 32 | 320,000 | 64,000 | 3,200,000 |

每个 cell：

- 自然预热 5 秒，不清 PostgreSQL 或 OS cache；
- 正式运行 8 秒；
- 五次重复；
- seed 按公开公式固定；
- `prepared` protocol、持久连接、零 think time；
- `250 ms` latency limit 只计 late，不跳过；
- `max-tries=1`，不把重试隐藏为成功。

这是一组 closed-loop maximum-throughput probes。client 完成上一笔后才发下一笔，
所以它会隐藏上游无限排队和放弃请求；生产 SLO 仍需 open-loop offered-load
sweep。

## 禁止动作

runner 不会：

- 修改 PostgreSQL、Patroni、PgBouncer、HAProxy、内核或 Pigsty 配置；
- 设置 `fsync=off`、`synchronous_commit=off` 或使用 unlogged table；
- 执行 `pg_stat_reset*`、`pg_stat_statements_reset`；
- drop OS cache、重启 PostgreSQL、强制 checkpoint、切换主库；
- 暂停归档、复制、备份、监控或 autovacuum；
- 把 raw query text、连接密码、URI、客户端地址或监控原始 payload 写入公共摘要；
- 把两点比较声称为精确 knee；
- 输出 production-approved TPS。

## 证据层

私密 evidence 包保留：

```text
preflight-evidence.json
remote-benchmark.log
remote/
  capacity-evidence.json
  initialize-{S,M,L}.txt
  runs/<cell-run>/
    pgbench.stdout
    pgbench.stderr
    transactions.*
    stats-before.json
    stats-after.json
    client-system.jsonl
    server-system.jsonl
    database-waits.jsonl
remote-cleanup.json
validation-report.json
negative-report.json
public-summary.json
review.txt
```

公共仓库只保存 `capacity-run.json` 的 allowlist 摘要。raw transaction logs、
system samples、SQL snapshots、queryid 明细和 HTTP payload 不进入公共仓库。

## 运行

完整运行需要一个不存在或为空的新私密目录，通常持续数分钟：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch26-run
static/labs/ch26/task.sh all
```

只做静态检查：

```bash
static/labs/ch26/task.sh lint
```

分阶段：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch26-run
static/labs/ch26/task.sh capture
static/labs/ch26/task.sh exercise
static/labs/ch26/task.sh verify
static/labs/ch26/task.sh review
```

已有 evidence 可以反复 `verify` 和 `review`，不能覆盖 capture 或 benchmark。

## 通过标准

- preflight 证明目标是空的教学沙箱；
- 三档规模、两档并发、每档五次，共 30 次 measured run；
- 每次都有 p50/p95/p99、client/server OS、PostgreSQL wait 与 counter delta；
- 事务失败和 skipped 均为零；late 单独报告；
- 所有统计 reset timestamp 不变；
- Pigsty 时序要么有观察值，要么以 `missing`/`query-failed` 明示，不补零；
- client saturation 若存在，必须进入解释；
- quantile 从事务样本重算，不平均 p99；
- 二十六个对抗变体全部被拒绝；
- 专用 database、role 和远端 `/tmp` 均清理；
- `production_ch26_gate` 保持 `pending`。
