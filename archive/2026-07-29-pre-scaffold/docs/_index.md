---
title: PostgreSQL 36计
cascade:
  type: docs
breadcrumbs: false
---

> 授人以鱼，不如授人以渔，不如授人以全自动捕鱼机。

![](/logo.png)

## 作者

[**冯若航**](https://vonng.com)，网名 [@Vonng](https://github.com/Vonng)。
[PostgreSQL 专家](https://vonng.com/pg)，[数据库老司机](https://vonng.com/db)，[云计算泥石流](https://vonng.com/cloud)。
[**Pigsty：开源PG发行版**](https://pigsty.cc) 作者与创始人。
架构师，DBA，全栈工程师 @ TanTan，Alibaba，Apple。
[活跃](https://committers.top/china)[开源贡献者](https://gitstar-ranking.com/Vonng)，
[DDIA](https://ddia.pigsty.io) / [PG Internal](https://pgint.vonng.com) 中文版译者，公众号：《老冯云数》主理人，数据库 KOL。



## [上卷：应用开发](/dev)

{{< cards cols="3" >}}
    {{< card link="/ch01" title="01 扬帆起航" icon="flag" subtitle="搭建 PostgreSQL 实战沙箱" tag="编写中" tagType="info" >}}
    {{< card link="/ch07" title="07 追本溯源" icon="chart-bar" subtitle="执行计划与统计信息" tag="未发布" >}}  
    {{< card link="/ch13" title="13 博采众长" icon="globe" subtitle="内核分支与扩展生态" tag="未发布" >}}
    
    {{< card link="/ch02" title="02 盲人摸象" icon="eye" subtitle="建立 PostgreSQL 全局认知" tag="未发布" >}}
    {{< card link="/ch09" title="09 巧夺天工" icon="color-swatch" subtitle="索引设计与维护策略" tag="未发布" >}}
    {{< card link="/ch14" title="14 见微知著" icon="document-search" subtitle="全文检索与向量检索" tag="未发布" >}}
    
    {{< card link="/ch03" title="03 手到擒来" icon="hand" subtitle="掌握 psql 与核心工具链" tag="未发布" >}}
    {{< card link="/ch08" title="08 抽丝剥茧" icon="collection" subtitle="慢 SQL 诊断方法论" tag="未发布" >}}
    {{< card link="/ch15" title="15 经天纬地" icon="database" subtitle="时序与地理空间能力" tag="未发布" >}}
    
    {{< card link="/ch04" title="04 正本清源" icon="document-text" subtitle="数据模型、类型与约束设计" tag="未发布" >}}
    {{< card link="/ch10" title="10 顾此失彼" icon="cog" subtitle="并发控制与隔离异常" tag="未发布" >}}
    {{< card link="/ch16" title="16 合纵连横" icon="eye" subtitle="分布式与分析计算扩展" tag="未发布" >}}
    
    {{< card link="/ch05" title="05 运筹帷幄" icon="calculator" subtitle="查询优化、事务与锁机制" tag="未发布" >}}
    {{< card link="/ch11" title="11 守正出奇" icon="briefcase" subtitle="模式变更与发布策略" tag="未发布" >}}
    {{< card link="/ch17" title="17 言出法随" icon="code" subtitle="函数、触发器与存储过程" tag="未发布" >}}
    
    {{< card link="/ch06" title="06 立木取信" icon="badge-check" subtitle="开发规约与评审清单" tag="未发布" >}}
    {{< card link="/ch12" title="12 一气呵成" icon="lightning-bolt" subtitle="从数据库到后端服务" tag="未发布" >}}
    {{< card link="/ch18" title="18 万法归宗" icon="library" subtitle="PostgreSQL 平台化替代" tag="未发布" >}}
{{< /cards >}}



-------------

## [下卷：运维管理](/dba)

{{< cards cols="4" >}}
    {{< card link="/ch19" title="19 开天辟地" icon="desktop-computer" subtitle="环境规划与部署基线" tag="未发布" >}}
    {{< card link="/ch25" title="25 望闻问切" icon="eye" subtitle="监控体系与可观测性" tag="未发布" >}}
    {{< card link="/ch31" title="31 枕戈待旦" icon="bell" subtitle="告警分级与应急响应" tag="未发布" >}}
    
    {{< card link="/ch20" title="20 狡兔三窟" icon="archive" subtitle="高可用拓扑与容灾目标" tag="未发布" >}}
    {{< card link="/ch26" title="26 胸有成竹" icon="clipboard-check" subtitle="容量规划与压测基线" tag="未发布" >}}
    {{< card link="/ch32" title="32 妙手回春" icon="clock" subtitle="PITR 与误操作恢复" tag="未发布" >}}
    
    {{< card link="/ch21" title="21 未雨绸缪" icon="duplicate" subtitle="备份体系与恢复演练" tag="未发布" >}}
    {{< card link="/ch27" title="27 精益求精" icon="refresh" subtitle="参数调优与资源治理" tag="未发布" >}}
    {{< card link="/ch33" title="33 力挽狂澜" icon="exclamation-circle" subtitle="故障切换与集群重建" tag="未发布" >}}
    
    {{< card link="/ch22" title="22 四通八达" icon="globe-alt" subtitle="服务接入与连接路由" tag="未发布" >}}
    {{< card link="/ch28" title="28 除旧布新" icon="link" subtitle="VACUUM 与膨胀治理" tag="未发布" >}}
    {{< card link="/ch34" title="34 李代桃僵" icon="adjustments" subtitle="流量调度与降级止血" tag="未发布" >}}
    
    {{< card link="/ch23" title="23 固若金汤" icon="lock-closed" subtitle="认证授权与数据安全" tag="未发布" >}}
    {{< card link="/ch29" title="29 移花接木" icon="trash" subtitle="复制、迁移与异构同步" tag="未发布" >}}
    {{< card link="/ch35" title="35 起死回生" icon="heart" subtitle="极限数据抢救与取证" tag="未发布" >}}
    
    
    {{< card link="/ch24" title="24 纲举目张" icon="clipboard-list" subtitle="SLA、SOP 与组织治理" tag="未发布" >}}
    {{< card link="/ch30" title="30 推陈出新" icon="switch-horizontal" subtitle="版本升级与回滚策略" tag="未发布" >}}
    {{< card link="/ch36" title="36 举一反三" icon="light-bulb" subtitle="复盘改进与平台演进" tag="未发布" >}}
{{< /cards >}}
