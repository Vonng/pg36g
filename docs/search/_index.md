---
title: 第 15 章 见微知著：全文、模糊与向量检索
linkTitle: 15 见微知著：全文、模糊与向量检索
weight: 250
aliases:
- "/ch15/"
- "/volume-1/search/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch15
book_number: 15
book_part: part-3
book_status: draft
---

搜索不是“给某一列加个索引”。它至少包含四个问题：

```text
哪些对象有资格出现？        filtering
从多少对象中找候选？        candidate generation
候选之间怎样比较先后？      ranking
怎样证明结果真的更好？      evaluation
```

全文检索、三元组模糊匹配和向量近邻解决的是不同子问题：

| 方法 | 最擅长捕捉 | 主要盲区 |
|---|---|---|
| PostgreSQL FTS | 词形归一、多词布尔/短语、字段权重 | 拼写错误、词表之外的语义表达 |
| `pg_trgm` | 字符串局部相似、错拼、包含与相似候选 | 业务语义、长文档相关性 |
| 向量检索 | 由模型编码的相似性 | 精确词优势、模型偏差、近似召回 |
| 混合检索 | 多路召回互补 | 参数、成本、解释与验证复杂度 |

它们可以组合，却不能因为“混合”两个字就自动更好。本章把检索从演示查询
变成一个可反驳的工程实验：

> 冻结语料、查询、相关性标注和模型身份；每一路独立产生候选；质量黄金值
> 使用精确计算；近似索引另测召回；最后才讨论延迟、部署与上线。

## 本章完成后

你应当能够：

- 区分精确过滤、词法相关、字符串相似与模型相似；
- 把查询解析、过滤、候选生成、排序、融合和重排拆成独立阶段；
- 为检索实验建立带版本的语料、查询集与分级相关性标注；
- 解释 parser、dictionary、configuration、`tsvector` 与 `tsquery`；
- 显式固定文本搜索配置，构造带 A/B 权重的存储生成列；
- 正确选择 `websearch_to_tsquery`、`plainto_tsquery`、`phraseto_tsquery`
  或 `to_tsquery`，而不把原始用户输入直接交给严格语法；
- 用 `ts_rank_cd` 排序，并知道 0–1 归一化不等于跨检索器可比概率；
- 解释 `similarity`、`word_similarity`、`%` 门槛与 GIN/GiST 的边界；
- 选择 L2、余弦或内积时，把模型训练与归一化合同写清楚；
- 区分精确近邻与 HNSW/IVFFlat 近似近邻，不用 ANN 结果定义质量黄金值；
- 解释过滤为何可能降低 ANN 返回数，以及 iterative scan 能补什么、不能
  保证什么；
- 用 RRF 合并不同分数尺度的排名，并知道何时需要校准或重排；
- 计算 Precision@K、Recall@K、MRR@K 与 NDCG@K；
- 在 Pigsty 中把扩展装包、数据库启用、版本核对和节点一致性分开验收；
- 把模型费用、数据出境、向量回填、索引维护、WAL 与副本延迟纳入 ADR；
- 交付一个可运行、可审校、可精确复位的检索 PoC。

## 一条有意不完美的实验

贯穿实验位于 `shop_ch15`，固定：

```text
17 products (16 active + 1 inactive guard)
8 queries
24 graded relevance judgments
4-dimensional handcrafted vectors
3 candidate generators
RRF k=60, source depth=4, result depth=3
```

四维向量的模型标识为：

```text
pg36-handcrafted-topic-4d-v1
```

它不是 embedding 模型，也没有调用任何外部 API。它只是可人工核算、每次
重建完全相同的主题坐标，用来隔离数据库机制与模型随机性。真实模型质量必须
用真实文本重新测，不能继承本章数字。

固定评估集得到：

| 策略 | Precision@3 | Recall@3 | MRR@3 | mean NDCG@3 | min NDCG@3 |
|---|---:|---:|---:|---:|---:|
| 全文 | 0.291667 | 0.291667 | 0.750000 | 0.613043 | 0.000000 |
| 模糊 | 0.916667 | 0.916667 | 1.000000 | 0.942881 | 0.842828 |
| 精确向量 | 1.000000 | 1.000000 | 1.000000 | 0.817314 | 0.631039 |
| RRF 混合 | 1.000000 | 1.000000 | 1.000000 | 0.962929 | 0.759192 |

结果故意保留三个反例：

1. `wireles hedphones` 与 `postgre databse tuning` 的全文结果为空，说明
   词形归一不是拼写纠正；
2. 精确向量覆盖全部相关对象，但次序不总正确，Recall 高不等于 NDCG 高；
3. `q02` 上混合 NDCG 为 `0.759192`，低于纯模糊的 `0.842828`，说明
   融合可以把弱信号带进来。

因此本章的结论不是“向量最好”或“混合必胜”，而是：

```text
the measured winner on this frozen set
is a release candidate for this frozen set
```

## 精确质量与近似服务路径分开

质量视图枚举过滤后的全部候选并计算精确 L2 距离，不经过 HNSW。HNSW 只在
独立 probe 中运行：

```text
query = q06 / trail hydration
exact top-3 = 7,8,9
HNSW top-3  = 7,8,9
recall@3    = 1.000000
```

这一个点证明“能够查询并比较”，不证明生产召回为 1。pgvector 官方说明，
默认无 ANN 索引时是精确搜索；HNSW/IVFFlat 以部分召回换取速度，生产应持续
拿近似结果与精确结果对照。参见
[pgvector 0.8.4 README](https://github.com/pgvector/pgvector/blob/v0.8.4/README.md)。

强制执行计划分别验证：

```text
FTS      -> GIN bitmap index scan
trigram  -> GIN bitmap index scan
exact    -> sequential scan + sort
HNSW     -> HNSW index scan
filtered -> HNSW index scan + active/category filter
```

这里关闭部分 planner 路径，只为证明索引可用；不是 17 行数据上的性能比较。

## 实验资产

规范与决策：

- [实验合同](/labs/ch15/lab-contract.md)
- [检索 ADR](/labs/ch15/search-adr.md)
- [冻结夹具清单](/labs/ch15/fixture-manifest.json)
- [v1.3 proposal](/labs/ch15/baseline-v1.3-proposal.json)
- [Pigsty 4.4 声明片段](/labs/ch15/pigsty-declaration.example.yml)

输入与实现：

- [冻结商品](/labs/ch15/frozen-corpus.csv)
- [冻结查询](/labs/ch15/frozen-queries.csv)
- [冻结相关性标注](/labs/ch15/frozen-judgments.csv)
- [建模与索引](/labs/ch15/setup.sql)
- [排名视图](/labs/ch15/ranking-views.sql)
- [评估汇总](/labs/ch15/quality-summary.sql)
- [ANN 对照](/labs/ch15/ann-compare.sql)
- [最终状态](/labs/ch15/final-state.sql)
- [自动审校器](/labs/ch15/review.py)
- [精确复位](/labs/ch15/reset.sql)

三份 CSV 不只是仓库附件。自动化会从数据库重新导出并执行逐字节比较，
`fixture-manifest.json` 还固定各文件 SHA-256、行数、模型身份、生成方法与
许可证边界。

## 快速运行

本章复用第 14 章已经安装和认证的扩展，不自行接管扩展生命周期：

```bash
export PGSERVICEFILE=/path/to/pg_service.conf
export PGSERVICE=pg36-admin

PG36_EVIDENCE_DIR="$PWD/evidence/ch15" \
  ./static/labs/ch15/task.sh all
```

`all` 会：

1. 验证目标数据库、角色、ch04-v1 模型和第 14 章扩展身份；
2. 以 owner/marker/对象白名单保护 `shop_ch15`；
3. 创建带权重的存储 `tsvector`、四张表、七个排名/质量视图；
4. 创建全文 GIN、标题 trigram GIN、向量 HNSW 与过滤 B-tree；
5. 从数据库导出三份 CSV 并与冻结输入逐字节比较；
6. 采集文档、索引、体积、权限、查询解析、排名和质量证据；
7. 采集精确计划与三类索引计划；
8. 以精确集合为真值测一次 HNSW Recall@3；
9. 证明 `pg36_app` 可读、更新返回 SQLSTATE `42501`；
10. 运行关系、生成列、过滤、质量、checksum 和权限的全量断言；
11. 证明错误 token、错误 target、活跃 worker 时 reset 分别被拒绝；
12. 不用 `CASCADE` 精确复位，确认第 14 章扩展保留，再完整重建复验。

正式 Homebrew PostgreSQL 18.4 证据两轮均得到：

```text
status=ok
fixture=frozen-byte-identical
quality=precision+recall+mrr+ndcg
ranking=fts+trigram+exact-vector+rrf
ann=q06-exact-vs-hnsw-recall-1.000000
guards=P3660+P3661+P3663
extensions=ch14-preserved
pigsty_l1=not-run
release_candidate_checksum=bf92a6ad0f60dc3e125b39dbf67bf4d6c5e50275192bd01a7ca4c50d142f822e
```

> **安全边界**
>
> `task.sh all` 会删除并重建带本章精确 marker 的 `shop_ch15`，只适合
> 本书本地/开发夹具。它不会删除扩展。生产上应以在线建索引、双写/回填、
> 灰度读流量和可回退发布替代“删后重建”。

## 学习路径

### [15.1 先定义检索任务与评估集](01/)

- [15.1.1 精确筛选、词法相关与语义相似](01/#item-15-1-1)
- [15.1.2 查询、候选、排序和过滤的分层](01/#item-15-1-2)
- [15.1.3 建立带人工相关性标签的查询集合](01/#item-15-1-3)

先固定“什么叫好”。没有评估集，后面的任何好看查询都只是故事。

### [15.2 PostgreSQL 全文检索](02/)

- [15.2.1 文档、词典、配置与 `tsvector`](02/#item-15-2-1)
- [15.2.2 查询语法、权重与相关性排序](02/#item-15-2-2)
- [15.2.3 GIN/GiST 索引、更新与语言边界](02/#item-15-2-3)

从 PostgreSQL 原生词法管线开始，理解它为何强，也理解错拼为何仍会漏。

### [15.3 模糊匹配与拼写容错](03/)

- [15.3.1 `pg_trgm` 相似度与距离](03/#item-15-3-1)
- [15.3.2 前缀、包含、拼写错误与候选召回](03/#item-15-3-2)
- [15.3.3 与全文检索的互补和重复](03/#item-15-3-3)

用字符三元组补足错拼，但不给零分 Top-K 贴上“相关”标签。

### [15.4 可复现的向量检索](04/)

- [15.4.1 维度、距离度量与归一化](04/#item-15-4-1)
- [15.4.2 精确近邻与近似索引](04/#item-15-4-2)
- [15.4.3 索引参数、过滤条件与召回代价](04/#item-15-4-3)
- [15.4.4 冻结文本、模型标识、许可证、向量文件与校验和](04/#item-15-4-4)

把向量看作有来源、有版本、有度量合同的数据，而不是神秘的“AI 列”。

### [15.5 混合检索与排序验证](05/)

- [15.5.1 词法、模糊和语义候选合并](05/#item-15-5-1)
- [15.5.2 分数归一、倒数排名融合与重排](05/#item-15-5-2)
- [15.5.3 用标注集比较质量，不用单个“好看案例”](05/#item-15-5-3)

学会合并名次、计算指标、解释反例，而不是拿一个查询挑选截图。

### [15.6 扩展部署与运行代价](06/)

- [15.6.1 安装检索扩展并核对版本](06/#item-15-6-1)
- [15.6.2 观察索引体积、构建、查询和维护](06/#item-15-6-2)
- [15.6.3 外部嵌入生成的权限、费用与数据边界](06/#item-15-6-3)

把 PostgreSQL 对象映射到 Pigsty 交付和长期运行，不把安装成功当作上线。

### [15.7 实战：`pg36_shop` 商品混合检索 PoC](07/)

- [15.7.1 用冻结向量离线复现实验](07/#item-15-7-1)
- [15.7.2 比较全文、模糊、向量与混合结果](07/#item-15-7-2)
- [15.7.3 输出 ADR、质量证据、生产代价与退出路径](07/#item-15-7-3)
- [15.7.4 验收采用 `checklist:evidence`，不设脱离场景的性能线](07/#item-15-7-4)

最后运行双周期实验，拿出可以评审、可以拒绝、也可以退出的 proposal。

## 版本与证据边界

本章原理覆盖 PostgreSQL 14–18；可执行 baseline 固定 `pg_trgm` 1.6、
`vector` 0.8.4，并在 PostgreSQL 18.4 上验证。实验使用英语配置，因为冻结
语料是英语。中文、多语言与混合字段不能照抄 `english`，应重新选择 tokenizer/
dictionary、语料和指标。

Pigsty 映射按 4.4 文档在 2026-07-29 核验。本地证据路径是直接 PostgreSQL，
没有冒充 Pigsty L1。当前 Pigsty 文档把 `pgvector` 列为默认安装包，把
`pg_trgm` 列为默认启用扩展；实际环境仍要检查目标版本、镜像/仓库和每个
主备节点。

权威入口：

- [PostgreSQL 18：全文检索导论](https://www.postgresql.org/docs/18/textsearch-intro.html)
- [PostgreSQL 18：控制文本搜索](https://www.postgresql.org/docs/18/textsearch-controls.html)
- [PostgreSQL 18：文本搜索索引](https://www.postgresql.org/docs/18/textsearch-indexes.html)
- [PostgreSQL 18：`pg_trgm`](https://www.postgresql.org/docs/18/pgtrgm.html)
- [pgvector 0.8.4 README](https://github.com/pgvector/pgvector/blob/v0.8.4/README.md)
- [Pigsty 4.4：默认扩展](https://pigsty.io/docs/pgsql/ext/extension/)

---

[上一章：博采众长：内核分支与扩展生态](/extensions-ecosystem/) · [返回上卷导读](/upper-volume/) · [下一章：经天纬地：时序、空间与时空查询](/spatiotemporal/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
