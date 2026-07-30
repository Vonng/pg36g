# 第 29 章实验合同

本实验只面向已确认的 Pigsty 四节点开发沙箱。源端是独立系统标识的 `pg-test`，
目标端是 `pg-meta`；实验只在两端创建带随机 `run_id` 标记的一次性数据库、角色、
publication、subscription 和 slot，不读取现有业务表，不修改平台路由，也不接入
生产流量。正式环境始终受 `production_ch29_gate=pending` 约束。

## 要回答的问题

1. 初始快照与随后发生的增量变更怎样汇合为一致状态？
2. subscription 停止消费时，源端 slot 怎样继续保留 WAL？
3. 显式 apply conflict 与不会报错的静默数据漂移分别怎样被发现和修复？
4. 为什么 sequence、DDL、凭据、写入围栏、回退窗口必须位于迁移状态机之内？
5. 怎样证明切换前后没有触碰真实 HAProxy、PgBouncer、DNS、VIP 或应用路由？

## 安全边界

- 两个数据库和五个角色必须同时匹配固定名称与本次随机 marker。
- 源端复制账号只获得 LOGIN、REPLICATION、CONNECT、schema USAGE 与 published
  table SELECT；源、目标运行账号使用不同凭据。
- 只允许暂停、恢复和删除 `pg36_shop_sub`，只允许删除 `pg36_shop_slot`。
- WAL 停滞负载有固定行数，不改变 `max_slot_wal_keep_size` 或任何集群参数。
- 冲突与静默漂移各只注入一个固定主键，并在继续切换前恢复双端 manifest。
- “切流”只修改私有证据目录中的 route history；不修改 Pigsty inventory、
  HAProxy、PgBouncer、DNS、VIP 或真实应用配置。
- 清理只使用普通 DROP。发现 marker 不符、存在无关会话或只能 force-drop 时失败关闭。

## 证据与结论边界

私有证据保存双端原始 manifest、分桶摘要、slot/LSN 样本、冲突统计、route history、
源文件散列和清理细节。公开文件只保留环境、数量、前后差异、验证结果与安全结论，
不含密码、conninfo、主机密钥或原始业务数据。

一次沙箱成功证明 PostgreSQL 18 原生逻辑复制状态机在这两个一次性数据库上可执行，
不证明生产数据量下的初始复制时长、WAL 预算、应用兼容、DDL 编排、网络加密、RTO、
RPO 或正式切换窗口已经获批。
