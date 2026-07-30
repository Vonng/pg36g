# 第 35 章实验合同

本章在线 managed `pg-test` 只做 L0 read-only capture。所有 byte-level 与 catalog-level
mutation 都发生在 `pg-test-3` 的
`/tmp/pg36-ch35-forensics-<run-id>` 私有一次性目录。

## 原始证据与操作副本

runner 创建启用 data checksum 的 PostgreSQL 18.4 fixture，干净停止后制作 known-good
snapshot。每个场景从它创建独立 case copy；恢复工作在另一份 working copy 上进行。
原始 case copy 在最终 exact-root cleanup 前不再写入。

临时实例：

```text
listen_addresses=''
private mode-0700 Unix socket
data_checksums=on
not in Patroni, DCS, HAProxy, PgBouncer, backup repository, or business route
```

## 两个盲场景

runner 随机安排两个不含语义的 case ID。classifier 只读 blind packet，不读 hidden truth。

### Physical heap page

只在 stopped case clone 上，对已知 fixture heap 的 block 2 内一个 byte 做 XOR one-bit。
证据必须同时显示：

```text
checksums enabled
offline pg_checksums reports at least one bad checksum
sequential online scan fails
relation kind is heap
no collation mismatch
```

该 case 不做原地修复。runner 从 known-good stopped snapshot 新建 recovery copy，并验证
checksum、`amcheck` 与四项业务不变量。

### Collation-derived state

只在 disposable case clone 内，通过明确开启的 `allow_system_table_mods` 把 exact ICU
collation version metadata 改为 run-specific fake version。它模拟 metadata mismatch，
不声称模拟真实 ICU 排序语义变化。证据必须显示：

```text
offline checksums clean
stored version differs from pg_collation_actual_version
exact B-tree passes structural amcheck
relation kind is index-derived
```

runner 保留 mutated case，另建 working copy；先 `REINDEX` exact dependent index，再
`ALTER COLLATION ... REFRESH VERSION`，然后验证 checksum、amcheck、version 与业务
不变量。

## 明确禁止

实验不会：

- 修改 managed PGDATA、PostgreSQL、Patroni、DCS、服务或路由；
- 在 running server 上修改 relation file；
- 在唯一来源上注入故障或反复试错；
- 删除 `pg_wal`、relation 原始损坏文件或 forensic evidence；
- 启用 `ignore_checksum_failure`、`zero_damaged_pages`；
- 执行 `pg_resetwal`；
- 执行 managed `reset:host`。

错误动作只做 counterfactual 验证，不实际执行。

## Guard 与复位

完整实验要求：

```text
PG36_CH35_TARGET=pg36-l2-vagrant/pg-test
PG36_CH35_NONPRODUCTION=true
PG36_CH35_PRODUCTION_DATA=false
PG36_CH35_PRODUCTION_TRAFFIC=false
PG36_CH35_CONFIRM=CLONE_CLASSIFY_RECOVER_CH35
```

任一 guard 缺失都在远端目录创建前失败。最终只在 marker 与 exact UUID path 匹配、
所有临时 postmaster 已停止后删除整个 disposable root。

`reset:host` 在本书中是“宿主机基线已不可相信时，从声明式 inventory 与可信备份重建
整台 L3”的风险类别，不是一条可以复制粘贴的普通命令。本实验只产出重建 decision
contract，`managed_reset_host_executed=false`，生产必须另行审批。

## 结论边界

本实验可证明两类人工构造的 isolated PG18 evidence 可被 blind classifier 区分，并证明
从 clean copy 恢复与“REINDEX 后 REFRESH”机制。它不证明真实控制器/内存/文件系统
故障、真实 ICU 语义升级、生产数据可恢复范围或 Pigsty host rebuild 时长。最终门禁为
`production_ch35_gate=pending`。
