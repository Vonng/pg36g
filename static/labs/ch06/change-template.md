# 数据库变更说明模板

## 身份

- Change ID：
- Owner：
- Reviewer：
- Target environment：
- Planned window：
- Expiry / cleanup date：
- Related application release：

## 目标与非目标

- 要改变的业务/运行事实：
- 明确不在本次范围内的事项：
- 成功后的可观察状态：

## 当前事实

- PostgreSQL / Pigsty / OS 版本：
- database / cluster / instance：
- relation size、row count、write rate：
- 当前 schema version 与 checksum：
- 当前依赖方与兼容窗口：

## 迁移设计

- expand：
- backfill：
- validate：
- switch read/write path：
- contract：
- idempotency / rerun behavior：

## 锁、WAL、容量与时间预算

- 预期 lock mode 与取得阶段：
- `lock_timeout` / `statement_timeout`：
- WAL、temporary space 与 replica lag 预算：
- 最老 transaction / snapshot 停止线：
- 可接受的 service impact：

## 失败与恢复

- 执行前备份/PITR 证据：
- 哪一步仍可 transaction rollback：
- 哪一步只能 forward repair：
- application rollback 与 schema compatibility：
- outcome ambiguous 时怎样确认：

## 验证

- precheck：
- positive cases：
- negative cases / expected SQLSTATE：
- catalog/runtime checks：
- post-state checksum：
- monitoring time range：

## 风险

- 风险级别：R0 / R1 / R2 / R3
- 最大可信故障：
- 停止条件：
- 审批人：
