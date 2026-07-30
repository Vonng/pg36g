# ch09 索引设计实验合同

## 教学目标

从已证明的访问模式推导、验证并审查索引，而不是按字段直觉堆叠：

1. 订单：少量 `placed` 订单的 customer + Top-N 查询；
2. 库存：现有 `(warehouse_id, sku_id)` 主键与反向 SKU 查询；
3. 搜索：全文检索的 GIN，而不是无边界的“万能 JSONB 索引”；
4. 事件：物理时间相关大表上的 BRIN/B-tree 空间与访问对照；
5. 写路径：被更新列是否进入索引对 HOT 与 WAL 的影响；
6. 发布：并发唯一索引失败留下 INVALID index 的识别与回收。

## 前置条件

- ch04-v1/ch05 rollback-only 验收通过；
- 只在已确认可写、可重建的 L1/本地 PostgreSQL 运行；
- PostgreSQL 14 或更新；
- 每个对象带固定 marker，碰到同名非本章对象必须拒绝；
- 所有 session 使用 `pg36-ch09-*` application identity。

## 专属对象

只在 `shop_private` 创建：

```text
ch09_order_probe
ch09_inventory_probe
ch09_search_probe
ch09_event_probe
ch09_write_base
ch09_write_indexed
ch09_unique_probe
```

`setup` 会在 marker 完全匹配后重建，属于 R1。`reset` 删除这些对象，
属于 R2，要求 action/target 双 token。业务 schema 不增加索引。

## 稳定断言

- order literal/custom plan 使用 partial covering index，generic status
  parameter 不能证明 predicate；
- order index-only scan 在 VACUUM 后 `Heap Fetches=0`；
- inventory reverse index 支持 SKU lookup，不能以 PG18 skip scan
  是否出现作为跨版本 golden；
- search query 使用专属 GIN，目标结果恰为 100；
- event BRIN 与 B-tree 均能支持同一范围，BRIN 明显更小；
- 无 volatile index 的 write table 产生高 HOT ratio；有该 index 的
  对照 HOT 为 0 且 WAL 更多；
- 并发 unique build 必须以 SQLSTATE 23505 失败、观察到 INVALID，
  精确 drop 后残留为 0；
- rejected event B-tree 在保存 size/plan 后精确移除；
- final worker=0、所有保留索引 valid、ch04-v1 checksum 不变。

节点名、cost、elapsed、buffer 数量、WAL 字节与 PID 不作为固定 golden。
只有机制关系、结果行数、catalog validity、对象集合与状态复位进入验收。

## 生产边界

本章自动化不在生产执行：

- 不为调查创建/删除生产索引；
- 不执行全局 statistics reset；
- 不强制 planner GUC 作为长期修复；
- 不自动 drop “unused” index；
- 不在未知事务、磁盘或 replica lag 条件下启动 concurrent build；
- 不把实验阈值当所有硬件/版本的 SLO。

生产候选必须另行评估锁、两个 table scan、CPU/I/O、WAL、复制延迟、
长事务等待、唯一语义、磁盘峰值、失败残留、监控窗口与回退。
