# 第 32 章实验合同

本实验只面向已确认的 Pigsty 四节点开发沙箱。它在 `pg-test` 的 `test` 数据库创建
marker 约束的 `pg36_ch32` 一次性 schema，执行一次新 full backup，并在
`pg-test-3` 的 `/data/pg36-ch32-restore/<run-id>` 下通过 `pig pitr` 创建两次 side
restore。它不覆盖 `/pg/data`，不暂停 Patroni，不修改 DCS、路由或真实服务。

## 事故模型

fixture 有 5,000 个账户。runner 随机选择连续 1,000 个 victim：

1. base backup 后提交一笔安全加款；
2. 同一错误事务把 1,000 个余额置零，并生成 1,000 条 fixture-only pending outbox；
3. 错误之后，100 个 victim 又收到合法加款；
4. source audit 保存错误事务 XID；外部消息 dispatch 永远关闭。

恢复目标不是脚本中的固定时间。runner 从 source audit 独立取得 damage XID，先故意
执行 inclusive XID PITR，证明错误事务也被重放并拒绝该候选；再执行 exclusive XID
PITR，证明安全事务存在，而 damage 与 post-target 合法事务都不存在。

## 选择恢复还是对账

直接把 exclusive candidate 切成生产，会丢掉 target 后 100 笔合法加款。实验不改
真实路由，而是从恢复候选提取 1,000 个历史正确余额，再加上 source audit 中的合法
post-target delta，通过条件更新修复一次性 fixture。最终要求：

```text
all victim rows repaired
all 100 legitimate post-target writes preserved
all wrong outbox events canceled
external dispatch count remains zero
business manifest equals independent expected value
```

## Side restore 隔离

每个候选都必须：

- 由 `pig pitr --plan` 先生成计划；
- 使用 custom `-D` 与 `--no-restart`；
- 指定 exact fresh backup、damage XID、`target-timeline=current`；
- 通过 pgBackRest `archive-mode=off` 禁止恢复分支回写 source repo；
- 手工以 `listen_addresses=''`、private mode-0700 Unix socket 启动；
- 使用 private HBA，只允许本机 `postgres` peer；
- 不加入 Patroni/DCS，不接触 HAProxy/PgBouncer/VIP；
- 完成验证后停止 postmaster，再按 marker 删除 exact root。

## 授权与清理

执行写入与 side restore 需要：

```text
PG36_CH32_TARGET=pg36-l2-vagrant/pg-test
PG36_CH32_NONPRODUCTION=true
PG36_CH32_PRODUCTION_DATA=false
PG36_CH32_PRODUCTION_TRAFFIC=false
PG36_CH32_CONFIRM=RANDOM_XID_PITR_RECONCILE_CH32
```

任一 guard 缺失都在 source mutation 前失败。正常结束会删除 fixture schema 与两个
side restore root；不会 expire 新 backup，因为删除 backup/WAL 不是本次授权的一部分。
失败清理也只匹配 exact run marker，绝不终止无关进程或删除宽泛目录。

## 证据与结论边界

时间测量拆成 target identification、plan、restore copy、replay、validation 和
reconciliation。它们来自小型共享沙箱，不能外推生产 RTO。原始 exclusive PITR 状态
缺少 100 笔 target 后合法写；对账后 fixture 数据损失为零，但这不证明真实业务的
外部副作用可补偿。

本实验不执行业务 cutover，不演练托管目录恢复，不证明 repository immutable、区域灾备
或 worst-case archive RPO。最终门禁固定为 `production_ch32_gate=pending`。
