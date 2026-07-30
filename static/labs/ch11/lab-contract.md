# ch11 模式发布实验合同

## 教学目标

把“在线 DDL”改写成可验收的发布状态机，而不是一组看似安全的命令：

```text
legacy
  -> expanded
  -> backfilling
  -> migrated
  -> validated
  -> switched
  -X-> contract（缺少真实观察证据时拒绝）
```

实验分别证明：

- 元数据 fast path 不等于无锁；`ADD COLUMN` 仍可能因
  `ACCESS EXCLUSIVE` 锁预算耗尽而以 `55P03` 失败；
- non-volatile constant default 使用 missing-value 元数据，volatile
  default 改写 50,000 行并产生更高 WAL；
- 旧写入、新双写与表示不一致反例在同一兼容窗口内闭合；
- 回填批次与 checkpoint 原子提交，受控中止返回 `75`，随后精确续跑；
- `NOT VALID`、`VALIDATE CONSTRAINT` 与 `SET NOT NULL` 分阶段完成；
- 预验证 `CHECK` 后的 `ATTACH` 锁关系，以及 PostgreSQL 14+
  `DETACH PARTITION CONCURRENTLY` 的事务边界和数据保留语义；
- 本地实验不能伪造生产观察窗口，因此最终保留旧列与兼容桥。

## 固定目标

- database：`pg36_shop`
- effective role：`pg36_owner`
- schema：`shop_private`
- fixture 前缀：`ch11_`
- application name 前缀：`pg36-ch11-`
- 依赖：ch04-v1 模型与 ch05 稳定业务 checksum

每个写入口先验证 database、writable instance、role、`search_path`、
模型版本和 fixture marker。实验不修改 `shop.*` 业务表。

## 可自动证明与不可伪造的边界

本地 suite 可以自动证明锁图、SQLSTATE、目录状态、数据一致性、WAL
相对关系、checkpoint、重跑和最终 checksum。它不能证明：

- 真实生产流量下的 tail latency；
- 主从之间的复制延迟及 slot/WAL retention；
- 磁盘、CPU、IO、连接池和 HAProxy 水位；
- 所有旧应用实例、离线任务和临时脚本已经退出；
- 约定的 rollback observation window 已经过去。

因此 `contract-gate.sql` 要求精确动作令牌、精确目标和外部观察凭证。
默认 `all` 故意不提供这些输入，并断言 `P3612` 与旧结构仍在。

## 中止、复位与证据

- 单批回填与 checkpoint 在同一事务；失败时两者一起回滚；
- `--max-batches=2` 是受控停止线，返回 `EX_TEMPFAIL=75`；
- `CREATE/DROP INDEX CONCURRENTLY` 与
  `DETACH PARTITION CONCURRENTLY` 均由事务块外的独立入口运行；
- `reset` 需要
  `PG36_RESET_TOKEN=RESET_CH11_RELEASE_LAB` 与
  `PG36_RESET_TARGET=pg36_shop/shop_private/ch11`；
- reset 在存在 `pg36-ch11-*` worker 或对象 marker 不匹配时拒绝；
- evidence 保存 manifest、原始 stderr/CSV/JSON、最终校验和 proposal。

计时值只记录，不作为跨机器 golden。验收比较的是状态关系与不变量。
