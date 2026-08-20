---
title: 第 19 章 开天辟地：环境规划与部署基线
linkTitle: 19 开天辟地：环境规划与部署基线
weight: 290
aliases:
- "/ch19/"
- "/volume-2/deployment-baseline/"
type: docs
math: true
breadcrumbs: true
comments: false
book_kind: chapter
book_id: ch19
book_number: 19
book_part: part-4
book_status: draft
---

上卷回答了 PostgreSQL 能做什么；下卷从一个更苛刻的问题开始：

> 我们准备把什么服务，交付给谁，承诺到什么程度；声明的版本、主机、
> 初始化与拓扑，是否真的存在？

本章先写需求与资源合同，再冻结 PostgreSQL 初始化选择，最后用 exact Pigsty
v4.4.0 在四台 Linux VM 上完成 PostgreSQL 18 部署和 L2 沙箱验收。正式
结果是“带六项例外的沙箱通过”，不是生产批准。

## 本章目标

读完并完成实验后，你应当能够：

1. 从业务损失、数据分类、owner、workload 与 RPO/RTO 写服务需求；
2. 将 CPU、memory、storage、network 与可观察饱和/故障条件连接；
3. 建立 OS baseline，而不是照抄 sysctl 模板；
4. 冻结并验证 locale/provider、encoding、checksum、page/WAL、auth 等
   PostgreSQL 初始化契约；
5. 严格区分 node、instance、database cluster、HA cluster、database、
   service、pool 与 DCS；
6. 用 secret-safe Pigsty inventory 声明两个 service unit；
7. 从 inventory、host、SQL、Patroni/service 四面交叉验收；
8. 区分 sandbox acceptance、exception 与 production gate；
9. 为 destructive reset 建立显式 guard，而不把它混入正常检查。

## 前置与后续

前置：

- [第 18 章 PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) 提供 service catalog、
  capability placement 与下卷 evidence gate；
- 读者应已掌握 Linux 与 SQL；
- 不要求预先掌握 PostgreSQL HA、Pigsty 或 Ansible internals。

后续：

- [第 20 章 高可用拓扑与容灾目标](/high-availability/) 使用本章保留 baseline
  验证 election、fencing、RTO 与数据损失边界；
- 第 21 章验证 backup/restore；
- 第 22 章验证 service routing、pooling 与 client semantics；
- 后续容量、安全、变更和升级 gate 不由本章安装结果代替。

## 学习路径

```text
service requirement
    -> resource/failure model
        -> host observed baseline
            -> irreversible PostgreSQL initialization contract
                -> topology and stable identity
                    -> secret-safe Pigsty declaration
                        -> live four-plane acceptance
                            -> exceptions + next gates
```

前三节解决“为什么、需要什么、机器是什么”；19.4–19.6 解决“哪些选择必须
提前冻结、如何声明”；19.7 只读验证声明与事实是否一致。

## 正式实验结果

```text
target               pg36-l2-vagrant
Pigsty               v4.4.0 exact tag
PostgreSQL           18.4 observed
hosts                4 distinct Ubuntu 24.04/aarch64 guests
service units        pg-meta + pg-test
pg-test              one primary + two streaming replicas
normal validation    passed
negative tests       9/9 rejected as designed
sandbox L2           accepted-with-exceptions
production ch19      pending
mutation by lab      none
reset                not executed
```

六项例外：

```text
shared hypervisor/power/storage
single etcd
single local backup target
unqualified virtual storage
temporary inventory-based secret handling
three pg-test guests below recommended 2-vCPU/2-GiB floor
```

这些例外不是脚注；它们逐项阻止 failure-domain、DCS、DR、durability、
secret lifecycle 与 capacity 的生产结论。

## 本章目录

### [19.1 先写服务需求](01/)

- [19.1.1 业务重要性、数据分类与所有者](01/#item-19-1-1)
- [19.1.2 负载形态、增长、峰谷和批处理窗口](01/#item-19-1-2)
- [19.1.3 可用性、RPO、RTO 与维护窗口](01/#item-19-1-3)

### [19.2 计算、内存、存储与网络](02/)

- [19.2.1 CPU 核数、频率、NUMA 与虚拟化](02/#item-19-2-1)
- [19.2.2 内存预算、页缓存与 OOM 边界](02/#item-19-2-2)
- [19.2.3 IOPS、吞吐、时延、容量与冗余](02/#item-19-2-3)
- [19.2.4 时钟、DNS、带宽、防火墙与故障域](02/#item-19-2-4)

### [19.3 操作系统与主机基线](03/)

- [19.3.1 文件系统、挂载、预读与透明大页](03/#item-19-3-1)
- [19.3.2 用户、目录、权限、时间同步与日志](03/#item-19-3-2)
- [19.3.3 基线检查必须记录事实而非套用调优模板](03/#item-19-3-3)

### [19.4 版本与数据库初始化契约](04/)

- [19.4.1 PostgreSQL、locale、collation、编码与 checksum](04/#item-19-4-1)
- [19.4.2 WAL、页大小、扩展与认证前提](04/#item-19-4-2)
- [19.4.3 版本矩阵、升级窗口与勘误入口](04/#item-19-4-3)

### [19.5 拓扑、命名与故障域](05/)

- [19.5.1 主节点、同步副本、异步副本与仲裁](05/#item-19-5-1)
- [19.5.2 节点、实例、集群、服务的统一词表](05/#item-19-5-2)
- [19.5.3 环境、区域、租户与业务命名](05/#item-19-5-3)

### [19.6 用声明式清单交付两个服务单元](06/)

- [19.6.1 inventory、参数模板与主机分组](06/#item-19-6-1)
- [19.6.2 生产服务与隔离验证服务](06/#item-19-6-2)
- [19.6.3 幂等部署、差异检查与失败重跑](06/#item-19-6-3)

### [19.7 实战：L2 部署验收](07/)

- [19.7.1 核对版本、拓扑、资源、端点和安全入口](07/#item-19-7-1)
- [19.7.2 从 SQL、主机与 Pigsty 三侧验证同一事实](07/#item-19-7-2)
- [19.7.3 产出基线清单、风险例外与 `reset:cluster`](07/#item-19-7-3)

## 实验入口

- [`lab-contract.md`](/labs/ch19/lab-contract.md)：风险、输入、动作、验收边界；
- [`requirements.json`](/labs/ch19/requirements.json)：机器可验证的需求；
- [`baseline-v2.0-sandbox.json`](/labs/ch19/baseline-v2.0-sandbox.json)：
  接受决定与非生产边界；
- [`inventory.example.yml`](/labs/ch19/inventory.example.yml)：无真实凭据的结构示例；
- [`task.sh`](/labs/ch19/task.sh)：`project/capture/verify/review/all`；
- [`deployment-adr.md`](/labs/ch19/deployment-adr.md)：架构决定；
- [`deployment-run.json`](/labs/ch19/deployment-run.json)：无 secret 的执行摘要。

正常 `all` 是只读验收，不包含 deploy、failover、restore 或 reset。

## 本章最重要的判断

```text
declaration != observation
playbook success != service acceptance
node count != independent failure domains
replica exists != RPO achieved
port open != routing contract
SSL on != transport security complete
sandbox passed != production approved
```

如果只记住一个方法，就记住：

> 同一事实必须由合适的 authority 证明；差异必须被拒绝或登记为有范围的
> exception，不能被一句“看起来正常”吞掉。

---

[上一章：万法归宗：PostgreSQL 数据平台与替代边界](/data-platform-boundaries/) · [返回下卷导读](/lower-volume/) · [下一章：狡兔三窟：高可用拓扑与容灾目标](/high-availability/) ·
[查看全书目录](/toc/) · [查看索引中心](/indexes/)
