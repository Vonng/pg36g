# `pg36_shop` 开发规约 baseline v0.1

- 版本：`0.1.0`
- 发布日期：`2026-07-29`
- 证据范围：ch01–ch05
- 权威机器可读源：`baseline-v0.1.json`

## 规则等级

| 等级 | 含义 | 默认处置 |
|---|---|---|
| safety | 违反后可能造成数据错误、越权、不可恢复变更或不可归因事故 | merge/deploy blocker；仅 none 或受控 breakglass |
| default | 团队统一采用的工程默认 | 需要有 owner、expiry 和验证方式的 waiver |
| preference | 多个正确方案之间的维护性/成本偏好 | reviewer 根据场景证据决策 |

等级不是语气强弱。safety rule 必须有可执行停止线；default 允许有证据的例外；preference 不能伪装成“数据库绝对要求”。

## Safety

| Rule ID | 标题 |
|---|---|
| SAFE-CONN-001 | 精确声明并验证连接目标 |
| SAFE-SECR-002 | 凭据不进入仓库、命令行或证据包 |
| SAFE-ROLE-003 | 分离登录角色、对象所有者与运行角色 |
| SAFE-DEFR-004 | SECURITY DEFINER 固定解析上下文并收回 PUBLIC 执行权 |
| SAFE-CONS-005 | 关键不变量由命名约束与反例闭合 |
| SAFE-MIGR-006 | 破坏性迁移先证明可表示并设置停止线 |
| SAFE-TXNN-007 | 首个事务错误触发显式恢复 |
| SAFE-RETR-008 | 只按 SQLSTATE 整体重试且副作用幂等 |
| SAFE-DEST-009 | 破坏动作使用精确目标、双重令牌与后验 |
| SAFE-PAGE-010 | 对外分页必须定义稳定全序 |

## Defaults

| Rule ID | 标题 |
|---|---|
| DEFAULT-SESS-001 | 声明 application_name 与超时预算 |
| DEFAULT-CONT-002 | 固定编码、时区与名称解析上下文 |
| DEFAULT-NAME-003 | 用 schema、owner、命名和注释表达对象边界 |
| DEFAULT-TYPE-004 | 类型名必须闭合单位、范围和时间语义 |
| DEFAULT-KEYS-005 | 分离内部键、业务键、外部引用与幂等键 |
| DEFAULT-QUER-006 | 查询显式投影并声明结果合同 |
| DEFAULT-TXNN-007 | 事务只覆盖保持不变量所需的最短边界 |
| DEFAULT-FIXT-008 | fixture 可重建且状态由 checksum 验收 |
| DEFAULT-EVID-009 | 每次任务保存输入指纹与前后状态 |
| DEFAULT-VERS-010 | DDL 使用版本标记、幂等入口与 forward path |

## Preferences

| Rule ID | 标题 |
|---|---|
| PREF-TEXT-001 | 无长度合同的文本优先使用 text |
| PREF-SEMI-002 | 核心关系事实优先拆表，半结构化字段有边界 |
| PREF-PART-003 | 先证明生命周期、规模或裁剪收益再分区 |
| PREF-ASQL-004 | 高级 SQL 以关系表达清晰和可测试为准 |
| PREF-PLAN-005 | 计划或索引变更以估算和运行证据驱动 |

## 如何读一条规则

JSON 中每条 rule 都有：

- `statement`：可执行的规范句；
- `scope`：它约束哪些交付面；
- `rationale`：要阻止的失败机制；
- `evidence`：来自 ch01–ch05 的可复核资产与观察；
- `exception`：none、breakglass、waiver 或 review 的进入条件；
- `checks`：automated、runtime 或 review 验收。

只有“应该/不要”的句子不是规则；没有范围会被过度套用，没有例外机制会逼出暗中绕过，没有检查方式则无法知道规则是否生效。

## 生命周期

```text
candidate
  → 在 L1/测试环境试行
  → 记录误报、漏报与成本
  → active in baseline v0.x
  → ch07–ch11 追加运行证据
  → ch12 发布 v1.0 或修订/废弃
```

规则不因进入 baseline 永久正确。事故、评审、度量和例外都是后续输入；修改 rule statement 必须升级 baseline，并在 change log 中解释兼容影响。

## 使用方式

```bash
cd static/labs/ch06

# 不连接数据库：结构、证据引用、交付清单、shell/Python 与安全模式
./quality-gate.sh static

# 已确认的 L1：真实 catalog/session/query contract
export PGSERVICEFILE=/absolute/private/path/pg_service.conf
export PGSERVICE=pg36-admin
./quality-gate.sh all
```

`check_baseline.py`只验证 registry 的结构和内部一致性，不宣称自动证明每条规则的业务合理性。安全和正确性仍由自动 gate、runtime evidence 与有 owner 的 review 共同闭合。
