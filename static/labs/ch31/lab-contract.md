# 第 31 章实验合同

本实验面向已确认的 Pigsty 四节点开发沙箱。`capture` 只通过 `pg-test` service、
三个 Patroni REST 端点和 `pgBackRest info` 获取只读、最小化的现场基线；`exercise`
在本机离线运行桌面推演。它不会注入真实故障，不会暂停 Patroni，不会切换主节点、
重启服务、终止连接、改变路由、恢复备份或写入数据库。

这里的 “Pigsty L3” 指 Pigsty 文档中的 `FULL` 监控接入层级，不是变更风险级别。
本实验的在线风险始终是 `L0-read-only`。

## 要回答的问题

1. 严重度为什么只决定响应节奏，不能替代 PITR、HA、过载和完整性判型？
2. 首发告警为什么只能作为线索，不能直接授权重启、提升或删除 WAL？
3. 前十五分钟怎样同时保护用户、恢复能力和证据，而不是急于证明根因？
4. 单人值守与团队响应如何使用同一决策日志，但采用不同的角色实现？
5. 证据包怎样证明来源、时间和完整性，同时避免收集原始 SQL、日志和凭据？

## 盲抽方式

场景库包含八个案例，每条技术路线各两个。每个案例都有：

- 一个信息不足且可能误导的首发症状；
- 可按问题请求的证据卡；
- 必须先获得的关键证据；
- 安全的第一动作、危险动作、停止线和升级条件；
- 唯一的主要路由与当前响应目标。

`task.sh all` 使用固定 seed 生成一份可审计的参考 run；它证明场景引擎、响应合同和
validator 可工作，不证明任何真人已具备应急能力。真正演练时，由主持人保管
`facilitator-pack.json`，只把 `blind-packets.json` 和 `response-template.json`
交给参与者。

## 现场采集边界

PostgreSQL 查询显式执行在 `READ ONLY` 事务中，设置短 `statement_timeout` 和
`lock_timeout`，只保存聚合活动、复制、slot、归档与 control identity，不保存 SQL
正文、bind value、客户端地址或业务行。Patroni 只读 REST 返回会被缩减为 IP、角色、
状态、版本和 timeline。pgBackRest 输出只保留 stanza 状态、备份数量、最后备份类型、
时间、LSN 与 system identifier。

采集前后的源文件 SHA-256 绑定同一次 run。证据目录必须为 `0700`，文件必须为
`0600`；review 会拒绝 credential URI、SCRAM verifier、private key、原始 SQL/日志
字段和过度生产声明。

## 结论边界

一次通过的参考 run 只能证明：

```text
live read-only context captured
two blinded tabletop cases selected
solo and team response contracts validated
required evidence precedes route
dangerous actions remain unexecuted
decision logs cover the first fifteen minutes
```

它不证明真实 on-call 反应时间、生产权限、告警质量、备份可恢复、HA 可切换或业务
owner 已批准。最终状态固定为 `production_ch31_gate=pending`。
