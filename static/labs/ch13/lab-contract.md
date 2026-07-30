# ch13 数据库端逻辑实验合同

## 目标

本实验不以“能创建函数和触发器”为成功标准，而是验证逻辑放置决策：

```text
单行合法域               -> CHECK
旧行到新行的状态跃迁     -> BEFORE ROW trigger
事务最终时的跨表一致性   -> deferred constraint trigger
应用可调用的窄命令接口   -> SECURITY DEFINER function
允许分批提交的维护入口   -> top-level CALL + procedure
跨系统副作用与调度       -> 留在应用或平台
```

## 固定目标

- database：`pg36_shop`
- schema：`shop_ch13`
- owner：`pg36_owner`
- application role：`pg36_app`
- application name 前缀：`pg36-ch13-`
- 依赖：ch04-v1 数据模型与 ch05 稳定业务 checksum
- PostgreSQL：14–18；正式证据在 18.4 采集

实验只创建带精确 marker 的 `shop_ch13` 对象，不修改 `shop.*` 业务表。
应用角色对实验表没有 DML 权限，只能执行三个经过审计的函数。

## 要证明的关系

1. 七个状态的 49 个有序对中，恰好六条边合法；非法跳转返回 `P3613`；
2. `paid` 与捕获金额在事务提交点一致；无支付进入 paid 或删除已捕获
   payment 都返回 `P3614`；
3. 乐观版本前置条件失败返回 `P3616`；
4. 支付命令前置条件失败返回 `P3618`；
5. 应用直接更新表返回 `42501`；
6. 行级触发器处理每一行，带 transition table 的语句级触发器为三行批量
   更新只写一条 statement audit；
7. `EXCEPTION` 块回滚内部持久化修改，同时保留局部变量与外层流程；
8. 带 `COMMIT AND CHAIN` 的过程在显式事务块内返回 `2D000`，顶层
   `CALL` 则按 `2/2/1` 三批提交五行，第二次调用处理零行；
9. `pg_proc`、`pg_trigger`、ACL 和 `pg_stat_xact_user_functions` 为声明、
   权限与调用事实提供原始证据。

## 不能由本地实验替代的事实

- 真实生产吞吐、尾延迟、锁等待、WAL 和副本延迟；
- 连接池路径下的会话状态与事务控制行为；
- 跨系统消息是否被消费者处理；
- 调度器是否按时、去重、补偿和告警；
- 所有并发写入口是否遵守同一锁顺序。

这些事实必须在实际 Pigsty L1 环境中另行观测，不能由本地成功输出伪造。

## 复位边界

`reset` 必须同时提供：

```text
PG36_RESET_TOKEN=RESET_CH13_ROUTINE_GUARD
PG36_RESET_TARGET=pg36_shop/shop_ch13
```

脚本还会核对 database、writable instance、owner、schema/object marker、
对象白名单与活跃 worker。删除使用精确对象清单和 `DROP SCHEMA`
RESTRICT 语义，不使用 `CASCADE`。
