# ch05 实验合同

## 目的

本章不创建新的业务对象，而是在已经验收的 `ch04-v1` 模型上观察查询、快照、事务失败、WAL 与锁等待。所有业务写入都在事务中回滚；成功验收后，订单 `1002` 的指纹与 ch04 checksum 必须保持不变。

## 前置条件

- 数据库是明确可用于演练的 Pigsty L1 / 本地测试库；
- `PGSERVICEFILE` 指向权限为 `0600` 的私有 service file；
- service 默认名为 `pg36-admin`，登录角色可 `SET ROLE pg36_owner`；
- ch04-v1 已安装并通过 `static/labs/ch04/task.sh verify`；
- blocking 实验的控制连接有权查看所有相关会话，并取消自己启动的精确 PID。

## 动作与风险

| 动作 | 风险 | 行为 |
|---|---|---|
| `verify` | R0·观察 | 验证 ch04-v1、无残留 worker、样例 checksum |
| `observe` | R0·观察 | 读取当前会话、快照、tuple header 与 WAL 位置 |
| `transaction` | R2·受控演练 | 制造预期 SQLSTATE；写一行后回滚；观察 WAL 前进 |
| `blocking` | R2·受控演练 | 两个受控会话竞争订单 1002；取消精确 blocker PID 后双方回滚 |
| `all` / `review` | R2·受控演练 | 前验、三类实验、后验 |

这些动作不适合直接对生产主库执行。即使最后回滚，`UPDATE` 仍会取得行锁、制造 tuple/WAL 与统计活动；实验也会调用 `pg_cancel_backend`。生产调查应先用只读 SQL 和 Pigsty 面板观察，不应为了“看见阻塞”主动制造阻塞。

默认 blocking 实验同步完成后立即取证并释放，不依赖固定 sleep。若要让一个采集周期较长的 Pigsty dashboard 有机会采到现场，可显式设置 `PG36_DASHBOARD_HOLD_SECONDS=1..25`；这只是教学观察窗，会人为延长锁等待，不能用于生产。

## blocking 实验不变量

1. blocker 与 waiter 的 `application_name` 含本次唯一 run tag；
2. blocker 完成未提交 `UPDATE` 后进入 `PgSleep`；
3. 普通 `SELECT` 在 1 秒 statement timeout 内返回旧的已提交指纹；
4. waiter 的 `pg_blocking_pids(pid)` 精确指向 blocker，且 `wait_event_type=Lock`；
5. 控制连接只对刚刚解析并复核的 blocker PID 调用 `pg_cancel_backend`；
6. blocker 断开使事务回滚，waiter 获锁后也显式回滚；
7. 两个 worker 均退出、订单指纹恢复、ch04 checksum 不变。

## 证据

每次运行都写入独立证据目录：

- `manifest.txt`：时间、版本与资产 SHA-256；
- `observe.txt`：会话、快照、tuple header 与 WAL 三个位点；
- `transaction-errors.stderr`：稳定 SQLSTATE `22012`、`25P02`、`23514`；
- `wal-rollback.txt`：写事务 XID、前后 LSN、观察到的 WAL 字节与状态复原；
- `blocking/activity.csv`：两个 worker 的状态、等待事件与 blocking PID；
- `blocking/locks.csv`：当时的 regular lock-manager 视图；
- `blocking/summary.txt`：读可见性、锁链、取消结果与最终不变量；
- `verify-before.txt` / `verify-after.txt`：实验前后状态摘要。

LSN 差值是这段窗口内实例的全局 WAL 活动，不能当作某一事务的精确“日志大小”；LSN 前进也不能证明事务提交。`pg_locks` 是瞬时观测，且不会把每个行锁都作为永久的 tuple 行展示，所以 blocker 的权威识别来自 `pg_blocking_pids()`。
