# 第 36 章实验合同

本章不制造第五种故障，也不连接 PostgreSQL、Pigsty、SSH 或任何外部服务。它只读
第 32～35 章已经发布的去敏证据摘要，把四类演练编译成一份可审计的复盘组合：

```text
frozen public evidence
  -> pointer-bound observations
  -> four incident records
  -> cross-incident control themes
  -> 90-day reference backlog
  -> capability assessment contract
```

## 事实与解释

每条 observed fact 必须包含来源 JSON Pointer、期望值和 knowledge stage。编译器从
源文件重新解析并比较值，不允许把事后解释改写成“当时已知”。

四个输入都是 sandbox 演练，不是真实生产事故。`impact.kind` 只能是
`simulated` 或 `observed-sandbox`。跨事故 theme 的状态固定为
`production-assessment-required`：实验说明该控制值得评估，不证明某个生产组织已经
缺少它。

## 行动项

每个行动项必须有 role owner、P0/P1、0～90 天阶段、控制类型、可交付物、验证程序、
通过条件、关闭证据、重新验证周期和失效条件。`加强意识`、`以后注意`、以人名代替
owner role、把 proposed 直接标 closed，均不能通过。

backlog 是参考路线，不是变更批准。所有 action 均保持：

```text
status=proposed
production_execution_approved=false
```

## 结业边界

编译器可以证明全书能力地图完整覆盖 ch01～ch36，但不能据此证明某位读者已经掌握。
learner 状态必须保持 `not-assessed`；读者需在获授权环境中交付并答辩各能力域的证据。

## 负向验证

validator 对正式 bundle 构造 36 个 live mutant，包括篡改源事实、把 sandbox 影响
冒充生产、删除行动 owner/验证/失效条件、自动批准生产动作、遗漏路线阶段和自动认证
读者。每个 mutant 都必须被完整 validator 拒绝。

## 安全边界

- 不连接数据库、SSH、监控、工单或消息系统；
- 不覆盖第 32～35 章输入；
- 不发通知、不建工单、不执行 backlog；
- 不导出 raw evidence、secret 或个人信息；
- `production_ch36_gate=pending`。
