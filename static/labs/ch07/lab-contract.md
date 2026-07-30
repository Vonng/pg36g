# ch07 计划与统计实验合同

## 目标

在专属 fixture 中可重复证明三件事：

1. 单列统计无法描述 `region` 与 `order_status` 的跨列相关，扩展统计显著改善估算；
2. 倾斜参数下 custom plan 与 generic plan 看到的选择率不同，计划差异本身不等于回归；
3. 分区裁剪可发生在规划期或执行期，包裹分区键的条件可能让裁剪失效，父表统计需要显式 `ANALYZE`。

## 持久对象

- `shop_private.ch07_plan_probe`
- `shop_private.ch07_event_probe` 及四个季度分区
- `shop_private.ch07_region_status_stats`

对象带固定 comment marker。若同名对象存在但 marker 不匹配，`setup` 与 `reset` 都会拒绝。

## 风险

- `setup`：R1，可逆地重建上述专属 fixture，写入 100000 + 3650 行；
- `stats` / `parameters` / `partition`：R1，执行只读查询并更新专属对象统计；
- `EXPLAIN ANALYZE`：真实执行 SELECT，会消耗 CPU、buffer 与 I/O；
- `reset`：R2，只删除上述专属对象，要求两个精确 token；
- 不允许在生产库照搬 100000 行 fixture 或 `ANALYZE`/`auto_explain` 参数。

## 稳定验收与动态证据

稳定验收：

- correlated-present estimate 在扩展统计后显著接近 25000；
- impossible combination estimate 显著下降；
- custom plan 正确区分 90000-row hot tenant 与 10-row cold tenant；
- forced generic plan 对两个参数使用同一估算；
- constant condition 只含一个 partition，wrapped condition 含四个；
- generic parameter 在初始化/执行阶段只执行一个 partition；
- 父表 `pg_stats` 从 0 变为非零；
- ch04-v1 业务 relation checksum 前后不变。

动态证据：

- exact cost/time/buffers；
- Seq/Index/Bitmap 的具体节点选择；
- sample-derived histogram bounds；
- plan JSON 的版本新增字段。

动态值保存在 evidence，但不做跨硬件/版本 golden。
