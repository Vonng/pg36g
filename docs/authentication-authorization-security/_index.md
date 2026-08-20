---
title: 第 23 章 固若金汤：认证、授权与数据安全
linkTitle: 23 固若金汤：认证、授权与数据安全
weight: 330
aliases:
- "/ch23/"
- "/volume-2/authentication-authorization-security/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch23
book_number: 23
book_part: part-4
book_status: draft
---

数据库安全不是在系统外面再围一堵墙，而是让每一次越过边界都留下可验证的
答案：

```text
谁在连接
  -> 从哪里、通过哪条加密路径
      -> 以哪个 login 通过认证
          -> 当前使用哪个 effective role
              -> 对哪个对象有什么权限
                  -> 哪些行可见、哪些新值可写
                      -> 谁能变更这些规则
                          -> 事件能否被安全地调查和撤销
```

只检查其中一层会产生危险的“半安全”：

```text
SCRAM 成功              != 网络中的服务器身份正确
TLS 已加密              != 客户端验证了证书名称
HBA 匹配                != 角色有对象权限
GRANT SELECT            != 能看见全部行
RLS 生效                != table owner / superuser 也受约束
密码已经修改            != 旧连接已经断开
PostgreSQL role 已创建   != PgBouncer 已交付该身份
日志很多                != 有完整、受保护、可检索的审计链
```

本章先建威胁模型，再沿认证、授权、行级安全、密钥和审计一路向内。最后把
第 22 章的 transaction pool 纳入模型：同一个 PostgreSQL backend 会先后
服务不同客户端，因此 session 级安全上下文不仅会“丢失”，还可能泄漏给下一
个租户。

## 本章目标

完成本章后，你应当能够：

1. 用资产、主体、入口、信任跨越和失败后果编写数据库威胁模型；
2. 区分终端用户、应用 login、effective role、object owner 与 break-glass；
3. 从 `pg_hba_file_rules` 解释 first-match，而不是凭配置片段猜认证结果；
4. 区分认证方法、密码存储、传输加密和服务器身份校验；
5. 使用 SCRAM，理解 channel binding、密码轮换与客户端兼容边界；
6. 说明 `sslmode=require`、`verify-ca` 与 `verify-full` 分别证明什么；
7. 用 `pg_stat_ssl`、证书 SAN、HBA 和真实连接共同验收 TLS；
8. 把 LOGIN、group、owner、migrate、runtime、readonly 角色拆开；
9. 正确使用 PostgreSQL 16+ membership 的 `ADMIN`、`INHERIT` 与 `SET`；
10. 设计 schema/table/sequence/function/default privilege 的最小权限；
11. 识别 `PUBLIC`、owner、`search_path`、`SECURITY DEFINER` 和预定义高权
    角色造成的越权路径；
12. 为共享表设计 RLS 的 `USING` 与 `WITH CHECK`；
13. 解释 default-deny、permissive `OR`、restrictive `AND` 与完整表操作边界；
14. 使用 `FORCE ROW LEVEL SECURITY` 约束 owner，并明确 superuser/
    `BYPASSRLS` 仍会绕过；
15. 通过事务级 `SET LOCAL ROLE` 和 tenant context 支持 transaction pool；
16. 复现 session `SET` 跨客户端泄漏，并证明事务局部状态在提交后消失；
17. 设计生成、分发、双版本轮换、撤销和应急回收的凭据生命周期；
18. 区分普通运行日志、对象/会话审计、平台审计和合规证据；
19. 在 Pigsty 中声明用户、HBA 和接入层，再从渲染产物与运行事实反查；
20. 对一个环境给出“通过、带例外通过、待整改或拒绝”的诚实安全结论。

## 前置与后续

前置：

- [第 6 章 开发规约](/development-standards/) 已处理参数绑定、受控
  `search_path`、`SECURITY DEFINER` 和 secret-free 交付；
- [第 10 章 并发控制](/concurrency-isolation/) 已建立事务与 session 边界；
- [第 19 章 部署基线](/deployment-baseline/) 已固定 Pigsty v4.4.0 四机
  nonproduction sandbox；
- [第 20 章 高可用](/high-availability/) 已区分 data plane、control plane
  与 break-glass；
- [第 21 章 备份体系与恢复演练](/backup-recovery/) 已说明备份、WAL、日志同样是敏感
  数据载体；
- [第 22 章 服务接入](/connection-pooling-routing/) 已证明 transaction
  pooling 会复用 backend 并保留某些 session 状态。

后续：

- 第 24 章把安全例外、owner、轮换、SOP 和审批纳入治理；
- 第 25 章把连接、认证失败、角色变更与审计事件接入可观测系统；
- 第 29、30 章处理复制/迁移/升级中的身份与双版本兼容；
- 第 31 章把泄露、越权、凭据失陷与取证放进事件响应；
- 第 32–35 章会再次约束备份、恢复、故障操作和抢救身份。

## 学习路径

```text
资产与主体
  -> 信任边界和攻击路径
      -> HBA/认证/TLS
          -> login 与 effective role
              -> 对象所有权和最小权限
                  -> RLS 行边界
                      -> transaction-pool 上下文
                          -> secret 生命周期
                              -> 日志、审计和脱敏
                                  -> Pigsty 声明/渲染/运行差异
                                      -> 双租户对抗性验收
```

顺序很重要。若先写一条 RLS policy、最后才问“tenant id 从哪里来”，就可能
把用户自己提交的 tenant id 原样写入 GUC，得到一套语法正确却可随意越权的
系统。

## 六层安全证明

| 层 | 要证明的问题 | PostgreSQL / Pigsty 证据 |
|---|---|---|
| 暴露面 | 哪些端口和网络能到达 | listener、防火墙/安全组、HAProxy、HBA |
| 传输 | 对端是谁、链路是否加密 | `sslmode`、CA/SAN、`pg_stat_ssl`、PgBouncer TLS |
| 认证 | login 是谁、凭据是否有效 | HBA first-match、SCRAM/cert/外部身份、认证日志 |
| 授权 | current role 能做什么 | role graph、ACL、owner、default privilege |
| 数据 | 哪些行可见、哪些新值可写 | RLS flag、policy、正负测试、`FORCE RLS` |
| 治理 | 谁能变更、撤销、调查 | inventory、审批、secret manager、audit/retention |

这六层不能互相代替。例如 PostgreSQL `hostssl` 只要求连接使用 TLS；客户端若
选择不校验证书名称，仍可能把密码发给错误的服务器。反过来，`verify-full`
只能验证连接到证书所代表的服务器，不能证明这个 login 应当读取某个租户。

## 角色分层

本章采用一个可复用的角色图：

```text
login identity
  ├─ SET TRUE, INHERIT FALSE -> runtime NOLOGIN
  └─ SET TRUE, INHERIT FALSE -> readonly NOLOGIN

migration identity
  -> migrate NOLOGIN
      -> SET TRUE, INHERIT FALSE -> owner NOLOGIN

break-glass
  -> 独立控制；不属于应用正常路径
```

职责：

| 角色 | LOGIN | 主要权限 | 明确不应拥有 |
|---|---:|---|---|
| application login | 是 | 只允许切换到批准的 runtime role | owner、DDL、ADMIN OPTION |
| runtime | 否 | USAGE + 必要 DML | schema CREATE、TRUNCATE、BYPASSRLS |
| readonly | 否 | USAGE + SELECT | 写入、迁移 |
| migrate | 否 | 可切换到 owner | 日常服务流量、凭据 |
| owner | 否 | 拥有应用对象和 policy | 日常 LOGIN |
| break-glass | 独立 | 紧急高权动作 | 无审批、无时限、无审计 |

PostgreSQL 16 起，membership 自身有 `ADMIN`、`INHERIT` 与 `SET` 选项。
本章使用：

```sql
GRANT pg36_ch23_runtime TO test
WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
```

因此 `test` 登录后不会隐式得到 runtime 权限，但能在批准的事务中
`SET LOCAL ROLE`；它也不能把 runtime 身份再授予别人。

## 租户事务合同

共享表 RLS 的最小请求序列：

```sql
BEGIN;
SET LOCAL ROLE pg36_ch23_runtime;
SELECT set_config('app.tenant_id', $1, true);

-- 所有业务 SQL；$1 必须来自已认证、已授权的应用身份映射

COMMIT;
```

第三个参数 `true` 表示 transaction-local。提交或回滚之后，角色和 tenant
context 都不应继续生效。

表同时使用：

```sql
ALTER TABLE pg36_ch23.account ENABLE ROW LEVEL SECURITY;
ALTER TABLE pg36_ch23.account FORCE ROW LEVEL SECURITY;
```

policy 分开描述读写：

```text
SELECT            USING
INSERT            WITH CHECK
UPDATE            USING + WITH CHECK
owner             USING + WITH CHECK，且 FORCE RLS
```

`USING` 回答“旧行能否进入操作”；`WITH CHECK` 回答“新行版本能否存在”。
只写其中一边，常会允许把一行从本租户改到另一个租户，或者插入不可见数据。

## 正式实验

```text
target          pg36-l2-vagrant/pg-test
Pigsty          v4.4.0
PostgreSQL      18.4
PgBouncer       1.25.2, transaction mode
database        test
fixture         schema pg36_ch23, two tenants, four synthetic rows
topology        pg-test-1 primary, pg-test-2/3 streaming replicas
timeline        11 before and after
```

角色与对象：

```text
five synthetic roles             all NOLOGIN after drill
superuser/CREATEDB/CREATEROLE     false
REPLICATION/BYPASSRLS             false
runtime table ACL                 SELECT, INSERT, UPDATE
readonly table ACL                SELECT
schema CREATE for runtime         false
RLS / FORCE RLS                   true / true
policies                           5
tenant row counts                  2 + 2
```

RLS 观测：

```text
runtime tenant A                  exactly 2 A rows
runtime tenant B                  exactly 2 B rows
missing context                   0 rows
malformed context                 SQLSTATE 22P02
cross-tenant INSERT               SQLSTATE 42501
cross-tenant UPDATE               SQLSTATE 42501
runtime disable RLS               SQLSTATE 42501
runtime CREATE/TRUNCATE           SQLSTATE 42501
readonly INSERT                   SQLSTATE 42501
row_security=off                  SQLSTATE 42501, not a bypass
raw sandbox login                 SQLSTATE 42501
owner without context             0 rows under FORCE RLS
owner with tenant A               2 A rows
superuser break-glass             all 4 rows
```

连接池反例临时把入口 PgBouncer 从：

```text
default_pool_size=50
reserve_pool_size=30
reserve_pool_timeout=1
query_wait_timeout=120
```

改为：

```text
default_pool_size=1
reserve_pool_size=0
reserve_pool_timeout=1
query_wait_timeout=15
```

客户端 A 用 session 级 `set_config(..., false)` 设置 tenant A；关闭后，客户端 B
在同一个 backend、没有设置 tenant 的情况下仍读到 tenant A 的两行。这是
有意注入的失败，不是支持方式。

刷新 pool 后，四个事务依次在同一个 backend 上得到：

```text
tenant A local context        A 的 2 行
missing context               0 行
tenant B local context        B 的 2 行
missing context               0 行
```

这证明隔离来自事务边界，而不是恰好换了 backend。随后四个 pool 参数精确
复位，并对三个节点执行 `RECONNECT test` 清理注入的 session 状态。

TLS 与认证观测：

```text
PostgreSQL ssl                          on
minimum protocol                       TLSv1.2
direct sslmode=require                  TLSv1.3 / AES-256-GCM
direct verify-full                      成功
wrong certificate name                 拒绝
verify-full + channel_binding=require   成功
direct sslmode=disable                  成功，生产缺口
PgBouncer client TLS                    disable
pooled sslmode=disable                  成功
pooled sslmode=require                  拒绝，生产缺口
HBA parser errors                       0
server private-key mode                 0600
certificate SAN                         覆盖各节点 DNS 与 IP
CRL file/directory                      未配置
```

凭据轮换使用一个不进入 PgBouncer userlist 的 direct-only synthetic role：

```text
secret v1 new connection               成功
pool connection                        失败；身份面未声明
change to secret v2
secret v1 new connection               失败
secret v2 new connection               成功
already-authenticated v1 session       仍可用
ALTER ROLE ... NOLOGIN
new connection                         失败
already-authenticated session          仍可用
final PASSWORD NULL + NOLOGIN          已验证
```

密码值、SCRAM verifier、raw userlist 和 private key 都没有进入证据。

## 生产结论

本章 formal sandbox 结论是：

```text
identity/role separation                通过
object ACL                              通过
two-tenant FORCE RLS                    通过
transaction-local pool context          通过
credential lifecycle semantics          通过
public cert and key-mode checks          通过
topology/pool restoration                通过

direct business TLS enforcement          未通过
PgBouncer client TLS                     未通过
CRL/revocation drill                     未完成
client CA distribution/rotation          未完成
pgAudit                                  未安装/未加载
log bind-parameter policy                待整改
production approval                      pending
```

这不是“Pigsty 不安全”的概括，而是对这一份 dev/test inventory 和运行状态的
精确判断。Pigsty 默认面向可信内网的开发、测试和演示；生产必须依据自己的
威胁模型收紧密码、网络、HBA、证书、审计与 secret 管理。

## 本章例外

在前四章下卷例外之外，本章保留：

```text
EX23-TRUSTED-INTRANET-NO-TLS
  普通业务 HBA 使用 host + SCRAM；内网明文 TCP 可成功。

EX23-PGBOUNCER-CLIENT-TLS-DISABLED
  池化客户端入口没有 TLS；不能通过生产传输门禁。

EX23-NO-CRL-OR-ROTATION-DRILL
  证书命名正确，但没有执行 CA/cert/CRL 双版本轮换与撤销。

EX23-NO-PGAUDIT
  shared_preload_libraries 没有 pgAudit，扩展也未安装。

EX23-FULL-NONERROR-BIND-PARAMETERS
  log_parameter_max_length=-1；与慢 SQL 日志组合时可能记录完整 bind 值。

EX23-SYNTHETIC-TWO-TENANT
  只有四行合成数据、一个 schema；不能推出复杂产品的 policy 正确。

EX23-MULTIPLEXED-TEST-LOGIN
  为复用已有 PgBouncer 声明，formal lab 用 test 切换 runtime/readonly；
  生产应为 workload 配置独立 login 与 credential。
```

## 本章目录

### [23.1 威胁模型与信任边界](01/)

- [23.1.1 用户、应用、运维、平台与第三方](01/#item-23-1-1)
- [23.1.2 网络、凭据、SQL、备份和日志攻击面](01/#item-23-1-2)
- [23.1.3 数据分级、租户边界与应急权限](01/#item-23-1-3)

### [23.2 认证与连接准入](02/)

- [23.2.1 `pg_hba.conf` 的匹配顺序与证据](02/#item-23-2-1)
- [23.2.2 SCRAM、证书与外部身份](02/#item-23-2-2)
- [23.2.3 TLS 验证、吊销与密钥轮换](02/#item-23-2-3)

### [23.3 角色与最小权限](03/)

- [23.3.1 login、group、owner 与 runtime role](03/#item-23-3-1)
- [23.3.2 schema、table、sequence、function 权限](03/#item-23-3-2)
- [23.3.3 默认权限、所有权迁移与越权路径](03/#item-23-3-3)

### [23.4 行级安全与连接池上下文](04/)

- [23.4.1 RLS policy、owner bypass 与强制 RLS](04/#item-23-4-1)
- [23.4.2 租户身份通过事务参数传递](04/#item-23-4-2)
- [23.4.3 transaction pooling 下使用 `SET LOCAL`](04/#item-23-4-3)
- [23.4.4 验证复用连接不会泄漏上一个租户状态](04/#item-23-4-4)

### [23.5 密钥、审计与敏感信息](05/)

- [23.5.1 凭据生成、存放、轮换和撤销](05/#item-23-5-1)
- [23.5.2 审计目标、日志范围与访问控制](05/#item-23-5-2)
- [23.5.3 参数、SQL 文本与日志脱敏](05/#item-23-5-3)

### [23.6 Pigsty 安全基线](06/)

- [23.6.1 角色、HBA、证书与服务入口声明](06/#item-23-6-1)
- [23.6.2 管理面、监控面和数据库面的网络边界](06/#item-23-6-2)
- [23.6.3 从配置渲染到运行事实的差异检查](06/#item-23-6-3)

### [23.7 实战：隔离两个租户](07/)

- [23.7.1 建立应用角色、迁移角色和只读角色](07/#item-23-7-1)
- [23.7.2 通过 PgBouncer 事务池验证 RLS](07/#item-23-7-2)
- [23.7.3 注入会话状态泄漏与越权访问并修复](07/#item-23-7-3)
- [23.7.4 输出权限矩阵、轮换证据与应急回收步骤](07/#item-23-7-4)

## 实验入口

- [`lab-contract.md`](/labs/ch23/lab-contract.md)：权限、变更、证据和 reset 边界；
- [`requirements.json`](/labs/ch23/requirements.json)：机器验收合同；
- [`threat-model.json`](/labs/ch23/threat-model.json)：资产、主体和信任跨越；
- [`role-contract.json`](/labs/ch23/role-contract.json)：五类 synthetic role；
- [`tenant-contract.json`](/labs/ch23/tenant-contract.json)：事务级租户上下文；
- [`security-adr.md`](/labs/ch23/security-adr.md)：RLS 与连接池决策；
- [`topology.mmd`](/labs/ch23/topology.mmd)：端点、角色和数据边界；
- [`task.sh`](/labs/ch23/task.sh)：唯一安全入口；
- [`security-run.json`](/labs/ch23/security-run.json)：正式参考结果；
- [`negative-cases.json`](/labs/ch23/negative-cases.json)：二十个反例。

`task.sh all` 只重验既有证据，不登录应用身份、不改 role/password/pool/HBA/
certificate，也不删除 fixture。`drill:security` 和 `reset:fixture` 是两条
完全分离、精确守卫的路径。

## 参考资料

- [PostgreSQL 18：Client Authentication](https://www.postgresql.org/docs/18/client-authentication.html)
- [PostgreSQL 18：pg_hba.conf](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html)
- [PostgreSQL 18：Password Authentication](https://www.postgresql.org/docs/18/auth-password.html)
- [PostgreSQL 18：libpq SSL Support](https://www.postgresql.org/docs/18/libpq-ssl.html)
- [PostgreSQL 18：Database Roles](https://www.postgresql.org/docs/18/user-manag.html)
- [PostgreSQL 18：Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)
- [PostgreSQL 18：Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html)
- [PgBouncer：Features](https://www.pgbouncer.org/features.html)
- [PgBouncer：Configuration](https://www.pgbouncer.org/config.html)
- [Pigsty：Security Considerations](https://pigsty.io/docs/deploy/security/)
- [Pigsty：HBA Rules](https://pigsty.io/docs/pgsql/config/hba/)

---

[上一章：四通八达：服务接入、连接池与路由](/connection-pooling-routing/) · [返回下卷导读](/lower-volume/) · [下一章：纲举目张：SLO、SOP 与组织治理](/slo-sop-governance/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
