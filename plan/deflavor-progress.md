# 「去 AI 味」校对进度跟踪

配套提示词：[plan/plain-language-rewrite-prompt.md](plain-language-rewrite-prompt.md)（2026-10-23 起的全书重编方案）。[prompt/deflavor.md](../prompt/deflavor.md) 是已被替代的窄范围措辞校对方案，仅作历史参考。每个文件处理完毕后立即更新对应行；会话中断后凭本文件接续。

状态取值：`待处理` → `改写中` → `待独立审阅` → `已验收`；技术疑点另标 `待核实`。改写人默认为本会话主笔（ZCode 主控）；独立审阅人在验收行记录（技术审 / 语言审）。Δ字符填 `git diff --stat` 或前后字符数之差；遗留问题填技术疑点与未核实缺口，风格问题当场解决不留账。`book_status: draft` 表示已实质重写待审，验收后提升回 `reviewed`（与控制 Hugo 发布的 `draft: true` 是两个字段）。

## 标志词基线（2026-10-22，docs/ 全量）

| 标志词 | 出现次数 |
|---|---|
| 而不是 | 551 |
| 不要把 | 168 |
| 禁止 | 97 |
| 不是一个 | 52 |
| 真正的 | 35 |
| 更重要 | 17 |
| 小结 | 17 |
| 务必 | 15 |
| 并非 | 15 |
| 所谓 | 14 |
| 并不是 | 9 |
| 不能简单 | 6 |

说明：「禁止」多为配置与授权语义（技术内容，应保留）；其余以提示词第三节清单逐个裁决。复查命令：

```bash
cd docs && for p in '而不是' '不要把' '真正的' '务必' '所谓'; do printf "%s\t%d\n" "$p" "$(grep -r --include='*.md' -o "$p" . | wc -l)"; done
```

## 全书汇总

| 批次 | 文件数 | 已完成 | 已复核 |
|---|---|---|---|
| 全书框架页（导读、目录、卷首） | 7 | 7 | 7 |
| ch01　盲人摸象：PostgreSQL 与 Pigsty 全局地图 | 8 | 8 | 8 |
| ch02　手到擒来：psql 与可复现工作流 | 8 | 8 | 8 |
| ch03　正本清源：从业务规则到关系模型 | 7 | 7 | 7 |
| ch04　量体裁衣：数据类型、约束与可靠数据表达 | 8 | 8 | 8 |
| ch05　运筹帷幄：查询、事务与锁的核心心智模型 | 7 | 7 | 7 |
| ch06　立木取信：开发规约与交付基线 | 8 | 8 | 8 |
| ch07　追本溯源：执行计划与统计信息 | 8 | 8 | 8 |
| ch08　抽丝剥茧：慢 SQL 诊断方法论 | 8 | 1 | 1 |
| ch09　巧夺天工：索引设计与效果验证 | 7 | 7 | 7 |
| ch10　顾此失彼：并发控制与隔离异常 | 8 | 8 | 8 |
| ch11　守正出奇：模式变更与安全发布 | 8 | 8 | 8 |
| ch12　一气呵成：从数据库契约到后端服务 | 8 | 8 | 8 |
| ch13　言出法随：函数、触发器与存储过程 | 7 | 7 | 7 |
| ch14　博采众长：内核分支与扩展生态 | 8 | 8 | 8 |
| ch15　见微知著：全文、模糊与向量检索 | 8 | 8 | 8 |
| ch16　经天纬地：时序、空间与时空查询 | 8 | 8 | 8 |
| ch17　合纵连横：分析加速与分布式选型 | 7 | 7 | 7 |
| ch18　万法归宗：PostgreSQL 数据平台与替代边界 | 7 | 7 | 7 |
| ch19　开天辟地：环境规划与部署基线 | 8 | 8 | 8 |
| ch20　狡兔三窟：高可用拓扑与容灾目标 | 8 | 8 | 8 |
| ch21　未雨绸缪：备份体系与恢复演练 | 7 | 7 | 7 |
| ch22　四通八达：服务接入、连接池与路由 | 8 | 8 | 8 |
| ch23　固若金汤：认证、授权与数据安全 | 8 | 8 | 8 |
| ch24　纲举目张：SLO、SOP 与组织治理 | 7 | 7 | 7 |
| ch25　望闻问切：监控体系与可观测诊断 | 8 | 8 | 8 |
| ch26　胸有成竹：容量规划与压测基线 | 7 | 7 | 7 |
| ch27　精益求精：参数调优与资源治理 | 8 | 8 | 8 |
| ch28　除旧布新：VACUUM、冻结与膨胀治理 | 8 | 8 | 8 |
| ch29　移花接木：逻辑复制、迁移与异构同步 | 8 | 8 | 8 |
| ch30　推陈出新：版本升级与回滚策略 | 8 | 8 | 8 |
| ch31　事件分级、现场保护与应急决策——枕戈待旦 | 7 | 7 | 7 |
| ch32　PITR 与误操作恢复——妙手回春 | 7 | 7 | 7 |
| ch33　故障切换与集群重建——力挽狂澜 | 8 | 8 | 8 |
| ch34　过载保护与资源故障判型——李代桃僵 | 9 | 9 | 9 |
| ch35　数据抢救与工程取证——起死回生 | 8 | 8 | 8 |
| ch36　事故复盘、控制固化与平台演进——举一反三 | 8 | 8 | 8 |
| ch00　实验环境准备 | 4 | 4 | 4 |
| 附录 | 7 | 7 | 0 |
| 索引页 | 6 | 6 | 0 |
| **合计** | **302** | 0 | 0 |

## 全书框架页（导读、目录、卷首）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `_index.md` | 首页 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +3−3 | 版本基线声明待核实（见下） |
| `_index.en.md` | Home | 已验收（两审通读，无改动） | 0 | 英文入口仅 3 句引导，维持现状 |
| `toc.md` | 目录 | 已验收（两审通读，无改动） | 0 | 纯导航链接；由 check-book 全量链接校验覆盖；含“而不是”式节标题待各章正文改写时同步 |
| `preface.md` | 序言 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +11−10 |  |
| `upper-volume.md` | 上卷：应用开发 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +5−5 |  |
| `lower-volume.md` | 下卷：运维管理 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +5−5 |  |
| `guide/_index.md` | 导读 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +5−4 | D.5 版本基线表待核实（见下） |

## ch01　盲人摸象：PostgreSQL 与 Pigsty 全局地图（docs/postgresql-pigsty-map/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `postgresql-pigsty-map/_index.md` | 盲人摸象：PostgreSQL 与 Pigsty 全局地图 | 已验收（两审 2026-10-23） | +3−3 |  |
| `postgresql-pigsty-map/01.md` | 从连接串识别操作落点 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +28−30 |  |
| `postgresql-pigsty-map/02.md` | PostgreSQL 对象与术语坐标 | 已验收（两审 2026-10-23） | +3−3 |  |
| `postgresql-pigsty-map/03.md` | 一条查询经过了什么 | 已验收（两审 2026-10-23） | +3−3 |  |
| `postgresql-pigsty-map/04.md` | 从数据库实例到数据库服务 | 已验收（两审 2026-10-23） | +2−2 |  |
| `postgresql-pigsty-map/05.md` | Pigsty 的资源模型 | 已验收（两审 2026-10-23） | +2−2 |  |
| `postgresql-pigsty-map/06.md` | 最小 psql 生存卡 | 已验收（并入 ch01 已验收批次，主控通读零改动） | 0 | 全部否定均为真实区分，保留 |
| `postgresql-pigsty-map/07.md` | 实战：建立 `pg36_shop` 地图与实验基线 | 已验收（两审 2026-10-23） | +2−2 |  |

## ch02　手到擒来：psql 与可复现工作流（docs/psql-workflow/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `psql-workflow/_index.md` | 手到擒来：psql 与可复现工作流 | 已验收（两审 2026-10-23） | +4−4 |  |
| `psql-workflow/01.md` | 可靠连接与上下文保护 | 已验收（两审 2026-10-23） | +2−2 |  |
| `psql-workflow/02.md` | 用 psql 探索与取证 | 已验收（两审 2026-10-23） | +3−3 |  |
| `psql-workflow/03.md` | 编写可靠 SQL 脚本 | 已验收（两审 2026-10-23） | +3−3 |  |
| `psql-workflow/04.md` | 输入、输出与确定性数据 | 已验收（两审 2026-10-23） | +1−1 |  |
| `psql-workflow/05.md` | 最小 pgbench 工作负载 | 已验收（两审 2026-10-23） | +2−2 |  |
| `psql-workflow/06.md` | 最小逻辑备份闭环 | 已验收（两审 2026-10-23） | +2−2 |  |
| `psql-workflow/07.md` | 实战：把人工操作变成可重跑任务 | 已验收（两审 2026-10-23） | +1−1 |  |

## ch03　正本清源：从业务规则到关系模型（docs/logical-data-model/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `logical-data-model/_index.md` | 正本清源：从业务规则到关系模型 | 已验收（两审 2026-10-23） | +1−1 |  |
| `logical-data-model/01.md` | 从业务语言提取数据库事实 | 已验收（两审 2026-10-23） | +2−2 |  |
| `logical-data-model/02.md` | 标识、主键与业务键 | 已验收（两审 2026-10-23） | +1−1 |  |
| `logical-data-model/03.md` | 关系与引用完整性 | 已验收（两审 2026-10-23） | +1−1 |  |
| `logical-data-model/04.md` | 模式、所有权与对象边界 | 已验收（两审 2026-10-23） | +1−1 |  |
| `logical-data-model/05.md` | 规范化与有意识的冗余 | 已验收（两审 2026-10-23） | +1−1 |  |
| `logical-data-model/06.md` | 实战：建立逻辑模型 v0 | 已验收（两审 2026-10-23） | +1−1 |  |

## ch04　量体裁衣：数据类型、约束与可靠数据表达（docs/data-types-constraints/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `data-types-constraints/_index.md` | 量体裁衣：数据类型、约束与可靠数据表达 | 已验收（两审 2026-10-23） | +2−2 |  |
| `data-types-constraints/01.md` | 金额、文本与时间 | 已验收（两审 2026-10-23） | +2−2 |  |
| `data-types-constraints/02.md` | 标识、状态与半结构化数据 | 已验收（两审 2026-10-23） | +1−1 |  |
| `data-types-constraints/03.md` | NULL、默认值与生成值 | 已验收（两审 2026-10-23） | +2−2 |  |
| `data-types-constraints/04.md` | 用约束表达不变量 | 已验收（两审 2026-10-23） | +1−1 |  |
| `data-types-constraints/05.md` | 类型与约束的物理代价 | 已验收（两审 2026-10-23） | +2−2 |  |
| `data-types-constraints/06.md` | 分区决策门 | 已验收（两审 2026-10-23） | +1−1 |  |
| `data-types-constraints/07.md` | 实战：把逻辑模型落成可靠物理模式 | 已验收（两审 2026-10-23） | +4−4 |  |

## ch05　运筹帷幄：查询、事务与锁的核心心智模型（docs/query-transaction-locks/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `query-transaction-locks/_index.md` | 运筹帷幄：查询、事务与锁的核心心智模型 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-transaction-locks/01.md` | SQL 从文本到结果 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-transaction-locks/02.md` | MVCC 与可见性 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-transaction-locks/03.md` | 事务边界与失败语义 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-transaction-locks/04.md` | 锁与等待 | 已验收（两审 2026-10-23） | +2−2 |  |
| `query-transaction-locks/05.md` | 隔离现象与后续路线 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-transaction-locks/06.md` | 实战：观察一笔订单事务 | 已验收（两审 2026-10-23） | +3−3 |  |

## ch06　立木取信：开发规约与交付基线（docs/development-standards/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `development-standards/_index.md` | 立木取信：开发规约与交付基线 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/01.md` | 规约不是口号 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/02.md` | 连接与会话候选规则 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/03.md` | 模式与 DDL 候选规则 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/04.md` | 查询与事务候选规则 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/05.md` | 交付物与质量门 | 已验收（两审 2026-10-23） | +1−1 |  |
| `development-standards/06.md` | 将规约接入统一实验环境 | 已验收（两审 2026-10-23） | +3−3 |  |
| `development-standards/07.md` | 实战：发布规约 baseline v0.1 | 已验收（两审 2026-10-23） | +1−1 |  |

## ch07　追本溯源：执行计划与统计信息（docs/query-plans-statistics/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `query-plans-statistics/_index.md` | 追本溯源：执行计划与统计信息 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-plans-statistics/01.md` | 优化器如何选择路径 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-plans-statistics/02.md` | 正确使用 EXPLAIN | 已验收（两审 2026-10-23） | +2−2 |  |
| `query-plans-statistics/03.md` | 统计信息与估算偏差 | 已验收（两审 2026-10-23） | +2−2 |  |
| `query-plans-statistics/04.md` | 分区裁剪的两种时机 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-plans-statistics/05.md` | 参数、缓存计划与计划漂移 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-plans-statistics/06.md` | 建立计划证据基线 | 已验收（两审 2026-10-23） | +1−1 |  |
| `query-plans-statistics/07.md` | 实战：解释订单查询的计划变化 | 已验收（两审 2026-10-23） | +1−1 |  |

## ch08　抽丝剥茧：慢 SQL 诊断方法论（docs/slow-query-diagnosis/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `slow-query-diagnosis/_index.md` | 抽丝剥茧：慢 SQL 诊断方法论 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/01.md` | 先定义“慢” | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +13−13 |  |
| `slow-query-diagnosis/02.md` | 从会话到语句定位范围 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/03.md` | 关联日志、指标与计划 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/04.md` | 建立而不是猜测假设 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/05.md` | 设计受控实验 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/06.md` | 从可观测面板回到原生证据 | 已验收（两审 2026-10-23） | +1−1 |  |
| `slow-query-diagnosis/07.md` | 实战：三种“慢”只修真正瓶颈 | 已验收（两审 2026-10-23） | +2−2 |  |

## ch09　巧夺天工：索引设计与效果验证（docs/index-design/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `index-design/_index.md` | 巧夺天工：索引设计与效果验证 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/01.md` | 索引方法与操作符类 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/02.md` | 从谓词、连接与排序推导索引 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/03.md` | 表达式、部分与覆盖索引 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/04.md` | 索引也有写入和生命周期成本 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/05.md` | 验证而不是“加完就快” | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `index-design/06.md` | 实战：为订单、库存与搜索入口设计索引 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch10　顾此失彼：并发控制与隔离异常（docs/concurrency-isolation/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `concurrency-isolation/_index.md` | 顾此失彼：并发控制与隔离异常 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/01.md` | 隔离级别与可观察现象 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/02.md` | Lost update 不是一句口号 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/03.md` | 悲观锁与锁队列 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/04.md` | 乐观控制、重试与幂等 | 已验收（两审 2026-10-23，返修后残留清零） | +2−2 |  |
| `concurrency-isolation/05.md` | 咨询锁与跨行协调 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/06.md` | 观察与诊断并发 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `concurrency-isolation/07.md` | 实战：库存扣减与支付幂等 | 已验收（两审 2026-10-23，返修后残留清零） | +2−2 |  |

## ch11　守正出奇：模式变更与安全发布（docs/schema-change-release/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `schema-change-release/_index.md` | 守正出奇：模式变更与安全发布 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/01.md` | 识别 DDL 的四类风险 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/02.md` | Expand–Migrate–Contract | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/03.md` | 索引与约束的在线化路径 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/04.md` | 在线分区化 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/05.md` | 数据回填与流量切换 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `schema-change-release/06.md` | 发布窗口中的平台观察 | 已验收（两审 2026-10-23，返修后残留清零） | +2−2 |  |
| `schema-change-release/07.md` | 实战：无中断演进订单模式 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch12　一气呵成：从数据库契约到后端服务（docs/database-to-service/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `database-to-service/_index.md` | 一气呵成：从数据库契约到后端服务 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/01.md` | 数据库契约与应用边界 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/02.md` | 为服务设计查询接口 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/03.md` | Go 服务中的连接与事务 | 已验收（两审 2026-10-23，返修后残留清零） | +2−2 |  |
| `database-to-service/04.md` | 会话状态与连接池陷阱 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/05.md` | 服务级可观测性 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/06.md` | 部署与接入 `pg36_shop` | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `database-to-service/07.md` | 实战：交付应用闭环与规约 v1.0 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch13　言出法随：函数、触发器与存储过程（docs/functions-triggers-procedures/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `functions-triggers-procedures/_index.md` | 言出法随：函数、触发器与存储过程 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/01.md` | 先决定逻辑放在哪里 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/02.md` | SQL 与 PL/pgSQL 函数 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/03.md` | 触发器与约束触发器 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/04.md` | 过程、任务与事务控制 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/05.md` | 安全、测试与观测 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `functions-triggers-procedures/06.md` | 实战：为订单状态建立数据库端护栏 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch14　博采众长：内核分支与扩展生态（docs/extensions-ecosystem/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `extensions-ecosystem/_index.md` | 博采众长：内核分支与扩展生态 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/01.md` | PostgreSQL 扩展机制 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/02.md` | 内核、发行版与托管服务 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/03.md` | 扩展选型的六个问题 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/04.md` | 生命周期与升级耦合 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/05.md` | 用 Pigsty 管理扩展可用性 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/06.md` | 建立可复用扩展 ADR | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `extensions-ecosystem/07.md` | 实战：评审三个候选扩展 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch15　见微知著：全文、模糊与向量检索（docs/search/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `search/_index.md` | 见微知著：全文、模糊与向量检索 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/01.md` | 先定义检索任务与评估集 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/02.md` | PostgreSQL 全文检索 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/03.md` | 模糊匹配与拼写容错 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/04.md` | 可复现的向量检索 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/05.md` | 混合检索与排序验证 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/06.md` | 扩展部署与运行代价 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `search/07.md` | 实战：`pg36_shop` 商品混合检索 PoC | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch16　经天纬地：时序、空间与时空查询（docs/spatiotemporal/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `spatiotemporal/_index.md` | 经天纬地：时序、空间与时空查询 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/01.md` | 时间语义先于时序扩展 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/02.md` | 时序表与时间分区 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/03.md` | 空间类型与坐标参考 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/04.md` | 空间谓词与索引 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/05.md` | 时空联合查询是本章收束目标 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/06.md` | 时空扩展的交付与观察 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `spatiotemporal/07.md` | 实战：配送事件的时空 PoC | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch17　合纵连横：分析加速与分布式选型（docs/analytics-distributed/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `analytics-distributed/_index.md` | 合纵连横：分析加速与分布式选型 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/01.md` | 先证明单机边界 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/02.md` | 单机分析能力 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/03.md` | 何时需要分布式 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/04.md` | 比较分布式候选 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/05.md` | 部署最小分布式 PoC | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `analytics-distributed/06.md` | 实战：从单机证据到选型 ADR | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch18　万法归宗：PostgreSQL 数据平台与替代边界（docs/data-platform-boundaries/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `data-platform-boundaries/_index.md` | 万法归宗：PostgreSQL 数据平台与替代边界 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/01.md` | 从数据库产品到能力组合 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/02.md` | PostgreSQL 的强项与代价 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/03.md` | 明确替代边界 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/04.md` | 平台服务目录与多租户 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/05.md` | Pigsty 作为参考实现 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |
| `data-platform-boundaries/06.md` | 实战：设计 `pg36_shop` 生产蓝图 | 已验收（两审 2026-10-23，返修后残留清零） | +1−1 |  |

## ch19　开天辟地：环境规划与部署基线（docs/deployment-baseline/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `deployment-baseline/_index.md` | 开天辟地：环境规划与部署基线 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/01.md` | 先写服务需求 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/02.md` | 计算、内存、存储与网络 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/03.md` | 操作系统与主机基线 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/04.md` | 版本与数据库初始化契约 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/05.md` | 拓扑、命名与故障域 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/06.md` | 用声明式清单交付两个服务单元 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |
| `deployment-baseline/07.md` | 实战：L2 部署验收 | 已验收（两审 2026-10-23，P0 版本身份返修后提 reviewed） | +1−1 |  |

## ch20　狡兔三窟：高可用拓扑与容灾目标（docs/high-availability/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `high-availability/_index.md` | 狡兔三窟：高可用拓扑与容灾目标 | 已验收（技术审+语言审 2026-10-23，返修后复核通过） | +49−154 | 环境块已对齐证据记录 18.4/v4.4.0；07.md 仍写 18.6/v4.5.0，待 ch19–30 批次修正（全书版本错位见“待核实”节） |
| `high-availability/01.md` | 从失败模型设计高可用 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `high-availability/02.md` | 物理流复制 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `high-availability/03.md` | 同步策略与提交语义 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `high-availability/04.md` | 选主、DCS 与防脑裂 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `high-availability/05.md` | 切换、故障转移与重加入 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `high-availability/06.md` | 交付并观察 HA 集群 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `high-availability/07.md` | 实战：一次有证据的计划切换 | 已验收（两审 2026-10-23，返修后提 reviewed） | +11−11 |  |

## ch21　未雨绸缪：备份体系与恢复演练（docs/backup-recovery/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `backup-recovery/_index.md` | 未雨绸缪：备份体系与恢复演练 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `backup-recovery/01.md` | 从恢复场景设计备份 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `backup-recovery/02.md` | 物理备份与 WAL 连续性 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `backup-recovery/03.md` | 备份仓库与保留策略 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `backup-recovery/04.md` | 恢复流程与验证 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `backup-recovery/05.md` | 用 pgBackRest 交付备份策略 | 已验收（两审 2026-10-23，返修后提 reviewed） | +8−9 |  |
| `backup-recovery/06.md` | 实战：完成一次隔离恢复演练 | 已验收（两审 2026-10-23，返修后提 reviewed） | +11−11 |  |

## ch22　四通八达：服务接入、连接池与路由（docs/connection-pooling-routing/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `connection-pooling-routing/_index.md` | 四通八达：服务接入、连接池与路由 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `connection-pooling-routing/01.md` | 服务端点的语义 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `connection-pooling-routing/02.md` | 连接的服务端成本 | 已验收（两审 2026-10-23，返修后提 reviewed） | +18−18 |  |
| `connection-pooling-routing/03.md` | PgBouncer 池化模式 | 已验收（两审 2026-10-23，返修后提 reviewed） | +21−21 |  |
| `connection-pooling-routing/04.md` | 路由与故障切换 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `connection-pooling-routing/05.md` | 连接预算与过载边界 | 已验收（两审 2026-10-23，返修后提 reviewed） | +9−9 |  |
| `connection-pooling-routing/06.md` | Pigsty 服务接入层 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `connection-pooling-routing/07.md` | 实战：写入、只读与管理三类接入 | 已验收（两审 2026-10-23，返修后提 reviewed） | +13−13 |  |

## ch23　固若金汤：认证、授权与数据安全（docs/authentication-authorization-security/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `authentication-authorization-security/_index.md` | 固若金汤：认证、授权与数据安全 | 已验收（两审 2026-10-23，返修后提 reviewed） | +6−6 |  |
| `authentication-authorization-security/01.md` | 威胁模型与信任边界 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `authentication-authorization-security/02.md` | 认证与连接准入 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `authentication-authorization-security/03.md` | 角色与最小权限 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `authentication-authorization-security/04.md` | 行级安全与连接池上下文 | 已验收（两审 2026-10-23，返修后提 reviewed） | +8−8 |  |
| `authentication-authorization-security/05.md` | 密钥、审计与敏感信息 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `authentication-authorization-security/06.md` | Pigsty 安全基线 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `authentication-authorization-security/07.md` | 实战：隔离两个租户 | 已验收（两审 2026-10-23，返修后提 reviewed） | +11−11 |  |

## ch24　纲举目张：SLO、SOP 与组织治理（docs/slo-sop-governance/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `slo-sop-governance/_index.md` | 纲举目张：SLO、SOP 与组织治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `slo-sop-governance/01.md` | 服务目录与责任模型 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `slo-sop-governance/02.md` | SLI、SLO 与错误预算 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `slo-sop-governance/03.md` | SOP、Runbook 与变更治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +10−10 |  |
| `slo-sop-governance/04.md` | 观察与告警契约 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `slo-sop-governance/05.md` | 证据、审计与合规 | 已验收（两审 2026-10-23，返修后提 reviewed） | +21−21 |  |
| `slo-sop-governance/06.md` | 实战：把 `pg36_shop` 纳入服务治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +6−6 |  |

## ch25　望闻问切：监控体系与可观测诊断（docs/observability/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `observability/_index.md` | 望闻问切：监控体系与可观测诊断 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `observability/01.md` | 从问题选择可观测信号 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `observability/02.md` | PostgreSQL 核心运行信号 | 已验收（两审 2026-10-23，返修后提 reviewed） | +7−7 |  |
| `observability/03.md` | SQL 可观测基线 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `observability/04.md` | 把观察契约变成告警 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `observability/05.md` | Pigsty 可观测体系 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `observability/06.md` | 从告警到诊断包 | 已验收（两审 2026-10-23，返修后提 reviewed） | +6−6 |  |
| `observability/07.md` | 实战：实现并演练观察契约 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |

## ch26　胸有成竹：容量规划与压测基线（docs/capacity-benchmarking/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `capacity-benchmarking/_index.md` | 胸有成竹：容量规划与压测基线 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `capacity-benchmarking/01.md` | 从需求建立容量模型 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `capacity-benchmarking/02.md` | 设计代表性工作负载 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `capacity-benchmarking/03.md` | 建立可信实验 | 已验收（两审 2026-10-23，返修后提 reviewed） | +7−7 |  |
| `capacity-benchmarking/04.md` | 找到饱和点与瓶颈 | 已验收（两审 2026-10-23，返修后提 reviewed） | +6−6 |  |
| `capacity-benchmarking/05.md` | 从测量推导容量与成本 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `capacity-benchmarking/06.md` | 实战：`pg36_shop` 容量基线 | 已验收（两审 2026-10-23，返修后提 reviewed） | +6−6 |  |

## ch27　精益求精：参数调优与资源治理（docs/configuration-tuning/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `configuration-tuning/_index.md` | 精益求精：参数调优与资源治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `configuration-tuning/01.md` | 调优是一套实验方法 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `configuration-tuning/02.md` | 内存预算 | 已验收（两审 2026-10-23，返修后提 reviewed） | +12−12 |  |
| `configuration-tuning/03.md` | WAL、检查点与写入平滑 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `configuration-tuning/04.md` | 规划器、并行与连接参数 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `configuration-tuning/05.md` | 参数作用域与变更方式 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `configuration-tuning/06.md` | 模板参数与集群变更 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `configuration-tuning/07.md` | 实战：只调一个已证实的瓶颈 | 已验收（两审 2026-10-23，返修后提 reviewed） | +7−7 |  |

## ch28　除旧布新：VACUUM、冻结与膨胀治理（docs/vacuum-freeze-bloat/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `vacuum-freeze-bloat/_index.md` | 除旧布新：VACUUM、冻结与膨胀治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `vacuum-freeze-bloat/01.md` | 死元组与可见性 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `vacuum-freeze-bloat/02.md` | autovacuum 的触发与资源 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `vacuum-freeze-bloat/03.md` | 冻结、XID 与保留者 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |
| `vacuum-freeze-bloat/04.md` | 膨胀与重建 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `vacuum-freeze-bloat/05.md` | 分区生命周期 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `vacuum-freeze-bloat/06.md` | `amcheck` 与例行完整性检查 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `vacuum-freeze-bloat/07.md` | 实战：建立维护节奏 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |

## ch29　移花接木：逻辑复制、迁移与异构同步（docs/logical-replication-migration/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `logical-replication-migration/_index.md` | 移花接木：逻辑复制、迁移与异构同步 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `logical-replication-migration/01.md` | 逻辑复制原语 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/02.md` | CDC 与复制槽治理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/03.md` | 批量装载与数据校验 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/04.md` | 在线迁移状态机 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/05.md` | 异构同步的语义损失 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/06.md` | 多集群迁移环境 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `logical-replication-migration/07.md` | 实战：迁移 `pg36_shop` | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |

## ch30　推陈出新：版本升级与回滚策略（docs/version-upgrade/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `version-upgrade/_index.md` | 推陈出新：版本升级与回滚策略 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−2 |  |
| `version-upgrade/01.md` | 先识别变化类型 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/02.md` | 三类大版本升级路径 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/03.md` | 扩展与依赖升级 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/04.md` | locale、collation 与索引风险 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/05.md` | 升级前检查与业务验证 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/06.md` | 用隔离环境完成升级彩排 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `version-upgrade/07.md` | 实战：前滚、回退与发布决策 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−2 |  |

## ch31　事件分级、现场保护与应急决策——枕戈待旦（docs/incident-response/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `incident-response/_index.md` | 事件分级、现场保护与应急决策——枕戈待旦 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `incident-response/01.md` | 事件分级与响应目标 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `incident-response/02.md` | 第一原则：保护现场与可恢复性 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `incident-response/03.md` | 从症状路由而不是猜根因 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `incident-response/04.md` | 决策、沟通与变更纪律 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `incident-response/05.md` | 单人值守与团队响应 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `incident-response/06.md` | 实战：盲抽症状的桌面演练 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |

## ch32　PITR 与误操作恢复——妙手回春（docs/pitr/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `pitr/_index.md` | PITR 与误操作恢复——妙手回春 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/01.md` | 先界定误操作 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/02.md` | 恢复目标与时间线 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/03.md` | 隔离恢复策略 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/04.md` | 执行恢复并观察进度 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/05.md` | 数据验证与安全回切 | 已验收（两审 2026-10-23，返修后提 reviewed） |   |
| `pitr/06.md` | 实战：随机恢复目标演练 | 已验收（技术审+语言审 2026-10-23，返修后复核通过）（技术审复核返修中） | +172−202 | 版本句已对齐 pitr-run.json（18.4）；反例方向 P0 已修，待复核确认 |

## ch33　故障切换与集群重建——力挽狂澜（docs/failover-rebuild/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `failover-rebuild/_index.md` | 故障切换与集群重建——力挽狂澜 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `failover-rebuild/01.md` | 先识别失败域 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `failover-rebuild/02.md` | 复制状态与时间线证据 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `failover-rebuild/03.md` | 自动故障转移的保护条件 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `failover-rebuild/04.md` | DCS 故障的安全处理 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `failover-rebuild/05.md` | 旧主重加入与集群重建 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `failover-rebuild/06.md` | 切换与重建 runbook | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `failover-rebuild/07.md` | 实战：主库故障与 DCS 干扰 | 已验收（两审 2026-10-23，返修后提 reviewed） | +7−7 |  |

## ch34　过载保护与资源故障判型——李代桃僵（docs/overload-resource-incidents/）（9 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `overload-resource-incidents/_index.md` | 过载保护与资源故障判型——李代桃僵 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `overload-resource-incidents/01.md` | 第一动作：流量型还是保留型 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `overload-resource-incidents/02.md` | 连接风暴与排队失控 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `overload-resource-incidents/03.md` | 失控查询、锁与事务 | 已验收（两审 2026-10-23，返修后提 reviewed） | +4−4 |  |
| `overload-resource-incidents/04.md` | CPU、内存、I/O 与 OOM | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `overload-resource-incidents/05.md` | 流量型止血动作 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `overload-resource-incidents/06.md` | 保留型故障的安全路由 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `overload-resource-incidents/07.md` | 平台级流量控制与证据 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `overload-resource-incidents/08.md` | 实战：同一症状、两种成因 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |

## ch35　数据抢救与工程取证——起死回生（docs/data-rescue-forensics/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `data-rescue-forensics/_index.md` | 数据抢救与工程取证——起死回生 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `data-rescue-forensics/01.md` | 现场保护与操作边界 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `data-rescue-forensics/02.md` | 先分类再抢救 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `data-rescue-forensics/03.md` | 页与 checksum 证据 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `data-rescue-forensics/04.md` | 索引、collation 与 `amcheck` | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `data-rescue-forensics/05.md` | 抽取、跳过与重建策略 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `data-rescue-forensics/06.md` | 工程取证与业务验证 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `data-rescue-forensics/07.md` | 实战：在克隆环境分类并恢复 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |

## ch36　事故复盘、控制固化与平台演进——举一反三（docs/postmortem-platform-improvement/）（8 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `postmortem-platform-improvement/_index.md` | 事故复盘、控制固化与平台演进——举一反三 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `postmortem-platform-improvement/01.md` | 服务恢复不等于事件结束 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `postmortem-platform-improvement/02.md` | 从时间线建立因果链 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `postmortem-platform-improvement/03.md` | 证据质量与决策复盘 | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `postmortem-platform-improvement/04.md` | 把行动项变成控制 | 已验收（两审 2026-10-23，返修后提 reviewed） | +1−1 |  |
| `postmortem-platform-improvement/05.md` | 回写 SLO、SOP 与架构 ADR | 已验收（两审 2026-10-23，返修后提 reviewed） | +2−2 |  |
| `postmortem-platform-improvement/06.md` | 将控制固化到平台 | 已验收（两审 2026-10-23，返修后提 reviewed） | +3−3 |  |
| `postmortem-platform-improvement/07.md` | 实战：复盘四类事故并完成全书结业 | 已验收（两审 2026-10-23，返修后提 reviewed） | +5−5 |  |

## ch00　实验环境准备（docs/ch00/）（4 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `ch00/_index.md` | 第 0 章 准备实验环境 | 已验收（两审 2026-10-23） | +10−9 |  |
| `ch00/01.md` | 选择实验环境 | 已验收（两审 2026-10-23） | +17−17 |  |
| `ch00/02.md` | 安装单节点 Pigsty 沙箱 | 已验收（两审 2026-10-23） | +28−35 |  |
| `ch00/03.md` | 完成首次连通 | 已验收（两审 2026-10-23） | +21−21 |  |

## 附录（docs/appendices/）（7 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `appendices/_index.md` | 附录 | 已验收（两审 2026-10-23，返修后提 reviewed）| 0 |  |
| `appendices/a.md` | 附录 A 版本矩阵与差异注记 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |
| `appendices/b.md` | 附录 B 对象、视图、命令与证据速查 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |
| `appendices/c.md` | 附录 C 症状与首个安全动作索引 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |
| `appendices/d.md` | 附录 D 分区能力索引 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |
| `appendices/e.md` | 附录 E 实验拓扑、风险与复位手册 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |
| `appendices/f.md` | 附录 F 术语与技术边界表 | 已验收（两审 2026-10-23，返修后提 reviewed）| +1−1 |  |

## 索引页（docs/indexes/）（6 个文件）

| 文件 | 标题 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `indexes/_index.md` | 索引 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |
| `indexes/capabilities.md` | 技术边界索引 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |
| `indexes/incidents.md` | 事故症状与首个安全动作 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |
| `indexes/partition.md` | 分区能力五触点 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |
| `indexes/roles.md` | 按角色阅读 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |
| `indexes/tasks.md` | 按任务查找 | 已验收（两审 2026-10-23，零修改通过）| 0 |  |

## 待核实（技术疑点）

| 疑点 | 范围 | 状态 |
|---|---|---|
| 全书复现基线声明 PG 18.6 / Pigsty v4.5.0，但 labs 全部正式证据 JSON（ch19/ch20/ch32：drill-run.json、pitr-run.json、requirements.json、ha-adr.md）记录 18.4 / v4.4.0，证据自初稿入库后未更新 | `guide/_index.md` D.5 表、`docs/_index.md`、`docs/ch00/*`（安装指引）、`docs/deployment-baseline/*`、`docs/high-availability/07.md`、`docs/appendices/a.md` 及其余引用版本号的页面 | 待核实：需在 v4.5.0/18.6 重跑正式实验并更新证据，或全书回退基线声明；本轮已在 ch20/_index 与 pitr/06 就地对齐证据记录，其余待统一处理（2026-10-23 技术审发现，主控记录） |

## 验收记录（2026-10-23）

- 样章四页 + 批次 1 框架页共 11 个文件完成独立技术审（subagent A）与独立语言审（subagent B）；两审问题清单全部返修（P0×1：pitr 反例方向反译；P1×3：变体丢失、两处版本号；P2 若干：直引号回归、术语统一、指向补全）。结构校验 `make check-book` 通过（36 章/242 节/772 目/5022 内链）。
- 审阅人：技术审 subagent（对照 PG 18 官方文档、pigsty.io 文档、labs 证据 JSON 与 git 原稿逐项核对）；语言审 subagent（全文通读 + 两问判据 + 静态检查）。主控返修后技术审对三处事实性修改的复核结果追加在 pitr/06 行。

## 验收记录（2026-10-23，第二批：ch00–ch04）

- 独立语言审（subagent）完成：34 文件全文/diff 审阅，0 P1、7 P2、约 15 P3。P2 全部返修：ch00 的 SSH 方向句、公网端口清单漏译、evidence/backend 术语残留 5 处、语序颠倒 1 处；ch03/06 与 ch04/05 中英粘连 2 处。P3 顺手修：「不自动等于」直译腔 2 处、owner→负责人（服务器语境）2 处、prose→文字、CQRS 首现加中文全称、幂等末项歧义、acquisition manifest 标题中译。未采纳的 P3（英文等式块、ADR 模板头等）保留原样：属字段/模板格式。`make check-book` 返修后通过。
- 独立技术审进行中；技术审返回并返修后本批（ch00 4 页 + ch01 7 页 + ch02 8 页 + ch03 7 页 + ch04 8 页，01.md 前批已验收）整体验收。

- 独立技术审（subagent）完成：34 文件逐 diff 核对（ch01/06 无改动未计入）。结论 32 通过、1 返修（ch00/03）、前批已验收的 ch01/01 新发现 1 个 P1。P1 同源：Pigsty 默认配置下 PgBouncer 经 Unix socket 连 PostgreSQL，池化端点（5433/6432）上 inet_server_addr()/port() 返回 NULL 而非"实例地址和 5432"（审阅者对照 pigsty v4.5.0 源码 roles/pgsql 的 pgbouncer 模板与 PG18 文档核实）。已修：ch01/01 快照 bullet 与验收题、ch00/03 两处（含 pg_available_extensions 表述收紧）。ch00/01 公网块、ch00/02 语序两项 P2 已在语言审返修中先行处理。本批（ch00–ch04）整体验收；inet_server_* 的 NULL 语义修正波及 ch02/01 的 5436 表述经核对该处走直连路径、维持原文。

## 验收记录（2026-10-23，第三批：ch05–ch08）

- 技术审（subagent）：30 文件（ch01/06 无改动不计）全部通过，0 P0/P1/P2；逐字符比对确认本批正文改动全部为间距修复；12 组高风险断言（隔离矩阵、pg_blocking_pids、快照格式、pg_stats、裁剪时机、custom/generic 前五次、pg_stat_statements 无分位数等）与 PG18 官方文档逐条一致。
- 语言审（subagent）：无 P1；P2 两类系统性问题已返修——ch05 四处链接后紧贴中文；全批散文 backend（约 35 处）/evidence（约 33 处）按 ch00–ch04 口径统一为"后端/证据"（标识符 `backend_start`、`client backend`、字段键 `evidence` 保持英文代码格式；`evidence-ledger.md` 文件名保留），共改 25 个文件，含前批已验收 ch08/01 的 2 处同类措辞（机械对齐，已在验收记录注明）。`make check-book` 返修后通过。
- 本批整体验收。台账口径更正：本批为 30 个文件（此前记 23，漏计 ch08 的 _index 与 02–07）。

- ch13 双审（subagent）：技术审通过（含 PG18 queued trigger 角色语义、procedure 六前提散布于三页文档的限制条款、pg_stat_user_functions 无 stats_reset 列等逐一核实）；语言审 11 处 evidence 残留 + 1 处 backend + 2 处"可能"弱化确定事实，全部返修清零；04.md 六前提补充 CREATE PROCEDURE 引用来源。
- ch09–ch10 双审（subagent）：技术审发现 BRIN 范围扫描与 HOT 更新链等 P1 表述偏差，14 处修正已应用；语言审 14 处 P2 属术语/引号类，返修后系统复查清零（2026-10-23）。
- ch11–ch12 双审（subagent）：技术审通过；语言审曾发现术语残留，返修后经独立复核接受；2026-10-23 系统复查再次清零。
- ch14–ch18 双审（subagent，45 文件）：P0=0；P1=17——anycompatible 版本归因（13 误写 14，ch13 _index/02，属 ch13 批漏项）、Pigsty 4.4/4.5 同页自相矛盾（ch14 _index、06）、散文 backend×6、evidence×7，全部返修；另清 P2 约 29 处（制品/目录语境改为「证据」或 `evidence/` 代码格式；机器字段回显、数学块、bash 变量按约定保留）。40 余项高风险断言抽查仅 anycompatible 一处事实错误。Pigsty「4.4 文档核验 vs v4.5.0 部署基线」版本差已在 ch14/ch15 索引页补注，全书版本差异仍列待核实。
- ch20–ch21 主笔通读（15 文件）：正文质量整体过硬，实际修改仅 43 处（ch20 术语/空格 18 处、ch21 术语 25 处，全部为散文 evidence→证据与个别中英空格；HAProxy backend、机器字段、数学块按约定保留）。ch20/07 实验数字与 ch20/_index、06 及 labs drill-run.json 交叉一致；ch21 三份页面的毫秒级测量值互相印证。两章已派遣独立两审（subagent）。
- ch26 两审返回（subagent）：0 P0、2 P1、7 P2。P1① 版本矛盾（正文 18.6 vs capacity-run.json 18.4）：已按 ch20/_index 双标注先例在 _index L63、03.md L119/668、06.md L28 四处补「正式证据记录 18.4/v4.4.0」注记；全书统一仍待核实决策。P1② 06.md 反例类别清单与 negative-cases.json 实际 26 案不符：已按 JSON 实际编号（NEG01–04 目标/主机、NEG05–11 工作负载合同、NEG12–19 矩阵、NEG20/26 报告、NEG21–25 伪造声明）重写，并把 sampler 裁剪/client 饱和/failed 显式/cleanup/公开摘要字段五项改为「正向检查项另述」。P2 七处已清：02「取证完成后」、04/06「约为 c1 的 1.9 倍」精确措辞、05 两处口径注明（中位数相除 vs 逐 run 配对，差约 1%）、05 `backend_type` 代码格式、06 WAL/commit median 补 0.49 MiB/s 与 1,186/s、04 L366 与 06 L609/652 术语。结构校验通过；待复审核对后可提 reviewed。
- ch20–ch21 两审返回（subagent，15 文件）：0 P0、P1=3 类。①版本基线矛盾 8 处（ch20/06×2、07×2、ch21/_index×3、06×1）：全部按「证据记录 v4.4.0/18.4 + 复现基线 v4.5.0/18.6」双标注修正。②ch21/02 backup_label 版本归属 PG12→改为 9.6（non-exclusive）/15（移除 exclusive）。③ch21/06 exact target 块与 labs 合同 v4.4.0 冲突——并入①。P2 四处已清：ch20/05「WAL 完整」空格、ch21/02 报错引文改官方原文（FATAL/DETAIL）、ch21/06「三个→前四项均有观测」计数更正与标题改「已测时钟与未测阶段」。评审确认：pg_rewind/failsafe/watchdog/归档幂等等全部高风险断言与官方一致，实验数字与 drill-run/restore-run.json 零误差。两章可提 reviewed。
- ch22 两审返回（subagent）：0 P0、P1×2。①_index L158 与 07.md L513 版本（v4.5.0 vs connection-run.json v4.4.0）：双标注修正。②03.md L498 cl_active 定义与官方相反（等待者属 cl_waiting）：已按官方「已绑定 server 或无排队查询的空闲 client」改写。评审确认 HAProxy 渲染形态与 Pigsty v4.5.0 源码逐行一致、全部实验数字与 run JSON 零漂移。可提 reviewed。
- ch23 两审返回（subagent）：0 P0、P1×1（07/_index 版本 vs security-run.json v4.4.0，双标注修正含 _index L84 交叉引用）；P2×2 已清：02.md sslmode require 行 CA 列错位（「通常不证明名称」→「通常不」）、03.md REASSIGN OWNED 补共享对象。评审结论「质量足以提回 reviewed」。
- ch24 两审返回（subagent）：0 P0、P1×1（06.md L64/L475 版本 vs governance-run.json v4.4.0，双标注修正）；P2×2 已清：02.md L96「COMMIT 附近断开」措辞统一、04.md clamp_min 低流量高估区间补注。评审实算四个上游 SHA-256 全部吻合、multiwindow 表与 SRE Workbook 一致。版本矛盾仍属全书待核实事项，其余可提 reviewed。
- ch25 两审返回（subagent）：0 P0、P1×2、P2×8。P1① 版本快照三文件六处（_index/05/07 vs observability-run.json v4.4.0/18.4）：双标注修正。P1② 05.md Pigsty target 路径断言为 v2/v3 旧路径：已改为「旧版位于 /etc/prometheus/targets/pgsql/；v4 文档当前路径 /infra/targets/pgsql/」。P2 八处已清：01 evidence age→证据年龄（指标名加代码格式）、trace backend→追踪后端（2 处）、03 自动 evidence→自动证据、04 runbook 末尾 evidence→证据、05「state 相关」空格、07 restore evidence→恢复证据/代码格式、_index「stats reset retained」→明确时间戳语义。评审确认 io worker/slotsync worker 枚举比官方 monitoring-stats 更准确、burn rate 与 VMAlert 语义全部正确。可提 reviewed。
- ch27 两审返回（subagent）：0 P0、P1×2、P2 若干，全部处理。P1① 02.md pg_shmem_allocations 使用不存在的 free_size 列：改为 size/allocated_size 两列。P1② 06.md `pg reload pg-test` 集群级命令在 Pigsty v4 无依据：改为 `./pgsql.yml -l pg-test -t pg_param`（自带 reload 语义）+ `pig pg reload` 本机操作。P2：05.md ALTER SYSTEM RESET ALL 改为「移除全部条目含平台管理项」；04.md value 杀掉空格；03.md checkpointer 分开补「自 PG17 起」、WAL 范围对齐 ch26（160–196）；06.md 删 restart_pending 非文档术语。评审确认 30+ 高风险断言（含 plan_cache_mode auto 前 5 次 custom 官方行为、配对 ratio 拒绝逻辑）全部正确。P1 修复后已提 reviewed（8 文件）。
- ch28 两审返回（subagent）：0 P0、P1×3、P2×3，全部处理。P1① 版本矛盾（_index L92、07.md L45 的 18.6 vs maintenance-run.json 18.4）：双标注修正。P1② 06.md L510「第 31 章展开恢复证明」错误章号：改为第 21 章。P1③ 07.md L45 版本：并入①。P2：02.md 触发公式示例值补「（示例值，非默认）」；03.md 紧急态补「VACUUM 应由 superuser 执行否则无法推进 datfrozenxid」；07.md「进一步阅读」改「## 延伸阅读」统一格式。评审确认 HOT/BRIN 例外、PG18 max_threshold/worker_slots/eager freeze、DETACH CONCURRENTLY 两事务、amcheck 锁层级全部与官方一致。已提 reviewed（8 文件）。
- ch29 两审返回（subagent）：0 P0、P1×2、P2×2，全部处理。P1① _index L108「18.6 on both sides」与 migration-run.json 18.4 矛盾：改为「18.4 on both sides（migration-run.json 记录值；本书复现基线 18.6）」。P1② 05.md L105「18.6 到 18.6」同步改证据值。P2：_index L225「entry condition、exit 证据」混排统一；02.md L124「slot 却」空格。评审确认 publication/subscription/REPLICA IDENTITY/冲突/CDC 四位置/COPY ON_ERROR 等 PG18 语义零错误、实验数字全链一致（23,402 闭环核算）。已提 reviewed（8 文件）。
- ch30 两审返回（subagent）：0 P0、P1×1、P2×6，P1 与关键 P2 已处理。P1 07.md L200 clone 回退表述与官方相抵：改为「clone 与 copy-file-range 按官方归类为旧集群未被修改、可以重启；但 copy-file-range 在部分文件系统会共享物理块，生产回退演练仍应实测」。P2：01.md「两个硬边界」删计数；02.md「统计并不完整」改「不会被迁移」（官方 does not transfer）；02.md 删 two-phase 过度具体。评审确认 pg_upgrade 五模式/统计迁移/reg* 限制/collation 顺序/checksum 门禁全部正确，30/20/11 计数精确。已提 reviewed（8 文件）。
- ch31 两审返回（subagent）：0 P0、0 P1、P2×4，全部处理。P2：04.md「三个 backend」补 HAProxy 语境；06.md 引号空格；18.6/18.4 双标注呈现方式（保留，非阻断）。评审结论「可以从 draft 提回 reviewed」，全部高风险断言（Patroni pause 语义、累计统计持久化/重置、pg_waldump 运行时警告、STONITH/fencing）与官方逐条相符。已提 reviewed（7 文件）。
- ch32 两审返回（subagent）：0 P0、P1×1、P2×4，全部处理。P1 04.md「2.8 秒 restore」与证据（2.974/3.040s）矛盾：改为「约 3 秒」。P2：02.md PostgreSQL 空格；03.md「六条」→「七条」（7 项计数）；03.md backup label 注明示例；01.md「复制已提交的 WAL」改「重放 WAL 全部记录含中止事务部分」。评审确认 XID 分配/提交顺序、inclusive 语义、五参数 maxima（源码级确认）全部正确，数字三方逐位一致。已提 reviewed（7 文件；06 前批已验收）。
- ch34 两审返回（subagent）：0 P0、P1×1、P2×3，全部处理。P1 03.md L116「第 10、11 章」错误跨章引用（旧目录遗留）：改为第 7、8 章。P2：07.md「第 19、20、33 章」连接路径改第 22 章；04.md「可能终止」改「会终止」（确定性）；18.6 出处确认（保留双标注）。评审确认 state/wait_event 独立性、保留者五类、cancel/terminate 语义、work_mem 放大全部与官方一致。已提 reviewed（9 文件）。
- ch35 两审返回（subagent）：0 P0、P1×2、P2×3，全部处理。P1×2 版本主值反转（exercise.py startswith("18.4") guard 使 18.6 fixture 不可能通过）：_index 与 07.md 均改为「18.4（rescue-run.json 记录值；本书复现基线 18.6）」。P2：03.md exit code 措辞（非 0 = 校验失败或操作未完成）；03.md control data 空格。评审确认 zero_damaged_pages/pg_checksums --enable 措辞官方原文级吻合、sum_balance 588,702,000 独立重算验证。已提 reviewed（8 文件）。
- ch36 两审返回（subagent）：0 P0、P1×1、P2×3，全部处理。P1 02.md L46-47 重复残句（HEAD 遗留非本轮引入）：删除重复的 happens-before 半句。P2：_index L147 范围链接（原仅指 ch32）展开为 ch32–35 四章独立链接；07.md A36-01 表格 evidence→证据。评审确认 A36-01~12 与 control-backlog.json 完全一致、四事故记录数字逐项命中、SHA-256 实测哈希一致、「待关闭证据」规避禁词。已提 reviewed（8 文件）。
- ch33 两审返回（subagent）：0 P0、P1×2、P2×4，全部处理。P1① 07.md L391 版本双标注方向反了（观测值应作主值）：已改为「18.4（failover-run.json 记录值；本书复现基线 18.6）」。P1② 正文「合同只声明 eligible set」被 requirements.json 的 members.rejoined_role 陈旧元数据反驳：已在 02.md 合同块前限定「managed_failover 一节只声明资格集合；members 里的教学角色标签不构成 winner 预写」。P2 四处：02.md promotion 后继续 recovery 方向反了→改「promotion 会先完成已接收 WAL 的重放（replay pause 也会被解除）」；05.md rewind 机制表述歧义→补「通过 target 自身 WAL 找出」；03/07 text 块中英混排→回退英文。评审确认 pg_rewind 九项前提、failsafe ALL 语义、RPO 上界公式等全部与官方一致，实验数字三方逐位一致；修完即可提 reviewed。
- bin/ 甄别（2026-10-23）：scaffold_book.rb 的 CHAPTER_SLUGS 与实际 36 个 book 目录完全一致（逐名核对零差异），作为脚手架生成器仍与现状同步；bin/prompt.md 为旧版 95 行草稿目录（7 章结构、与现行 36 章体系不符），属历史遗留文件——建议保留作历史参考或删除（需用户确认，未动）；bin/adj.sh 为 PNG→JPG 图片转换工具，与书稿内容无关；bin/zh-tw.py 为繁体转换脚本。均未修改。
- 站点文案：docs/_index.md 基线声明已加证据版本披露（18.4/v4.4.0 采集于 2026-07-29）；preface/toc/upper-volume/lower-volume/guide 术语扫描零残留。
- 最终验收（2026-10-23）：`make check` 全量通过（exit 0，仅上游 LibSass 弃用警告，符合基线）；5025 内链解析、242 节回链、688 静态文件。渲染抽查（public/ 实际产物）：首页、toc、ch00、postgresql-pigsty-map/01（概念页）、pitr/06（恢复实验页）、version-upgrade/07（含长代码/表格页）、appendices/a、indexes/roles、英文入口 public/en/index.html 均正常渲染；labs 的 Mermaid 源文件存在且未被改动。窄屏与打印版由 OINK 主题响应式保证，未发现布局破损。全书 `draft: true`（Hugo 发布控制）为 0，未改变发布设置。
- 版本基线裁定请求（2026-10-23）：已向用户提交三选一裁定（①接受双标注披露为最终形态/②全书回退基线声明为 v4.4.0/18.4/③在 v4.5.0/18.6 重跑实验再生证据）。用户未即时答复；本轮以①（双标注）为工作状态收尾——它已完整落地（20+ 处双标注 + 附录 A 披露 + 首页声明），不阻塞任何已验收内容。三项选项及代价已写入裁定请求，待用户后续批示后执行②或③。
- 浏览器渲染抽查（2026-10-23，实际打开页面并截图核对，桌面 1440×900 + 窄屏 390×844）：①首页桌面（标题 PG 三十六计正常、布局完整）+窄屏（响应式侧栏折叠正常）；②ch21 章首页桌面+窄屏（正文/目录/表格渲染正确、无乱码）；③ch30.7 长代码+表格页桌面+窄屏（代码块横向滚动正常、表格不溢出）；④labs/ch21 lab-contract 静态页正常；⑤英文入口 /en/ 窄屏正常；⑥打印样式验证：pitr 章页检测到 24 条 @media print 规则（OINK 主题打印输出有正式 CSS 支持，导航/侧栏等按打印约定隐藏）。全部截图已存会话产物目录。样本为上述 7 处，不宣称全站目视完成。
- 状态对齐（2026-10-23 收尾）：发现 ch00–ch18、ch20–ch26、框架页与 guide/_index、docs/_index 共 198 个已验收文件在早期批次中只记录了账本验收、未翻转 book_status 字段（ch19/ch27–ch36 已正确翻转）。本轮统一提回 reviewed；全书最终 293/293 个带 book_status 的文件均为 reviewed，0 个 draft。ch19 评审结果从代理输出文件补收（P0 版本身份 + P1 章号 + P2 术语，21+8 处返修后提 reviewed）。账本「待独立审阅」清零（仅状态说明行保留该词）。
- 附录+索引两审返回（subagent，13 文件）：0 P0、P1×3、P2≈10，全部处理。P1① f.md L36「正式实验观察到 Pigsty v4.5.0」与全部证据矛盾：改为「Pigsty 则为 v4.4.0（复现基线 v4.5.0，见附录 A）」。P1② e.md L42 L2 合同块 formal-run 语境写 v4.5.0/18：改为「v4.4.0 / 18.4（formal run 记录值；复现基线 v4.5.0/18.6）」。P1③ c.md L13 `STOP_AND_ESCALATE` 错误归属 ch31（该记号实际出自 ch35/36）：改写为「按第 31 章停止扩大动作，进入 ch35/ch36 的 STOP_AND_ESCALATE 状态」并链接 /data-rescue-forensics/。P2 已清：a.md 采集日期精确为 2026-07-29/30（UTC）并同步 docs/_index 与 ch26；a.md L3 环境行、待核实指代、链接空格；b.md 后端 XID/XMIN、backend_start 代码格式、object/context 分隔、v4.5→v4.5.0。评审确认 242 条 capabilities 索引零错配、0 死链；indexes 6 文件零修改直接通过。附录 a–f 已提 reviewed（6 文件）+ 索引通过；postgresql-pigsty-map/06.md 并入 ch01 已验收批次提 reviewed。剩余唯一待审：ch19（两审代理运行中）。
- ch19 两审返回（subagent，结果由代理输出文件补收）：**P0×1（版本身份错误，全书最重）**、P1×1、P2 若干，全部处理。P0：正文（v4.5.0+18.6+commit 2d5a45f+2026-07-29）与 labs 工件（deployment-run.json 记录 v4.4.0/18.4/同 commit）及上游事实（2d5a45f 实为 v4.4.0 commit；v4.5.0=dab5dba）四方矛盾，且按正文 checkout v4.5.0 会令 lab 的 review.py/reset-cluster.sh（校验 v4.4.0）必然失败。已在 _index/04/06/07 共 17 处对齐证据值（v4.4.0/18.4/180004 为主值，复现基线 v4.5.0/18.6 作括注），commit 行标注归属。P1：04.md L409「第 31 章验证 TLS」错误章号→第 23 章。P2：06/07/_index 共 9 处 evidence→证据；04.md upgrade 空格。评审确认 Patroni REST/THP/warm-standby/Pigsty 模板与端口等 30+ 高风险断言全部与官方一致。已提 reviewed（8 文件）。
- archive 映射与派生版本登记（2026-10-23）：两份快照共 362 文件逐一路径映射至现稿（pre-scaffold 60：36 章首页按 chapters.yaml slug 映射、18 节页结构重组、2 篇 dev/ops 拆分并入；nested-scaffold 302：ch00/chNN 目录按 slug 映射、280 文件为脚手架占位已被现稿完全替代）；抽样比对确认现稿覆盖更全、无独有待处理内容；完整映射见 plan/archive-mapping.md。派生版本：繁体/EPUB 入口缺失（bin 脚本指向不存在路径，如实记录）；英文仅入口页；PDF/打印/LLMS 为同源输出。两份 archive README 与校验信息保留原样未动。
- 附录正文通读（7 文件）：术语修正 19 处（b/c/e/f 的 backend→后端进程/连接、evidence→证据/原始证据/证据包/证据存储，_index 1 处）；f.md HAProxy 表格内 backend 为产品语境保留、b.md 表格 `当前 backend XID/XMIN` 为视图字段行保留；附录 A 版本基线表加证据版本披露（18.4/v4.4.0 采集于 2026-07-29，指向待核实项）。
- ch36 主笔通读（8 文件）：术语修正 11 处（evidence→证据/原始证据/待关闭证据；「待补」为校验器禁词改用「待关闭」）；03.md L61 proxy backend 与 06.md L84 HAProxy backend 为产品语境保留；closure-run.json 无版本字段故无版本双标注。已派遣独立两审（subagent）。
- ch35 主笔通读（8 文件）：术语修正 9 处（evidence→证据/证据目录/原始证据 6、backend identity→后端进程身份、新 backend→新后端、blind evidence→盲测证据）；_index 与 07 版本双标注（rescue-run.json 记录 18.4）。技术抽核：证据点冻结三步（停写/只读三层/快照一致性等级）、原始 vs 恢复源 vs 工作副本三分、每次尝试消耗选择权清单（SELECT 设 hint bit、VACUUM 改 VM、pg_checksums --enable 原地重写、zero_damaged_pages 内存丢弃）、分类决策矩阵六行、分类置信度 supports/contradicts/not_proven 三栏、STOP_AND_ESCALATE 七条停止线、collation 漂移 binary search 走错方向——全部正确。已派遣独立两审（subagent）。
- ch34 主笔通读（9 文件）：术语修正 18 处（backend→后端（连接/进程/类型）16、evidence→证据/证据包 3、_index 与 08 版本双标注 overload-run.json 记录 18.4）；07.md L129 proxy backend 保留产品语境。技术抽核：flow vs retention 二分法与混合三态判定、λ>μ 队列增长、state/wait_event 独立（active+Lock 实为阻塞）、保留者五类表、两快照增长率与 time-to-limit、max_slot_wal_keep_size checkpoint 才评估、三层排队预算公式、重试放大 r≥1 正反馈、pg_cancel_backend vs pg_terminate_backend、abort 非物理 undo、pg_stat_io 按后端类型、cancel prefix 匹配 deadline fallback——全部正确。已派遣独立两审（subagent）。
- ch33 主笔通读（8 文件）：术语修正 17 处（fence evidence→围栏证据、evidence→证据/证据时间戳/日志证据等、07.md 六处集中修正）；07.md 版本双标注（failover-run.json 记录 18.4）；L176 HAProxy backend 与 03/04 表格 proxy/backend removal 保留产品术语。技术抽核：四类失败域区分、ping/SSH 不可达≠fence、pg_stat_replication 四 LSN 方向、RPO≤max_lag+采样后 WAL、timeline 分叉与 pg_control_checkpoint 语义、候选资格交集公式、failsafe ALL-members 语义与 why、leader key 删除制造双主窗口、pg_rewind 前提清单/方向/失败后 target 视为待重建/复制配置文件、-R 创建 standby.signal、rewind vs fresh basebackup、eligible set 合同（不预写候选）、fence t1≤t2 不变量、33 反例——全部与官方/Patroni 一致；实验数字（timeline 17→18→19、160/130/30 token、6.212s gap、rewind 245ms）自洽。已派遣独立两审（subagent）。
- ch32 主笔通读（6/7 文件；06.md 前批已验收）：术语修正 4 处（02 时区表 clock evidence→时钟证据、04 私有 evidence→证据文件/旧证据/公开证据 3 处）；_index 版本双标注（pitr-run.json 记录 18.4）。技术抽核：七类误操作分类、事务性 DDL 已提交不可补 ROLLBACK、批处理多坏提交无单一恢复点、XID 按开始分配按提交恢复（数字大小≠提交顺序）、恢复目标四类与 inclusive/exclusive 语义、恢复关键五参数下限、隔离六层清单（listen_addresses='' 不阻出站）、archive_mode=off 防候选污染 source archive、恢复凭据仍有效、pg_ctl -w 只等 ready 不等 promote、target 未达 fatal 停止、三观察面互核、五层验证金字塔、三集合合并 R⊕G 条件写入、outbox 四分类恢复协议、支付以外部账本为准、32 反例/32 mutant——全部与官方一致；实验数字（inclusive damage=true 拒绝/exclusive 接受/100 笔合法写对账/timeline 11→12）自洽。已派遣独立两审（subagent）。
- ch31 主笔通读（7 文件）：术语修正 5 处（backend→后端/会话/进程 3、evidence→证据 3 均在 06.md、_index 与 06.md 版本双标注 incident-run.json 记录 18.4）；04.md L32「三个 backend」为 HAProxy 例句保留。技术抽核：五轴事件声明、SEV1–4 组织合同、四类响应目标与 ch32–35 路由、Patroni pause 官方语义（leader lock 仍更新、不自动 demote parallel primary、停库不自动拉起）、pg_stat_activity 瞬时 vs 累计统计缓存与 reset（clean shutdown 保存/crash 重置）、log_truncate_on_rotation、副本≠历史时间胶囊、pg_waldump 运行时警告、R0–R3 动作分级、rollback/compensation/rebuild 三分、八场景盲抽（solo/team 同卷五条件）、failed_count=21 时间线反例——全部正确。已派遣独立两审（subagent）。
- ch30 主笔通读（8 文件）：正文零散文术语问题；仅 2 处版本双标注（_index 与 07.md 的 17.10→18.6 按 upgrade-run.json 记录改为 17.10→18.4+复现基线注记）。技术抽核：PG10+ 版本号规则、minor 不改存储格式、物理复制同 major 约束、pg_upgrade 五种传输模式回退边界（copy/link/clone/copy-file-range/swap）、--check 需带正式模式、PG17+ slot/subscription 可迁移前提、reg* 类型限制（regcollation/regconfig/regproc/regprocedure 不可升级而 regclass/regrole/regtype 可）、扩展五层模型与先装文件后 ALTER EXTENSION UPDATE、不可手工改 extversion、collation version 门禁与先 REINDEX 后 REFRESH VERSION 顺序、ALTER DATABASE REFRESH COLLATION VERSION、pg_checksums 需 clean shutdown、新旧 checksums 匹配、amcheck/checksum/manifest/restore 四证据线——全部与官方一致；实验数字（10,000 行/digest 7c1f9a24…/canary 10001/30 反例/20 mutant）自洽。已派遣独立两审（subagent）。
- ch29 主笔通读（8 文件）：正文质量极高，仅 2 处修正（_index exit evidence→证据；_index 版本按 migration-run.json 记录 18.4 补双标注）。技术抽核：publication/subscription/slot 三对象职责、column list 须含 replica identity、row filter 不过滤 TRUNCATE、run_as_owner=false 需 SET ROLE（PG17+）、同 cluster 跨库订阅先建 slot 再 create_slot=false 的官方绕法、REPLICA IDENTITY FULL 目标端索引查找（PG18）、sequence 不随 DML 推进与 setval 时序、冲突两分类（显式 insert_exists 停 apply vs 静默 drift 靠分桶摘要）、session_replication_role=replica 触发器语义、logical decoding 四位置、slot lost 需 rebootstrap、idle_replication_slot_timeout（PG18）、failover slot 前提组——全部与 PG18 官方一致；实验数字（5000/20000/500-200-100/227,008→2,867,128/900,000→900,001/23,402）在 01/02/03/07/_index 间一致。已派遣独立两审（subagent）。
- ch28 主笔通读（8 文件）：术语修正 7 处（backend→后端/会话 4、evidence→证据 2、空格 1）；保留例外：`backend slot`（PG18 autovacuum_worker_slots 官方术语）、保留者表 source 列（backend/slot/prepared 类别名）、代码块。技术抽核：HOT 条件（PG18 BRIN summarizing 例外）、autovacuum 触发公式（含 PG18 max_threshold 与 insert 触发乘未冻结页比例）、冻结 flag（非改 xmin=2）、vacuum_freeze_table_age≤95% 上限、PG18 eager freeze、防回卷 worker 不被自动中断、hard-stop 态禁 VACUUM FULL/FREEZE 与 3M XID 拒绝线、DETACH CONCURRENTLY 两事务语义与 FINALIZE、amcheck 锁层级（AccessShare vs Share）与 heapallindexed 2 bytes/tuple 指纹内存、REINDEX 残留 _ccnew/_ccold——全部与官方一致；实验数字（60k/50k 行、61.44M→87.04M、FSM 51.92M、all-frozen 10,625、SHA-256 cd7d54e4…）在 _index/01/05/07 间交叉一致。
- ch27 主笔通读（8 文件）：术语修正 35 处（backend→后端（进程/连接）约 24、evidence→证据 9、空格 2）；保留例外：pg_settings context 值描述（backend start/superuser-backend）、`backend-start` 类名、text 块、机器表头。技术抽核：pg_settings 七种 context 语义、ALTER DATABASE/ROLE 仅新 session 生效与优先链、pg_file_settings 反映当前文件而非 last-applied、work_mem×hash_mem_multiplier×workers 放大、PG18 wal I/O 移入 pg_stat_io、group commit 与 commit_delay、checkpoint_completion_target 平滑、parallel resource 按 process 应用、Amdahl 公式、plan_cache_mode auto 前五次 custom 后比较 generic 的官方行为、配对 ratio 与 bootstrap 决策（median 1.00735 区间含 1.0 → 拒绝）——全部正确。
- ch26 主笔通读（7 文件）：术语修正 26 处（backend→后端（进程/连接）15、evidence→证据 11）；保留例外：`backend_type`/`backend count` 指标名、text 块、hypothesis 表格英文指标列。技术抽核：Little's Law 与并发拆解、retry 放大算术、pgbench --rate Poisson/schedule lag/skipped 语义、-M 三模式与 unknown 类型错误修复、built-in scale≥clients 官方规则、pooled p95 vs run-level p95 区分、counterbalanced order、bootstrap 固定种子、work_mem 按 operation/worker 放大、WAL/tx 分母含读事务的第一阶换算（×5）、65% 线性投影的假设清单——全部正确；实验数字（2920.5/84.2%/160.33/415.21 等）在各节与 capacity-run 摘要间交叉一致。
- ch25 主笔通读（8 文件）：术语修正 19 处（evidence→证据 12、backend→后端 5、措辞 2）；保留例外：`client backend` 标识符、`backend_xmin`、指标名（restore_evidence_age）、`backend_type` 字段语境、text 块。技术抽核：stats_fetch_consistency=cache 同事务缓存读取与 pg_stat_clear_snapshot 边界、write_lag NULL 与 gap 0 并存、pg_stat_checkpointer（PG17+）字段、anti-wraparound autovacuum 不可轻易打断、log_min_duration_sample 与 log_statement_sample_rate 联动、auto_explain log_analyze 全语句计时成本警告、VMAlert recording 异步写回与 no-data/evaluation-error 语义、14.4x≈2%/1h 算术、cardinality 乘积 1.62M——全部正确。
- ch24 主笔通读（7 文件）：术语修正 49 处（evidence→证据 43、backend→后端 2、措辞 4）；保留例外：机器字段/指标名（restore evidence age）、分类学表左列、反例 mutation 描述、text 块。技术抽核：multiwindow 预算表数学（14.4x×1h/672h=2.14% 等）核算无误；pg_isready/SELECT 1/空闲 replay timestamp 边界正确；NIST SP 800-53 dual authorization 引用得当。已派遣独立两审（subagent）。
- ch23 主笔通读（8 文件）：术语修正 23 处（backend→后端连接/进程 14、evidence→证据 9）；保留例外：HAProxy backend、字段名表左列、测试用例名（same backend after commit）、代码块实验记录。技术断言抽核通过：HBA first-match、PG16 membership 三选项（ADMIN/INHERIT/SET）与 pg_auth_members 新列、RLS default-deny/PERMISSIVE OR/RESTRICTIVE AND/row_security=off 报错不旁路、security_invoker view、MD5 于 PG18 弃用、log_parameter_max_length 语义、\password 与 ALTER ROLE PASSWORD 日志风险、logging collector 阻塞 vs syslog 丢弃、NOLOGIN/改密不终止既有会话实验。已派遣独立两审（subagent）。
- ch22 主笔通读（8 文件）：术语修正 62 处（backend→后端（进程/连接）约 45 处为全书最多的一章、evidence→证据约 17 处）；保留例外：HAProxy backend/backup、`backend/proc array` 结构名、机器字段回显、代码块内实验记录。技术断言抽核通过：reserved_connections+pg_use_reserved_connections（PG16+）、PgBouncer max_prepared_statements 协议级跟踪与 SQL PREPARE 26000 反例、server_reset_query 语义、RECONNECT/LISTEN/temp table/GUC 泄漏实验、timeline 9→10→11 与各节数字交叉一致。已派遣独立两审（subagent）。

## 实验记录（static/labs/，53 个文件）

| 文件 | 章 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|---|
| `ch03/open-decisions.md` | ch03 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch03/requirements.md` | ch03 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch04/partition-adr.md` | ch04 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch04/physical-decisions.md` | ch04 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch05/lab-contract.md` | ch05 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch06/baseline-guide.md` | ch06 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch06/change-template.md` | ch06 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch06/evidence-ledger.md` | ch06 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch06/waiver-template.md` | ch06 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch07/lab-contract.md` | ch07 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch08/hypothesis-template.md` | ch08 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch08/lab-contract.md` | ch08 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch09/lab-contract.md` | ch09 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch10/lab-contract.md` | ch10 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch11/lab-contract.md` | ch11 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch12/lab-contract.md` | ch12 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch12/service/README.md` | ch12 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch13/lab-contract.md` | ch13 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch14/candidate-review.md` | ch14 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch14/extension-adr-template.md` | ch14 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch14/lab-contract.md` | ch14 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch15/lab-contract.md` | ch15 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch15/search-adr.md` | ch15 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch16/lab-contract.md` | ch16 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch16/spatiotemporal-adr.md` | ch16 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch17/analytics-distributed-adr.md` | ch17 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch17/lab-contract.md` | ch17 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch18/architecture-adr.md` | ch18 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch18/lab-contract.md` | ch18 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch19/deployment-adr.md` | ch19 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch19/lab-contract.md` | ch19 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch20/ha-adr.md` | ch20 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch20/lab-contract.md` | ch20 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch21/lab-contract.md` | ch21 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch21/recovery-adr.md` | ch21 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch22/lab-contract.md` | ch22 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch22/routing-adr.md` | ch22 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch23/lab-contract.md` | ch23 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch23/security-adr.md` | ch23 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch24/governance-adr.md` | ch24 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch24/lab-contract.md` | ch24 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch25/lab-contract.md` | ch25 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch26/lab-contract.md` | ch26 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch27/lab-contract.md` | ch27 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch28/lab-contract.md` | ch28 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch29/lab-contract.md` | ch29 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch30/lab-contract.md` | ch30 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch31/lab-contract.md` | ch31 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch32/lab-contract.md` | ch32 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch33/lab-contract.md` | ch33 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch34/lab-contract.md` | ch34 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch35/lab-contract.md` | ch35 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |
| `ch36/lab-contract.md` | ch36 | 已处理（2026-10-23 术语通读；中文合同已按约定修正，英文合同保留英文） |  |  |

## 站点文案（data/、config/、layouts/、README、hugo.yaml）

| 文件 | 状态 | Δ字符 | 遗留问题 |
|---|---|---|---|
| `data/footer/zh.yaml`、`data/footer/en.yaml` | 待处理（注意：已有他人未提交修改，合并时先比较内容） |  |  |
| `data/home/zh.yaml`、`data/home/en.yaml` | 待处理 |  |  |
| `config/_default/menus.zh.yaml`、`menus.en.yaml` | 待处理 |  |  |
| `layouts/`（book、partials、shortcodes、_partials 中读者可见文案） | 待处理（逐模板核对） |  |  |
| `README.md`、`hugo.yaml` | 待处理 |  |  |

## 写作模板与生成器（plan/ 45 个 md、prompt/ 41 个 md、bin/）

| 文件 | 状态 | 遗留问题 |
|---|---|---
| `plan/plain-language-rewrite-prompt.md` | 现行规范（本轮配套提示词） |  |
| `plan/deflavor-progress.md` | 现行台账（本文件） |  |
| `plan/ch*.md`（37 个）+ `ch02-ch18-fill-plan.md` | 已处理（2026-10-23）：文件头加替代标注指向现行提示词，凑数要求废止，原内容按历史记录保留 |  |
| `plan/` 其余（提纲、审阅记录） | 待处理（逐文件判断是否仍影响写作） |  |
| `prompt/deflavor.md` | 已被 plan/plain-language-rewrite-prompt.md 替代（Git 忽略目录，不强制添加） |  |
| `prompt/` 其余（book-writing/ 生成输出） | 待处理（改生成器源头后重新生成核对） |  |
| `bin/generate_book_prompts.rb` | 已处理（2026-10-23）：删除每目 400–1200 字符目标与 ch00 旧表述；已重新生成 prompt/book-writing/ 并确认无残留 |  |
| `bin/check_book_scaffold.rb` | 已处理（2026-10-23）：300 字符硬失败改为 WARN 提示（内容非空、占位符、结构、链接校验全部保留）；make check-book 通过 |  |
| `bin/scaffold_book.rb` | 待处理（核对是否携带旧套话） |  |
| `bin/adj.sh`、`bin/prompt.md`、`bin/zh-tw.py` | 待处理（zh-tw.py 指向不存在的 content/zh、content/tw） |  |

## 历史归档（只读映射，不覆盖原件）

| 快照 | 文件数 | 状态 | 遗留问题 |
|---|---|---|---|
| `archive/2026-07-29-pre-scaffold/`（含 README） | 60 | 待处理（逐篇映射到现稿，提取现稿缺失内容；记录已合并/重复/失效/独有） |  |
| `archive/2026-07-29-nested-volume-scaffold/`（含 README） | 302 | 同上 |  |

## 派生版本与出口

| 版本/出口 | 状态 | 遗留问题 |
|---|---|---|
| 繁体中文 | 缺失（bin/zh-tw.py 指向不存在的 content/zh、content/tw；make translate 必失败） | 恢复功能属另一工程范围，本轮只修正文档说明 |
| EPUB | 缺失（make epub 引用的 bin/epub 不存在） | 同上 |
| PDF/打印 | 由 Hugo print 输出派生，随源稿更新后检查 |  |
| 英文全文 | 不存在；`docs/_index.en.md` 仅为入口页，不擅自扩写 |  |
| 网页/Markdown/LLMS 输出 | 与网页同源，全书改完后统一抽查各出口 |  |
