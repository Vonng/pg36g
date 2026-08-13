---
title: 事故症状与首个安全动作
linkTitle: 事故症状与首个安全动作
weight: 40
type: docs
breadcrumbs: true
comments: false
book_kind: index
search_keywords: [事故, 应急, 故障, 恢复, 切换, 取证, 首个安全动作]
search_boost: 1.5
---

> 先按症状选择“首个安全动作”，再进入正式章节。症状相似不代表修复动作相同。

| 症状或场景 | 首个安全动作 | 目标章节 | 明确禁止 |
|---|---|---|---|
| 误删、误更新、错误 DDL | 停止继续写入并确定影响时间窗 | [ch32《PITR 与误操作恢复》](/pitr/) | 不覆盖仍可取证的原集群 |
| 主节点、复制或 DCS 异常 | 保护旧主并核对角色、时间线与 DCS 事实 | [ch33《故障切换与集群重建》](/failover-rebuild/) | 不在未 fencing 时提升第二个主库 |
| 连接、延迟、CPU、内存、I/O 表象 | 先判流量型还是保留型 | [ch34《过载保护与资源故障判型》](/overload-resource-incidents/) | 判型前不做破坏性清理 |
| XID 回卷风险 | 检查 `backend_xmin`、复制槽 `xmin`、`pg_prepared_xacts` | [ch28《VACUUM、冻结与膨胀治理》](/vacuum-freeze-bloat/)、[ch34《过载保护与资源故障判型》](/overload-resource-incidents/) | 不用一般摘流代替解除保留 |
| WAL 撑满磁盘 | 检查归档失败、复制槽和未完成备份 | [ch21《备份体系与恢复演练》](/backup-recovery/)、[ch34《过载保护与资源故障判型》](/overload-resource-incidents/)、[ch35《数据抢救与工程取证》](/data-rescue-forensics/) | **绝不手工删除 `pg_wal`** |
| checksum、索引、collation 或逻辑不一致 | 停写、克隆并保存原始证据 | [ch35《数据抢救与工程取证》](/data-rescue-forensics/) | 不在唯一副本上反复试错 |
