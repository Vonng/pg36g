# 第 30 章实验合同

本实验只面向已确认的 Pigsty 四节点开发沙箱。它把 `pg-meta` 节点当作执行主机，
但不接触该节点上由 Pigsty 管理的 PostgreSQL 数据目录、服务、路由或配置。实验使用
两个版本的官方 PostgreSQL 二进制，在随机 marker 约束的 `/tmp` 私有目录内创建
Unix-socket-only 临时集群，并在结束时精确删除。

## 要回答的问题

1. 为什么升级门禁必须先发现 collation version 漂移，再按“重建依赖对象、刷新版本”
   的顺序修复？
2. `pg_upgrade --check` 能拒绝哪些集群级不兼容条件，哪些业务语义仍需另行验证？
3. `--copy` 模式完成升级后，怎样证明新集群尚未接收写入时旧集群仍能启动？
4. 第一笔目标独占写入为什么会把“直接回退”改成“先对账再回退”？
5. 怎样证明实验没有安装包、开放 TCP、修改 Pigsty inventory、Patroni 或真实数据？

## 二进制前置条件

runner 不下载、不安装软件。调用者必须在维护窗口之外准备：

- PostgreSQL 17 的 `bin` 目录；
- 与该二进制匹配的 `share` 目录，供私有 `initdb -L` 使用；
- PostgreSQL 18 的 `bin` 目录。

`capture` 会记录版本、可执行文件 SHA-256、share 标识、平台架构和可用空间，并要求
17→18 的 major 关系成立。正式参考 run 使用 PGDG PostgreSQL 17.10 解包文件和
沙箱已安装的 PostgreSQL 18.4；这些 minor 号不是读者环境的固定要求。

## 安全边界

- 临时 postmaster 使用随机目录下权限为 `0700` 的 Unix socket；
- `listen_addresses` 固定为空，不开放 TCP；
- fixture 只有 `pg36_upgrade.app.orders` 的 10,000 行确定性合成数据；
- catalog 注入只允许修改该 fixture 中 `app.en_numeric` 的 `collversion`；
- 不兼容目标只用 `--no-data-checksums` 初始化并运行 `pg_upgrade --check`；
- 正式升级只允许 `pg_upgrade --copy`，禁止 link、clone、swap、no-sync；
- 不执行 `delete_old_cluster.sh`，也不读取 Pigsty 现有业务 database；
- rollback proof 必须发生在新集群任何独占写入之前；
- 清理前逐一证明所有临时 postmaster 已停止，路径与随机 marker 匹配。

## 证据与结论边界

私有证据保留 preflight、升级检查日志、升级日志、对象与配置 manifest、collation
依赖、前后查询计划、`amcheck` 结果、回退与清理记录。公开摘要不包含本地路径、用户
凭据或 managed cluster 的连接信息。

一次沙箱成功证明 17→18、`--copy`、当前架构和当前 fixture 的状态机可执行；它不证明
真实数据量下的停机时长、扩展二进制兼容、应用驱动行为、备份恢复、HA 拓扑、业务峰值
或生产发布已经获批。正式决策始终受 `production_ch30_gate=pending` 约束。
