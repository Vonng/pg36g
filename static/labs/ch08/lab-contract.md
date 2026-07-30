# ch08 慢查询诊断实验合同

## 教学目标

从同一个用户现象“请求迟迟不返回”中区分三类根因：

1. **估算/路径问题**：backend 正在执行，参数选择率与计划估算严重偏离；
2. **锁等待**：backend 为 active，但 `wait_event_type=Lock`，存在可证明 blocker edge；
3. **客户端慢消费**：backend 为 active，但 `wait_event_type=Client`、
   `wait_event=ClientWrite`，数据库在等待客户端接收结果。

诊断顺序必须是范围与时间窗 → activity/wait → query family/参数 →
计划与资源 → 单变量反证。不得先看见“慢”就建索引或取消任意 PID。

## 前置条件

- 已完成 ch04-v1；
- ch05 rollback-only 业务状态验收通过；
- ch07 planner fixture 已通过或由本章 setup 受控重建；
- 只在已确认可演练的 L1/本地 PostgreSQL 运行；
- 每个 worker 使用唯一 `application_name`，清理必须匹配
  PID + backend_start + database + application name。

## 三个 fixture 的边界

### estimate

- 复用 ch07 的 90000/10 tenant skew；
- 保存 generic/custom machine-readable plan；
- 不以 Seq/Index 节点名判定，只以 estimate/actual、buffers 与对照解释；
- 不修改业务表。

### lock

- 复用订单 1002 的 rollback-only update；
- blocker、waiter、observer 由明确同步条件编排；
- 只取消本实验精确 blocker，waiter 最终 rollback；
- 前后业务 fingerprint/checksum 必须一致。

### client

- 只生成 `generate_series` 派生的大结果，不读业务数据；
- 通过受控慢 reader 制造 socket backpressure；
- 必须观察 `Client/ClientWrite` 后取消精确实验 backend；
- 不能把普通 idle session 的 `ClientRead` 误判为慢客户端。

## Mystery 模式

- `PG36_CASE_SEED` 经 SHA-256 映射到三种 case；未提供时生成并记录 seed；
- ground truth 写入 mode 0600 的独立 answer artifact；
- 诊断器只读取公开 evidence，不读取 answer；
- `reveal` 在诊断完成后比较 classification 与 ground truth；
- 相同 seed 必须重现相同 case，便于教学复盘；
- 随机化只隐藏根因，不改变 target、风险或清理权限。

`0600` 只防止正常步骤误读答案，不构成同一 OS 用户之间的加密隔离；
知道源代码与 seed 的参与者仍可计算选择结果。教学纪律是先保存假设，
再运行 `diagnose`，最后 `reveal`。

## 证据包

最少包含：

```text
UTC start/end
service/database/user/application/PID/backend_start
activity snapshots + blocking edges
query shape + representative parameter
plan JSON + estimate/actual/buffers/settings
client/server versions
source hashes
hypothesis tree + rejected alternatives
before/after business checksum
classification + sealed reveal result
```

## 稳定验收

- estimate case：无 Lock/ClientWrite，cardinality error 越过阈值，custom 对照改善；
- lock case：waiter 精确指向 blocker，wait event 为 Lock，释放后前进；
- client case：无 blocker，wait event 精确为 ClientWrite，取消后 worker 清零；
- 诊断器在不知道 answer 的情况下三类各测试一次均分类正确；
- mystery seed 可复现，错误猜测不会被脚本伪装为通过；
- 所有 case 后 `active_lab_workers=0`，ch04-v1 checksum 不变。

## 运行入口与风险

```bash
export PGSERVICEFILE=/absolute/private/path/pg_service.conf
export PGSERVICE=pg36-admin
export PG36_EVIDENCE_DIR="$PWD/evidence/ch08/all-$(date -u +%Y%m%dT%H%M%SZ)"
./task.sh all
```

- `setup/all/review` 在 ch07 fixture 缺失时会通过 marker guard 受控重建，
  属于已确认 L1 上的 R1；
- estimate 只读持久数据，plan mode 仅在 session 内生效；
- lock 的写入全部 rollback；
- client 只生成派生结果，并以 PID + backend_start + database +
  application identity 精确取消自己的 worker；
- 本章没有持久 ch08 对象，因此没有删除式 reset；
- `diagnose/reveal` 可以离线复用同一 evidence 目录，不需要数据库连接。

## 不在本章自动执行

- 生产 query cancellation；
- 全局 `pg_stat_statements_reset()`；
- 在生产启用或调低 `auto_explain` 阈值；
- 修改 Pigsty/PgBouncer/HAProxy 配置；
- 清理非本章创建的会话、日志或 evidence。
