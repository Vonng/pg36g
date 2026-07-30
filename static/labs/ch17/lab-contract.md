# ch17 分析加速与分布式选型实验合同

## 目标

本实验回答的不是“怎样把 PostgreSQL 伪装成两台机器”，而是一个更重要的
工程问题：什么时候单机仍有余量，什么时候瓶颈属于数据访问形状，什么时候才
真正需要分布式。证据链固定为：

```text
冻结 24 万条本地事实与两份 12 万条分片事实
  -> 用并行、覆盖索引、BRIN、work_mem 与物化汇总刻画单机边界
  -> 比较本地、汇总、朴素 FDW 与两阶段聚合的同一份月报
  -> 证明分区裁剪、远端过滤和远端聚合
  -> 保留 JOIN 未下推与单分片故障两个反例
  -> 固定权限、身份、重建和跨库退出边界
  -> 形成可追溯的架构决策记录
```

## 固定目标

- 协调库：`pg36_shop`
- 分片库：`pg36_shard_a` 与 `pg36_shard_b`
- 协调 schema：`shop_ch17`
- 远端 schema：`shop_ch17_shard`
- 扩展 schema：`shop_ch17_ext`
- owner：`pg36_owner`
- application role：`pg36_app`
- 正式实验：PostgreSQL 18.x，实测 18.4，`postgres_fdw` 1.2
- Pigsty：正文映射到 4.4；本地直连证据不伪装成 Pigsty L1 验收
- 数据：8 租户、每租户 50 账户、120 日、每账户每日 5 条销售，共
  400 个账户与 240,000 条事实

三个数据库位于同一个本地 PostgreSQL 实例。它们足以显示 SQL、规划器、
FDW、权限与失败边界，却没有独立的 CPU、存储、网络或故障域。因此本实验
不能证明任何分布式吞吐、时延、弹性、高可用或线性扩展结论。

## 路由口径

协调端使用显式 LIST 分区：

| 分区 | 租户 | 外表 | 远端数据库 |
|---|---|---|---|
| shard A | 2、4、6、8 | `*_dist_0` | `pg36_shard_a` |
| shard B | 1、3、5、7 | `*_dist_1` | `pg36_shard_b` |

这不是为了推荐手写租户清单，而是为了让演示路由与冻结生成器的
`tenant_id % 2` 完全一致。PostgreSQL HASH 分区会调用类型的哈希支持函数，
`MODULUS 2, REMAINDER 0` 并不表示“偶数租户”；把两者当作同一算法会造成
裁剪后静默漏数。本章把这个失败原型作为分布式正确性案例保留。

## 单机证据口径

- 月聚合必须出现两个 worker、`Parallel Seq Scan`、partial/final
  aggregate，证明可并行，不把小样本耗时当容量结论。
- 租户 3 的 4 月查询必须使用覆盖 B-tree 的 `Index Only Scan`，返回
  7,500 行且 `Heap Fetches: 0`。
- 同一排序在 `work_mem=64kB` 下外排，在 `32MB` 下内存排序；它证明 spill
  可观测，不意味着应该把全局 `work_mem` 直接调大。
- 原始事实月报扫描 240,000 行，日汇总月报扫描 2,880 行，二者输出与冻结
  32 行完全一致。
- BRIN 只作为与物理相关性匹配时的候选保留；本实验不声称它优于 B-tree。

## 分布式证据口径

- 租户 3 的查询只能访问 shard B，远端 SQL 必须包含租户和日期过滤。
- 朴素全局月报向协调端返回 240,000 条事实行。
- 两阶段月报在两个分片分别按租户、日期聚合，各返回 480 行，共 960 行，
  协调端再合并成 32 个月结果。
- 租户 3 的账户维表与事实表位于同一远端库，但通过两个分区外表父表查询时，
  实测仍在协调端执行 `Hash Join`。所以“同分布键”只是下推的必要设计线索，
  不是既成事实；必须读计划。
- 临时把 shard B 端口改为不可达后，tenant 2 的 shard A 查询仍能返回
  30,000 行，而全局查询以 SQLSTATE `08001` 失败。事务断开会回滚服务器
  选项，任务还会再次核对端口。

## 身份与权限

本地 PostgreSQL 18 不允许非超级用户在没有凭据的默认配置下使用
`postgres_fdw` 信任式连接。本实验仅在同实例 Unix-domain socket 上显式
设置 `password_required=false`，并建立六个具名 user mapping：
`postgres`、`pg36_owner`、`pg36_app` × 两个 server。没有 PUBLIC mapping。

这是隔离实验的捷径，不是生产方案。生产必须评审 SCRAM、GSS、凭据委派、
secret 生命周期、连接审计和故障时的身份行为；不得照抄
`password_required=false`。

## 固定事实

| 事实 | 预期 |
|---|---:|
| 本地 / 分布式销售 | 240,000 / 240,000 |
| shard A / shard B | 120,000 / 120,000 |
| 日汇总 / 月结果 | 2,880 / 32 |
| 租户 3 的 4 月 | 7,500 笔，69,375.00 |
| 朴素 / 两阶段传输形状 | 240,000 / 960 行 |
| 本地业务校验和 | `42fb8ab5444469eba1f104a8e1e529dd` |
| 月报校验和 | `644d45544ebbc2a80c42270c38ac6885` |
| 应用写入 | SQLSTATE `42501` |
| shard B 不可达 | SQLSTATE `08001` |

## 复位边界

协调库 reset 需要：

```text
PG36_RESET_TOKEN=RESET_CH17_ANALYTICS_FDW_LAB
PG36_RESET_TARGET=pg36_shop/shop_ch17+shop_ch17_ext+fdw
```

远端库使用同一 action token，但 target 分别是
`pg36_shard_a/shop_ch17_shard` 与
`pg36_shard_b/shop_ch17_shard`。脚本先验证三个数据库，再逐库执行精确
DROP；不使用 `CASCADE`，并保留两个空数据库壳。

每个数据库里的 reset 都是单事务，但 PostgreSQL 没有把三个数据库的 DDL
包进一个本地原子事务的能力。因此完整退出不是全局原子操作。任务采用
“全部预检通过，再按协调库、A、B 顺序退出，随后整套重建并复核”的补偿式
流程；这本身就是分布式系统运维成本的一部分。
