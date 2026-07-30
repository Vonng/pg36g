# ch15 检索质量实验合同

## 目标

本实验验证的不是“某条搜索 SQL 能返回三行”，而是一条可重复的检索决策链：

```text
冻结语料、查询与人工标注
  -> 明确语言、字段权重、过滤与向量模型版本
  -> 分别产生全文、模糊、精确向量候选
  -> 用 RRF 合并名次
  -> 用 Precision / Recall / MRR / NDCG 比较
  -> 单独测量 HNSW 相对精确结果的召回
  -> 固定权限、发布证据与精确退出
```

## 固定目标

- database：`pg36_shop`
- schema：`shop_ch15`
- owner：`pg36_owner`
- application role：`pg36_app`
- PostgreSQL：14–18；正式本地证据在 18.4 采集
- 依赖：第 14 章已认证的 `pg_trgm` 1.6 与 `vector` 0.8.4
- Pigsty：正文映射到 4.4；本地路径是直接 PostgreSQL，不伪装为 L1
- fixture：17 个商品、8 个查询、24 条 1–3 级相关性标注
- embedding：`pg36-handcrafted-topic-4d-v1`，四维手工坐标，L2

实验只接管带精确 marker 的 `shop_ch15`。同名 schema 的 owner、marker、
关系白名单或 catalog 边界任何一项不符，setup 与 reset 都会拒绝继续。本章
不创建、升级或删除第 14 章持有的扩展。

## 质量口径

- `Precision@3`：前三个位置中相关结果数除以 3；未返回的位置也算损失。
- `Recall@3`：前三个位置覆盖的相关结果数除以该查询全部相关结果数。
- `MRR@3`：第一个相关结果名次的倒数；前三名没有相关结果时为 0。
- `NDCG@3`：按 `2^grade - 1` 计增益并按位置折损，再除以理想排序的 DCG。
- 每个查询恰有三条正相关标注，因此本 fixture 中 Precision@3 与 Recall@3
  数值相同；这不是两个指标通常等价。

所有质量黄金值都来自精确、全量的向量距离与确定性 SQL 排名。HNSW 查询只在
独立 probe 中与精确集合求交，不能反过来定义黄金值。

## 固定结论

| 策略 | Precision@3 | Recall@3 | MRR@3 | mean NDCG@3 |
|---|---:|---:|---:|---:|
| 全文 | 0.291667 | 0.291667 | 0.750000 | 0.613043 |
| 模糊 | 0.916667 | 0.916667 | 1.000000 | 0.942881 |
| 精确向量 | 1.000000 | 1.000000 | 1.000000 | 0.817314 |
| RRF 混合 | 1.000000 | 1.000000 | 1.000000 | 0.962929 |

这些数字只描述冻结集合。它们可以捕获代码回归，不能外推到真实用户流量。

## 执行计划口径

`fts-plan.sql`、`trigram-plan.sql` 与两个 HNSW probe 会暂时关闭某些 planner
路径，以证明索引“可被使用”；`vector-exact-plan.sql` 则关闭索引路径以证明
精确全量排序。强制计划不证明生产规划器会选择它，更不证明它更快。

真实发布必须另测：

- 代表性规模下的 P50/P95/P99 延迟与吞吐；
- 索引构建、更新、WAL、内存、磁盘和副本延迟；
- HNSW 在完整查询集、不同过滤选择性与不同 `ef_search` 下的 recall；
- 查询长度、语法、超时、并发和滥用边界；
- 模型生成链、失败重试、旧向量回填与双版本迁移。

## 复位边界

`reset` 必须同时提供：

```text
PG36_RESET_TOKEN=RESET_CH15_SEARCH_LAB
PG36_RESET_TARGET=pg36_shop/shop_ch15
```

脚本还会核对 database、writable instance、schema owner/marker、精确关系清单、
对象 marker 与活跃 worker。它按视图、表、schema 的依赖顺序使用 RESTRICT
语义，不使用 `CASCADE`，也不触碰 `shop_ch14` 或任何扩展。
