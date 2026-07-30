# ch14 扩展生命周期实验合同

## 目标

本实验不以“`CREATE EXTENSION` 成功”为验收标准，而是验证一条完整的扩展
治理链：

```text
问题与成功标准
  -> 软件包/控制文件可用
  -> 权限与预加载条件满足
  -> 数据库内创建并盘点成员
  -> 查询与索引行为成立
  -> 对象版本受控升级
  -> 升级后行为不变
  -> 备份依赖和可移植出口明确
  -> 精确复位
```

## 固定目标

- database：`pg36_shop`
- schema：`shop_ch14`
- owner：`pg36_owner`
- application role：`pg36_app`
- application name 前缀：`pg36-ch14-`
- PostgreSQL：14–18；正式证据在 Homebrew PostgreSQL 18.4 采集
- PostgreSQL 扩展：`pg_trgm` 1.3 → 1.6，`vector` 0.8.4
- Pigsty：正文映射到 4.4；本地证据路径是直接 PostgreSQL，不伪装为 L1

实验只会接管带精确 marker 的 `shop_ch14`、`pg_trgm` 与 `vector`。只要
发现同名扩展位于别的 schema、缺少 marker，或 schema 含有未知非扩展对象，
脚本就拒绝清理和重建。

## 三项 ADR 结论

| 候选 | 结论 | 本章理由 |
|---|---|---|
| `pg_trgm` | accept | 解决边界明确的单字段容错检索；原生 contrib、受信任、GIN 可验证、退出容易 |
| `vector` | pilot | 能提供向量类型与 ANN 索引，但模型、质量、维度、延迟和数据出口尚需场景证据 |
| `citus` | reject | 当前没有测得的分布式容量问题和分片键合同；拒绝的是过早引入，不是否定产品 |

## 要证明的关系

1. `pg_available_extension_versions` 同时说明版本可用性与
   `superuser/trusted/relocatable` 属性；
2. `pg36_owner` 能创建受信任的 `pg_trgm`，并成为扩展 owner；
3. 同一角色创建未受信任的 `vector` 返回 `42501`，管理员创建后扩展 owner
   保持超级用户；
4. `pg36_app` 能查询被授权的表，但不能 `ALTER EXTENSION`，后者返回
   `42501`；
5. `pg_trgm` 1.3 到 1.6 的更新路径存在，更新前后模糊检索结果均为
   `1,5,2`；
6. 向量 L2 检索结果为 `1,2,5`，强制计划能够分别看到 GIN 与 HNSW；
7. `pg_depend.deptype = 'e'` 能盘点扩展成员，普通 schema 所有权并不代表
   “扩展对象都属于 schema”；
8. 全库 schema-only dump 记录 `CREATE EXTENSION`，却不逐一展开成员对象；
   带 `--schema` 的选择性 dump 不自动带上依赖扩展；
9. 向量可以先转为文本导出，为试点退出保留一个明确但仍需演练的通道。

## 不能由本地实验替代的事实

- Pigsty 软件仓库、缓存与所有 L1 节点是否拥有同一构建；
- 真实查询分布下的召回率、P95/P99 延迟、内存、WAL 与副本延迟；
- 物理备库启动是否能加载相同动态库；
- 逻辑订阅端是否拥有兼容类型与扩展；
- `pg_upgrade` 前后动态库是否二进制兼容；
- 生产备份在洁净恢复环境中是否完整恢复。

这些事实必须分别在目标 Pigsty 集群、候选数据集、备库和恢复演练中采集，
不能由本地五行 fixture 代替。

## 复位边界

`reset` 必须同时提供：

```text
PG36_RESET_TOKEN=RESET_CH14_EXTENSION_LAB
PG36_RESET_TARGET=pg36_shop/shop_ch14/pg_trgm+vector
```

脚本还会核对 database、writable instance、角色、schema/extension marker、
版本、对象白名单与活跃 worker。删除顺序为业务表、`vector`、`pg_trgm`、
schema，全部使用 RESTRICT 语义，不使用 `CASCADE`。
