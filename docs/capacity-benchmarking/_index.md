---
title: 第 26 章 胸有成竹：容量规划与压测基线
linkTitle: 26 胸有成竹：容量规划与压测基线
weight: 360
aliases:
- "/ch26/"
- "/volume-2/capacity-benchmarking/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch26
book_number: 26
book_part: part-5
book_status: draft
---

一张写着“12 万 TPS”的截图，没有回答容量问题。

它可能来自：

```text
select-only
  + 全部命中缓存
  + fsync 关闭
  + 与 server 同机的 load generator
  + 一次 10 秒运行
  + 没有约束、索引维护、WAL、复制、备份和故障余量
```

也可能来自一个完全严谨的实验。数字本身无法告诉你是哪一种。

容量规划真正需要的是一条可审计推理链：

```text
业务到达过程
  -> operation mix 与数据形状
      -> 延迟、错误和正确性目标
          -> 可复现实验
              -> throughput / latency / failure distribution
                  -> CPU / memory / I/O / WAL / lock evidence
                      -> 单位业务资源需求
                          -> 增长、保留、维护和故障模型
                              -> 扩容触发线与提前期
```

本章把 PostgreSQL 的原生证据与 Pigsty 的观察面放到同一条链上。目标不是教你
“跑一个 pgbench 命令”，而是让你能判断：

- workload 是否代表业务；
- 实验是否控制了足够多的变量；
- load generator、连接路径或缓存是否在替 server 背锅；
- throughput 上升是否以 tail latency、错误或排队为代价；
- 一次测量能支持什么结论，不能支持什么结论；
- 怎样把测量变成 CPU、WAL、存储和提前期模型；
- 为什么生产容量仍需要故障、维护、备份和 open-loop 场景。

## 本章实验先给出一个反直觉结论

第 26 章参考运行不是“性能榜单”，而是一组教学用、有界的证据链：

- Pigsty `v4.4.0` 教学沙箱；
- PostgreSQL `18.4`；
- 独立 `pg-meta-1` load generator：2 vCPU、约 3.8 GiB RAM；
- `pg-test-1` primary：1 vCPU、约 1.9 GiB RAM；
- `shared_buffers`：512,753,664 bytes；
- 50% product read、30% order read、20% place-order；
- S/M/L 三档数据，1/8 两档 client；
- 每个 cell 五次重复，共 30 次 measured run；
- 511,709 笔事务，失败、skipped、deadlock 和超过 250 ms 的事务均为零；
- raw transaction、OS、SQL snapshot 与 wait evidence 全部留在私密 evidence；
- 专用 database、role 和远端临时目录全部清理。

聚合结果：

| cell | schema size | clients | median TPS | pooled p95 | server work | client work |
|---|---:|---:|---:|---:|---:|---:|
| S-c1 | 28.3 MiB | 1 | 1,508.5 | 2.152 ms | 48.9% | 17.7% |
| S-c8 | 28.3 MiB | 8 | 2,920.5 | 9.448 ms | 84.2% | 29.5% |
| M-c1 | 224.3 MiB | 1 | 1,555.8 | 2.123 ms | 50.1% | 17.8% |
| M-c8 | 224.3 MiB | 8 | 2,911.5 | 9.398 ms | 84.0% | 29.1% |
| L-c1 | 898.6 MiB | 1 | 1,423.6 | 2.259 ms | 46.3% | 16.2% |
| L-c8 | 898.6 MiB | 8 | 2,774.3 | 10.087 ms | 84.2% | 27.8% |

从 c1 到 c8：

```text
throughput gain       1.87x ~ 1.95x
pooled p95 multiplier 4.39x ~ 4.47x
```

这说明八个 client 获得了更多吞吐，却付出了约四倍多的 p95。它**没有**说明：

- knee 就在八个 client；
- 2,774 TPS 是 L 档生产容量；
- 65% CPU 对应的线性投影可以直接采购；
- 0 deadlock 代表业务没有锁风险；
- Pigsty 全窗口 median 就是某个 cell 的资源消耗；
- 虚拟磁盘代表生产存储。

两点只能 bracket，不能定位 knee；closed-loop 只能观察固定 client population，
不能重现上游 offered load；8 秒运行也远短于生产基线所需的时间。PostgreSQL
官方 [`pgbench` good practices](https://www.postgresql.org/docs/18/pgbench.html)
明确警告，不应相信只跑几秒的测试，可靠数字可能需要几分钟、几次乃至数小时。
因此本章参考 run 用来证明**实验管线与推理方法**，不批准生产数字。

公共 allowlist 结果见
[`capacity-run.json`](/labs/ch26/capacity-run.json)，完整边界见
[`lab-contract.md`](/labs/ch26/lab-contract.md)。

## 本章学习成果

完成本章后，你应该能独立完成：

1. 把业务 forecast 转成 operation-class arrival model，而不是只写“读写比 8:2”；
2. 区分 request、SQL statement、database transaction、connection 与并发；
3. 用 Little’s Law 检查到达率、响应时间和在途量是否自洽；
4. 选择内置 pgbench 作为 engine calibration，或写业务自定义脚本；
5. 声明 key distribution、mix、think time、arrival model、protocol 和连接路径；
6. 固定版本、配置、数据、随机 seed、预热、顺序和重复；
7. 正确处理 pooled percentile、run-level estimate、置信区间与异常样本；
8. 用 `pg_stat_database`、`pg_stat_io`、`pg_stat_wal`、wait event 和 OS 证据解释曲线；
9. 判断 load generator 是否成为瓶颈；
10. 把 CPU seconds/transaction、WAL bytes/transaction 和 bytes/order 写进容量模型；
11. 计算增长、保留、maintenance workspace、failure headroom 与 lead time；
12. 明确保留 unknown，并拒绝把 sandbox 结果升级为生产承诺。

## 本章目录

### [26.1 从需求建立容量模型](01/)

- [26.1.1 事务类型、读写比、并发和数据增长](01/#item-26-1-1)
- [26.1.2 平均值、峰值、突发与批处理叠加](01/#item-26-1-2)
- [26.1.3 延迟目标、错误预算与安全余量](01/#item-26-1-3)

### [26.2 设计代表性工作负载](02/)

- [26.2.1 内置 pgbench 与业务自定义脚本](02/#item-26-2-1)
- [26.2.2 参数分布、事务混合和数据倾斜](02/#item-26-2-2)
- [26.2.3 think time、连接方式和客户端瓶颈](02/#item-26-2-3)

### [26.3 建立可信实验](03/)

- [26.3.1 固定硬件、版本、配置、数据与随机种子](03/#item-26-3-1)
- [26.3.2 预热、重复、置信区间与异常值](03/#item-26-3-2)
- [26.3.3 冷热缓存、后台任务与邻居噪声](03/#item-26-3-3)
- [26.3.4 绝对性能结论只适用于记录过的环境](03/#item-26-3-4)

### [26.4 找到饱和点与瓶颈](04/)

- [26.4.1 吞吐—延迟曲线与排队拐点](04/#item-26-4-1)
- [26.4.2 CPU、内存、I/O、WAL 与锁的证据](04/#item-26-4-2)
- [26.4.3 连接数增加为何可能降低吞吐](04/#item-26-4-3)

### [26.5 从测量推导容量与成本](05/)

- [26.5.1 单位业务量的资源消耗](05/#item-26-5-1)
- [26.5.2 增长、保留、备份与维护空间](05/#item-26-5-2)
- [26.5.3 扩容触发线、提前期与失效假设](05/#item-26-5-3)

### [26.6 实战：`pg36_shop` 容量基线](06/)

- [26.6.1 运行三个规模和两个并发档位](06/#item-26-6-1)
- [26.6.2 用 Pigsty 与原生视图解释饱和点](06/#item-26-6-2)
- [26.6.3 输出可复现实验报告、容量模型和未知项](06/#item-26-6-3)

## 阅读与实践路线

如果你负责应用：

```text
26.1 -> 26.2 -> 26.3 -> 26.6
```

重点是 operation contract、arrival model、idempotency/retry、connection path 和
load generator。

如果你负责平台：

```text
26.1 -> 26.3 -> 26.4 -> 26.5 -> 26.6
```

重点是实验控制、native counters、Pigsty time series、headroom、failure model
和 provisioning lead time。

两条路线最终必须合流。平台无法从数据库指标猜出业务 mix；应用也不能从一张
TPS 表判断 WAL、backup、replica 和 maintenance 是否还有余量。

## 实验文件

```text
static/labs/ch26/
├── requirements.json
├── workload-contract.json
├── experiment-matrix.json
├── capacity-model.json
├── negative-cases.json
├── topology.mmd
├── lab-contract.md
├── setup.sql
├── reset-cell.sql
├── read-product.sql
├── read-order.sql
├── place-order.sql
├── stat-snapshot.sql
├── wait-sampler.sql
├── system_sampler.py
├── capture.py
├── exercise.py
├── remote_benchmark.py
├── validate.py
├── review.py
├── task.sh
└── capacity-run.json
```

它们分别固定：

| 文件 | 责任 |
|---|---|
| requirements | target、风险、支持/不支持的 claim、gate |
| workload contract | mix、分布、arrival、protocol、seed、cache policy |
| matrix | 三规模、两并发、五重复与 counterbalanced order |
| model | 业务输入、单位需求、空间与 lead-time 方程 |
| SQL / pgbench scripts | synthetic schema、reset 与三类事务 |
| samplers | OS measured window、PostgreSQL wait 与 counter snapshot |
| capture | L0 目标、上游与 clean-start gate |
| exercise | 远端隔离、完整矩阵与精确清理 |
| validate / review | 正向合同、26 个反例、hash、mode、secret 与 claim |
| public run | 聚合 allowlist；不含 raw evidence |

## 参考资料

- [PostgreSQL 18 `pgbench`](https://www.postgresql.org/docs/18/pgbench.html)
- [PostgreSQL 18 cumulative statistics](https://www.postgresql.org/docs/18/monitoring-stats.html)
- [PostgreSQL 18 resource consumption](https://www.postgresql.org/docs/18/runtime-config-resource.html)
- [PostgreSQL 18 WAL configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html)
- [PostgreSQL 18 streaming replication](https://www.postgresql.org/docs/18/warm-standby.html)
- [Pigsty monitoring architecture](https://pigsty.io/docs/concept/monitor/)
- [Pigsty PostgreSQL dashboards](https://pigsty.io/docs/pgsql/dashboard/)
- [Prometheus histogram and quantile practice](https://prometheus.io/docs/practices/histograms/)

---

[上一章：望闻问切：监控体系与可观测诊断](/observability/) · [返回下卷导读](/lower-volume/) · [下一章：精益求精：参数调优与资源治理](/configuration-tuning/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
