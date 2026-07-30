# 第 33 章实验合同

本实验只面向已经确认的四节点 Pigsty 开发沙箱。它由三段互相独立的证据组成：

1. 在 `pg-test-1` 上执行一次受 guard 约束的 `systemctl stop patroni`，持续从
   `10.10.10.11:5433` 服务端点写入幂等 token，等待 `pg-test-2` 自动提升；
2. 重新启动 `pg-test-1`，证明它作为流复制副本归队，再用一次健康的 planned
   switchover 恢复 `pg-test-1` 为教学基线主库；
3. 在 `pg-test-3` 的 `/tmp/pg36-ch33-rebuild-<run-id>` 内创建三套一次性 PostgreSQL
   数据目录，真实执行一次 `pg_rewind` 和一次 `pg_basebackup` 重建。

## 管理集群故障模型

正式动作是 **controlled process fence**，不是主机断电、内核崩溃、磁盘损坏或网络
黑洞。`systemctl stop patroni` 必须完成后，runner 才接受以下 fence evidence：

```text
patroni service active          false
managed postmaster alive        false
Patroni REST endpoint reachable false
old member accepts SQL writes   false
```

只有旧主满足这些条件、`pg-test-2` 成为唯一 primary、`pg-test-3` 仍在 streaming，
才记 failover 成功。沙箱 watchdog 为 off，所以结论只能是“这个 runner 先完成了进程
围栏”；它不证明硬件 fencing。

客户端每 200 ms 尝试一次带唯一 token 的 autocommit INSERT。网络错误意味着结果
unknown，不能直接重试成另一个业务动作。演练结束后按 token 查表：

```text
acknowledged token exists exactly once
unknown token exists zero or one time and is reconciled
duplicate business token count is zero
```

RPO 报告只说明本次 synthetic token。异步复制、单次短实验和已知客户端路径都不能推出
生产 `RPO=0`。write gap 同时包含探测间隔、代理重路由、连接重建和数据库恢复，只是本次
端到端沙箱观测，不是生产 SLO。

## DCS 与网络故障边界

本环境只有一个 etcd 成员，真实停止它既不能代表多数派 DCS，也会抹掉要研究的
quorum 差异；无 watchdog 的共享虚拟机也不适合注入不对称网络分区。因此本章从六个
blind scenario 中随机抽取一个，只输出 evidence checklist 与 stop line：

- 不停止、重启或改写 etcd；
- 不删除 leader key、`/config` 或 `/failsafe`；
- 不修改防火墙、路由、DNS、VIP、HAProxy 或 PgBouncer；
- 不根据单个节点的“DCS 不可达”就手工提升；
- DCS 恢复后先核对 leader lock、Patroni REST 和 `pg_is_in_recovery()`，不盲目
  bootstrap 新控制面。

`failsafe_mode=true` 只允许 incumbent primary 在能联系 `/failsafe` 中**全部**已知成员
时继续服务；它不是多数派写入协议，也不是忽略 DCS 的开关。

## 隔离 `pg_rewind` 与全量重建

临时实验从 source A 做出 standby B。A 停止后，B promote 并写入新时间线；随后 B
停止，A 单独启动并写入分叉标记，再停止。两个分叉 primary **从不同时运行**。

B 重新启动后：

1. `pg_rewind --target-pgdata=A --source-server=B -R`；
2. A 以 standby 身份启动并追上 B；
3. B 的新标记必须存在，A 的分叉标记必须消失；
4. 另建空目录 C，用 `pg_basebackup -R` 从 B 全量复制；
5. C 必须作为 streaming standby 启动并看到 B 的新标记。

所有临时实例 `listen_addresses=''`，只创建 mode-0700 Unix socket；不注册 Patroni，
不接入 DCS、代理、备份仓库或业务路由。target 使用 checksums，且验证
`full_page_writes=on`。如果 rewind 中途失败，不能把 target 当作可启动副本，应改从
可信 source 做全量重建。

## 授权、复位与禁止动作

完整演练需要：

```text
PG36_CH33_TARGET=pg36-l2-vagrant/pg-test
PG36_CH33_NONPRODUCTION=true
PG36_CH33_PRODUCTION_DATA=false
PG36_CH33_PRODUCTION_TRAFFIC=false
PG36_CH33_CONFIRM=FENCE_FAILOVER_REJOIN_REBUILD_CH33
PG36_CH33_INVENTORY=/absolute/private/inventory.yml
```

inventory 必须是 mode 0600，只用于生成临时 libpq service 文件，密码不会写入 evidence。
任一 guard 缺失都在 mutation 前失败。runner 的失败处理只会：

- 若 `pg-test-1` 被本 run 停止，则尝试重新启动；
- 若当前唯一主库是 `pg-test-2` 且三成员均健康，则 planned switchover 回
  `pg-test-1`；
- 删除 exact `pg36_ch33` fixture；
- 停止并删除带本 run marker 的 exact 临时 rebuild root。

它不会执行 `patronictl reinit`、删除 managed PGDATA、修改 Patroni 动态配置、改 DCS
或切换生产路由。全量 reinit 是破坏性动作，只能在另行审批的目标成员上执行。

## 结论边界

本实验能够证明受控进程 fence、自动 promotion、旧成员自动归队、客户端 token 对账、
timeline 前进、`pg_rewind` 与 fresh base backup 的机制。它不证明真实断电/存储损坏、
多可用区 DCS、多数派分区、硬件 watchdog、最坏 RTO、生产数据零损失或 managed reinit。
最终门禁固定为 `production_ch33_gate=pending`。
