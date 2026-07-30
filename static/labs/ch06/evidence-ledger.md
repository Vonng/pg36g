# baseline 证据账本

## v0.1 已纳入

| 来源 | 证据主题 | 进入 baseline 的规则族 |
|---|---|---|
| ch01 | 目标环境、角色、schema、危险 reset | CONN / ROLE / DEST |
| ch02 | service file、会话上下文、脚本证据 | CONN / SECR / SESS / EVID |
| ch03 | 业务规则、关系边界、确定性 fixture | NAME / KEYS / FIXT |
| ch04 | 类型、约束、迁移、状态与分区 ADR | CONS / MIGR / TYPE / PART |
| ch05 | query path、事务失败、retry、lock evidence | QUERY / TXN / RETR / PLAN |

## v0.2–v0.6 预留追加区

| 章节 | 必须追加的运行证据 | 可能升级的规则 |
|---|---|---|
| ch07 | estimate/actual、statistics、plan settings | PREF-PLAN-005 |
| ch08 | workload attribution、wait taxonomy、slow-query evidence | DEFAULT-EVID-009 |
| ch09 | index benefit/cost、write amplification、concurrent build | PREF-PLAN-005 |
| ch10 | lost update、write skew、deadlock、40001 retry | SAFE-RETR-008 |
| ch11 | expand/contract、lock budget、application compatibility | SAFE-MIGR-006 / DEFAULT-VERS-010 |

## v1.0 汇总条件

ch12 只有在以下条件全部满足时才能发布 baseline v1.0：

1. 每条 active rule 至少有一个可重复实验或生产事件证据；
2. safety rule 全部存在自动或 runtime gate，不只依赖文字评审；
3. 每个 exception 有 owner、expiry、补偿控制与复核结果；
4. query/transaction/DDL 规则已经在一个后端服务交付中实走；
5. 静态、live、negative 三类 gate 均可在统一环境重跑；
6. v0.x 期间的误报、漏报、例外和事故已经回写 rationale；
7. compatibility matrix 至少覆盖 PostgreSQL 14–18 与当前 Pigsty 基线；
8. baseline v1.0 有迁移说明，不静默改变既有规则语义。
