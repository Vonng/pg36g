# 第 24 章治理实验合同

## 目标

本实验验证一套治理文档能否形成闭环：

```text
service card
  -> SLI/SLO/control objective
      -> observation and missing-data semantics
          -> accepted/rejected alerts
              -> SOP and change authority
                  -> evidence retention
                      -> upstream drill references
                          -> current deployment gate
```

它不会创建数据库对象、修改告警规则、切换主库、恢复数据、轮换凭据或发送真实
通知。

## 风险等级

| 动作 | 风险 | 远端行为 | 本地产物 |
|---|---:|---|---|
| `lint` | L0 | 无 | 临时验证报告 |
| `capture` | L0 | 第 19 章只读 SSH/SQL/REST/TCP 采集 | 私密 evidence |
| `verify` | L0 | 无 | 更新验证报告 |
| `review` | L0 | 无 | 只读审查 |
| `all` | L0 | 与 `capture` 相同 | 完整 evidence |

本章没有 reset 或 mutation action。`all` 只表示“采集当前只读门槛并验证所有
合同”，不表示执行被合同引用的切换、恢复或安全演练。

## 私密输入

`capture` 与 `all` 要求：

```text
PG36_CH19_INVENTORY=/absolute/private/mode-0600/baseline.yml
PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch24-run
```

inventory 由第 19 章读取。第 24 章只接收脱敏投影与验证结果，不复制、不散列
原始 inventory，也不导出凭据。

## 上游证据边界

治理合同引用第 20–23 章已经保留的正式沙箱摘要。验证器检查 schema、run id、
文件哈希与各章 `production_*_gate=pending`，因此：

- 可以证明“治理条目指向了哪次实验”；
- 不能证明那些实验在今天仍然新鲜；
- 不能证明沙箱观测是生产 RTO、RPO、容量、可用性或安全批准；
- 不能把一份 JSON 摘要替代原始私密 evidence。

## 运行

只验证公共合同：

```bash
static/labs/ch24/task.sh lint
```

正式只读运行：

```bash
export PG36_CH19_INVENTORY=/absolute/private/baseline.yml
export PG36_EVIDENCE_DIR=/absolute/private/new-empty/ch24-run
static/labs/ch24/task.sh all
```

重验已有 evidence：

```bash
export PG36_EVIDENCE_DIR=/absolute/private/existing/ch24-run
static/labs/ch24/task.sh verify
static/labs/ch24/task.sh review
```

## 通过标准

- 服务卡有完整 owner、依赖、健康层和非生产边界；
- ratio SLO 的事件、测量点、窗口、排除和预算可以计算；
- 正确性与恢复就绪没有被平均错误率掩盖；
- 每个 SLI 有数据源、查询、维度、缺失语义和 fallback；
- page 可行动，原因/容量不会越权打扰值班；
- 四类核心 SOP 都有前置、停止线、验证、回退/前滚和证据；
- L2/L3 权限分离，break-glass 仍绑定目标与事后证据；
- 六类证据都有保留、访问、完整性和脱敏要求；
- 二十个对抗性变体全部被拒绝；
- 当前第 19 章沙箱门槛只读通过且生产门槛保持 `pending`。
