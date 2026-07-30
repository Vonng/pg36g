# ch16 时空查询实验合同

## 目标

本实验要证明的不是“PostGIS 能画一个点”，而是完整、可重复的时空决策链：

```text
冻结写入尝试、围栏版本与配送中心
  -> 分离事件时间、接收时间与有效时间
  -> 去重后按 UTC 事件时间路由到原生分区
  -> 固定 EPSG:4326 与 geometry/geography 职责
  -> 验证边界、距离、围栏换版和时空联合查询
  -> 对照可裁剪与不可裁剪谓词、GiST 与 SP-GiST 计划
  -> 固定权限、对象依赖、发布证据与精确退出
```

## 固定目标

- database：`pg36_shop`
- data schema：`shop_ch16`
- extension schema：`shop_ch16_ext`
- owner：`pg36_owner`
- application role：`pg36_app`
- PostgreSQL：14–18；正式本地证据在 18.4 采集
- 扩展：PostGIS 3.6.4 与 `btree_gist` 1.8
- Pigsty：正文映射到 4.4；本地直连路径不伪装为 L1
- fixture：13 次写入、12 个唯一事件、4 个围栏版本、3 个配送中心
- 坐标：项目自造 EPSG:4326 数据，不含外部地图或模型许可

setup 只接管 owner、marker、扩展版本、扩展 owner 和对象依赖全部精确匹配的
两个 schema。失败会由单事务整体回滚。PostGIS 是非 trusted、不可迁移扩展，
因此由管理员创建；trusted 的 `btree_gist` 由 `pg36_owner` 持有。

## 时间口径

- `occurred_at`：业务事件实际发生时刻，也是分区键。
- `received_at`：本次尝试被系统接收的时刻，用于迟到、乱序和重放审计。
- `valid_during`：围栏版本的业务有效时间，统一为 `[from, to)`。
- UTC 决定分区边界；用户时区只用于输入解析与展示。
- `e002` 与 `e003` 在纽约本地显示为 01:55 与 03:05，但实际只相隔 600 秒；
  不能用本地墙上时间做绝对时长运算。

## 空间口径

- 所有原始点与面是 `geometry(..., 4326)`；不同 SRID 的运算必须失败。
- 米制距离使用 `geography`；EPSG:4326 geometry 的距离单位是角度。
- 围栏归属使用 `ST_Covers`，因此边界点计入；`ST_Contains` 的边界语义不同。
- `ST_DWithin`、`ST_Covers` 等命名谓词会先使用包围盒索引条件，再执行精确
  判断。`<->` 最近邻与过滤谓词不能混成一个模糊的“空间索引更快”结论。

## 固定事实

| 事实 | 预期 |
|---|---|
| 写入尝试 / 唯一事件 | 13 / 12 |
| 重复事件 | `e003:2` |
| 三个 UTC 日分区 | 1 / 7 / 4 |
| 迟到超过 5 分钟 | `e001,e004` |
| 围栏命中 | 14 |
| 3 月 8 日 central | `e002,e003,e005,e006,e008` |
| 混合 SRID | SQLSTATE `XX000` |
| 重叠有效期 | SQLSTATE `23P01` |
| 应用写入 | SQLSTATE `42501` |
| 业务校验和 | `53f51cef1f0bed1a5c2fc89bfad109f4` |

## 执行计划口径

直接对 `occurred_at` 写半开范围时，只访问 3 月 8 日分区；把分区键包在
`AT TIME ZONE ... ::date` 中时，三张分区都被扫描。空间计划暂时关闭
`enable_seqscan`，只用于证明 GiST/SP-GiST 路径可用。fixture 太小，正常规划器
选择顺序扫描是合理的，强制计划不能证明索引更快。

生产发布必须另测代表性规模下的 P50/P95/P99、吞吐、WAL、索引构建、缓存、
vacuum、分区维护、备份恢复、副本延迟与空间选择率，并验证每个 Pigsty L1
节点的包和扩展版本一致。

## 复位边界

reset 必须同时提供：

```text
PG36_RESET_TOKEN=RESET_CH16_SPATIOTEMPORAL_LAB
PG36_RESET_TARGET=pg36_shop/shop_ch16+shop_ch16_ext
```

脚本会先执行完整 `verify.sql`，再核对活跃 worker。所有 DROP 都在一个事务中
按视图、表、数据 schema、扩展、扩展 schema 的依赖顺序执行，不使用
`CASCADE`，并保留第 14 章的 `pg_trgm` 与 `vector`。
