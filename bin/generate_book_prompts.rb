#!/usr/bin/env ruby
# frozen_string_literal: true

require "fileutils"
require "pathname"
require "yaml"

ROOT = Pathname.new(__dir__).parent.expand_path
CHAPTERS_PATH = ROOT.join("data/chapters.yaml")
BOOK_PATH = ROOT.join("data/book.yaml")
DOCS_PATH = ROOT.join("docs")
OUTPUT_PATH = ROOT.join("prompt/book-writing")
SENTINEL = OUTPUT_PATH.join(".generated-by-prompt-builder")

EXPECTED_CHAPTERS = 36
EXPECTED_SECTIONS = 242
EXPECTED_ITEMS = 772

FOCUS_NAMES = {
  "PG" => "PostgreSQL 原生语义、机制与可复核证据",
  "平台" => "通用数据库平台职责、工程边界与运行证据",
  "Pigsty" => "Pigsty 参考实现、具体操作与 PostgreSQL 原生复核",
  "准备" => "实验环境准备、成功检查与安全复位"
}.freeze

def load_yaml(path)
  YAML.safe_load(path.read(encoding: "UTF-8"), aliases: false)
end

def front_matter_and_body(path)
  parts = path.read(encoding: "UTF-8").split(/^---\s*$\n?/, 3)
  raise "Missing front matter: #{path}" unless parts.length == 3

  [YAML.safe_load(parts[1], aliases: false), parts[2]]
end

def item_summary(path, item)
  _metadata, body = front_matter_and_body(path)
  lines = body.lines
  heading_prefix = "## #{item.fetch('number')} "
  heading_index = lines.index { |line| line.start_with?(heading_prefix) }
  raise "Missing item heading #{item.fetch('number')} in #{path}" unless heading_index

  summary = lines[(heading_index + 1)..].find { |line| !line.strip.empty? }
  raise "Missing item summary #{item.fetch('number')} in #{path}" unless summary

  summary.strip
end

def enrich_chapters(chapters)
  chapters.each do |chapter|
    chapter.fetch("sections").each do |section|
      page = DOCS_PATH.join(chapter.fetch("slug"), "#{section.fetch('slug')}.md")
      raise "Missing section page: #{page}" unless page.file?

      section.fetch("items").each do |item|
        item["summary"] = item_summary(page, item)
      end
    end
  end
end

def chapter_zero
  metadata, body = front_matter_and_body(DOCS_PATH.join("ch00/_index.md"))
  sections = DOCS_PATH.glob("ch00/[0-9][0-9].md").sort.map do |path|
    section_metadata, section_body = front_matter_and_body(path)
    items = []
    lines = section_body.lines

    lines.each_with_index do |line, index|
      next unless (match = line.match(/^## (\d+\.\d+\.\d+) (.+?) \{#(item-[^}]+)\}\s*$/))

      summary = lines[(index + 1)..].find { |candidate| !candidate.strip.empty? }
      raise "Missing item summary after #{match[1]} in #{path}" unless summary

      items << {
        "id" => match[3],
        "number" => match[1],
        "title" => match[2],
        "summary" => summary.strip
      }
    end

    {
      "number" => section_metadata.fetch("book_number"),
      "slug" => path.basename(".md").to_s,
      "title" => section_metadata.fetch("title").sub(/^\S+\s+/, ""),
      "capability" => "准备",
      "items" => items
    }
  end

  {
    "id" => "ch00",
    "number" => 0,
    "title" => metadata.fetch("title").sub(/^第 0 章（可跳过）/, ""),
    "slug" => "ch00",
    "goal" => body[/\*\*可跳过说明\*\*：(.+)$/, 1]&.strip ||
      "为尚未拥有实验环境的读者准备 Pigsty L1 沙箱，并完成首次 PostgreSQL 连通。",
    "volume_title" => "前置准备（可跳过）",
    "part_title" => "实验环境准备",
    "sections" => sections
  }
end

def escape_table(text)
  text.to_s.gsub("|", "\\|").gsub("\n", " ")
end

def book_map(chapters)
  lines = [
    "| 章 | 卷与篇 | 标题 | 本章目标 |",
    "|---|---|---|---|"
  ]
  chapters.each do |chapter|
    location = "#{chapter.fetch('volume_title')}；#{chapter.fetch('part_title')}"
    lines << "| #{chapter.fetch('id')} | #{escape_table(location)} | #{escape_table(chapter.fetch('title'))} | #{escape_table(chapter.fetch('goal'))} |"
  end
  lines.join("\n")
end

def detailed_outline(chapter, section_level: 3, item_level: 4)
  lines = []
  chapter.fetch("sections").each do |section|
    lines << "#{"#" * section_level} #{section.fetch('number')} #{section.fetch('title')}"
    lines << ""
    lines << "- 写作文件：`docs/#{chapter.fetch('slug')}/#{section.fetch('slug')}.md`"
    lines << "- 内部取证侧重点：#{FOCUS_NAMES.fetch(section.fetch('capability'), section.fetch('capability'))}"
    lines << "- 注意：这一侧重点只用于作者选择证据，不要在成书目录中反复输出“能力归属”或 `[PG]`、`[平台]`、`[Pigsty]` 标签。"
    lines << ""
    section.fetch("items").each do |item|
      lines << "#{"#" * item_level} #{item.fetch('number')} #{item.fetch('title')}"
      lines << ""
      lines << "**既定写作范围**：#{item.fetch('summary')}"
      lines << ""
    end
  end
  lines.join("\n")
end

def global_context(chapters)
  <<~PROMPT
    ## 一、全书使命

    你正在编写《PostgreSQL 36 计：从 SQL 到生产——PostgreSQL 与 Pigsty 实战》。这不是命令手册、产品宣传册或知识点百科，而是一套由浅入深、理论与实践闭环的工程教程。

    目标读者已经熟悉 Linux、Shell、SSH、文件与进程操作，掌握通用 SQL、DDL、CRUD、连接、聚合、子查询、CTE 和基础事务，至少使用过一种后端语言，也理解版本控制与测试；但他们尚未系统掌握 PostgreSQL。不要重新教授 Linux 和通用 SQL。第 0 章只负责实验环境，不承担基础课职能。

    全书最终要让认真完成阅读与实验的读者：

    1. 建立准确、可迁移的 PostgreSQL 心智模型，而不是只会背参数和命令；
    2. 能设计可靠模式、查询、事务、索引、并发控制、数据库接口和安全发布流程；
    3. 能选择并治理扩展，理解 PostgreSQL 的能力边界与替代边界；
    4. 能基于 Pigsty 规划、部署、接入、保护、观察、调优、维护和升级 PostgreSQL 服务；
    5. 能处理高可用、备份恢复、容量、安全、迁移和生产事故；
    6. 能用证据作出工程判断，知道结论的适用条件、反例、代价、风险和回退路径；
    7. 在应用开发与运维管理两条路径上达到熟练、可独立承担工作的专家水平。

    ## 二、全书架构与导航约束

    - 全书包含不可跳过的“全书导读”、可跳过的第 0 章、36 个正式章节、两个卷导读页、六篇、附录和多维索引。
    - ch01–ch18 属于“上卷：应用开发”，包含筑基、应用、扩展三篇。
    - ch19–ch36 属于“下卷：运维管理”，包含规划、运营、出山三篇。
    - 36 个正式章节始终是顶层、平铺的导航项。上卷页与下卷页也是顶层导读索引页，但绝不是章节父目录，不能把章节重新移动到卷目录下。
    - 每章一个语义目录：`docs/<chapter-slug>/_index.md` 是章首页；每一个“节”是单独页面 `01.md`、`02.md`……；每一个“目”使用稳定编号与锚点。
    - 不得擅自改变卷、篇、章、节、目编号，不得随意改名、合并、拆分或交换顺序。若发现严重技术问题，先说明证据和最小修订建议。
    - 普通目录、章节索引和节页面不显示重复的“能力归属”句子，也不在链接后追加 `[PG]`、`[平台]`、`[Pigsty]` 标签。相关分类只作为作者内部取证线索和专用技术边界索引的数据。

    ## 三、PostgreSQL 与 Pigsty 的叙述关系

    - PostgreSQL 是核心知识对象，所有关键结论优先解释 PostgreSQL 自身语义、机制与原生证据。
    - Pigsty 是统一实验载体、观察窗口和生产参考实现，用于把 PostgreSQL、Patroni、PgBouncer、HAProxy、pgBackRest、监控与自动化组合成可操作的服务。
    - 必须自然区分三类内容：PostgreSQL 原生能力、任何生产平台都要承担的通用职责、Pigsty 的具体实现。不要把 Pigsty 的实现误写成 PostgreSQL 唯一或通用的做法。
    - 每当介绍 Pigsty 操作，都应在适当位置回到 SQL、系统目录、配置文件、日志、指标或原生组件验证；对跨平台读者说明可迁移的职责边界，但不要扩写成其他平台教程。
    - 作者与 Pigsty 存在直接关系，正文必须克制营销语言，主动说明限制、替代方案、退出成本和适用边界。

    ## 四、教学方法

    采用“问题牵引—心智模型—最小证据—示范操作—受控练习—独立任务—验收复盘”的节奏。具体要求：

    1. 先说明读者为什么需要这一知识、它解决什么真实问题，再引入术语；
    2. 从直观现象进入内部机制，再回到工程决策，避免一开始堆系统目录和参数；
    3. 使用 worked example 展示完整推理，再逐步撤掉提示，让读者完成独立任务；
    4. 一个段落只承担一个主要认知任务；新概念成组引入并立即落到可观察证据；
    5. 对重要结论给出成立条件、反例、常见误区、失败表现和判断边界；
    6. 每章显式说明前置知识、本章交付物、后续章节如何消费这些交付物；
    7. 重复出现的主题采用螺旋式加深：后文复用前文结论，不大段重讲，也不假设读者凭空知道；
    8. 不为了显得丰富而堆功能、链接或工具；深度优先于罗列，证据优先于口号；
    9. 既解释“怎么做”，也解释“为什么这样做、何时不该这样做、做错后如何识别和恢复”；
    10. 章节完成后提供适量复习问题、迁移问题或独立练习，用可验证反馈帮助读者检索和巩固。

    ## 五、贯穿案例与实验拓扑

    全书主线案例为 `pg36_shop`：

    - ch01–ch12：持续演进的电商、库存、订单与支付应用；
    - ch13–ch18：复用核心模式的独立能力场景，不把所有扩展强塞进一个服务；
    - ch19–ch30：复用确定性数据和工作负载，把应用建设成生产数据库服务；
    - ch31–ch35：从已知快照克隆独立事故现场，避免故障演练彼此污染；
    - ch36：汇总事故证据，形成治理闭环和平台演进计划。

    实验环境分层：

    - `L1`：单节点 Pigsty 开发沙箱，主要用于 ch01–ch18；
    - `L2`：三节点、可销毁的生产仿真环境，主要用于 ch19–ch30；
    - `L3`：由已知快照克隆的隔离事故环境，主要用于 ch31–ch35。

    每章按需要提供 `setup`、`exercise`、`verify:state`、`checklist:evidence`、`expected`、`reset:sql`、`reset:cluster`、`reset:host`，不要机械凑齐。实验数据必须固定随机种子、规模档位和校验和；玩具环境只证明方法，不用于宣称绝对性能。

    ## 六、安全、版本与事实纪律

    - `R0·观察`：只读查询、状态采样、计划分析；
    - `R1·可逆变更`：改变对象、配置或流量，但必须有经过验证的回退路径；
    - `R2·破坏性演练`：故障注入、切换、恢复、数据损坏，只能在明确标识的可销毁隔离环境中执行。

    所有命令都要给出执行位置、权限身份、前置状态、风险等级、关键预期输出、失败后的停止条件和复位方式。绝不暴露真实密码，不引导把数据库或管理入口裸露到公网，不把实验命令包装成可直接复制到生产的“万能命令”。

    正式写作必须声明或读取版本契约，包括 PostgreSQL、Pigsty、操作系统、Patroni、PgBouncer、HAProxy、pgBackRest 和关键扩展版本。对易漂移的界面、参数、默认值和命令注明版本范围。无法核实的内容明确标为待验证，不得编造命令、配置键、输出、性能数字或产品能力。

    检索资料时优先级如下：

    1. PostgreSQL、Pigsty 以及相关组件的官方文档、官方仓库和原始发布说明；
    2. PostgreSQL 源码注释、正式论文、RFC、标准和上游设计资料；
    3. 权威书籍、会议演讲和有实验依据的高质量技术文章；
    4. 作者博客中与章节直接相关、且能被原生证据复核的文章。

    避免 SEO 聚合站、低质量转载和无法追溯来源的结论。引用资料要服务于论证，不追求数量；正文末尾给出经过筛选的参考资料与进一步阅读。

    ## 七、正文写作风格

    - 使用自然、准确、专业、流畅的简体中文，语气像经验丰富且愿意解释原理的工程师；
    - 成语章名只承担品牌和记忆作用，正文以功能标题和技术问题为主，不强行附会“三十六计”；
    - 首次出现的重要英文术语给出中文解释和英文原词；SQL、命令、参数、对象名使用代码格式；
    - 避免空泛排比、营销口号、AI 腔、过密括号、无意义总结以及“显而易见”“众所周知”等表达；
    - 示例保持命名一致，优先使用 `pg36_shop`；不要每节发明新的玩具表；
    - 代码块必须可读，长脚本说明关键片段和文件位置；输出只保留用于判断的部分；
    - 只有关系复杂时才使用 Mermaid 图、表格或时序图，并在图后解释读图方法；
    - 不在正文中出现“AI 生成”“占位”“以后再写”等元话语；
    - 以完整覆盖认知任务为准，不机械凑字数。通常每目需要 400–1200 个中文字符，复杂实验可更长；绝不能用重复解释填充篇幅。

    ## 八、页面与交付格式

    章首页 `_index.md` 应包含：本章定位、读者前置、本章学习成果、贯穿场景、章节路线、主要交付物、复习与迁移问题、与前后章的衔接。章节目录链接保持简洁，不显示能力分类标签。

    每个节页面应围绕既定的“目”逐项展开，并按内容需要组合以下元素，而不是套用僵硬模板：

    - 问题场景与学习目标；
    - 准确的概念和心智模型；
    - 原理、内部机制与边界；
    - SQL、命令、配置或代码示例；
    - PostgreSQL 原生证据；
    - Pigsty 中的操作、观察与职责映射；
    - 常见误区、失败注入和诊断线索；
    - 实验步骤、预期结果、验收与复位；
    - 小结、复习问题及下一节桥接。

    保留现有 front matter、规范 URL、编号和稳定锚点。将脚手架的一段话摘要扩写为正文，不要只在摘要后追加零散材料。完成初稿后可把 `book_status: scaffold` 更新为 `book_status: draft`，但没有经过技术审校时不得标记为 final。

    如果拥有工作区写权限，直接编辑对应 Markdown 文件，并在完成后报告修改文件、验证命令、未决事实和风险。如果只能输出文本，则按文件路径分块给出完整 Markdown，不要只给大纲。

    ## 九、全书 36 章地图

    #{book_map(chapters)}
  PROMPT
end

def target_context(chapter, chapters)
  number = chapter.fetch("number")
  previous = number > 1 ? chapters[number - 2] : nil
  following = number.zero? ? chapters.first : chapters[number]
  previous_text =
    if previous
      "#{previous.fetch('id')} #{previous.fetch('title')}：#{previous.fetch('goal')}"
    elsif number == 1
      "全书导读与可选第 0 章；读者应已具备版本契约所要求的实验环境。"
    else
      "无；这是可选的实验准备章。"
    end
  following_text = following ? "#{following.fetch('id')} #{following.fetch('title')}：#{following.fetch('goal')}" : "无；这是正式正文的收束章。"
  section_files = chapter.fetch("sections").map { |section| "`docs/#{chapter.fetch('slug')}/#{section.fetch('slug')}.md`" }.join("、")

  <<~PROMPT
    ## 十、本次唯一任务

    完整编写 **#{chapter.fetch('id')} #{chapter.fetch('title')}**，不是继续扩充大纲，也不是只写其中一个示例。

    - 所属位置：#{chapter.fetch('volume_title')}；#{chapter.fetch('part_title')}
    - 本章目标：#{chapter.fetch('goal')}
    - 章首页：`docs/#{chapter.fetch('slug')}/_index.md`
    - 节页面：#{section_files}
    - 前一章及其交付：#{previous_text}
    - 后一章及其需求：#{following_text}

    写作时先读取这些现有页面及必要前置章，保留 front matter、编号、链接和锚点。围绕本章目标建立一条主叙事，确保各节互相推进，而不是 #{chapter.fetch('sections').length} 篇彼此独立的博客拼盘。

    ## 十一、本章不可变内容合同

    #{detailed_outline(chapter)}

    ## 十二、执行步骤

    1. **范围审计**：逐目确认它在本章承担的认知或实践任务，识别与前后章的重叠，列出本章必须回答的问题和明确不展开的问题。
    2. **证据计划**：为每个关键结论选择原生 SQL、系统目录、日志、配置、指标、源码或官方资料；为 Pigsty 操作安排原生复核。
    3. **实验设计**：选择与本章目标相符的主实验，声明 L1/L2/L3、版本、数据规模、身份、风险、预期、验收和 reset；不要堆互不相关的小实验。
    4. **完整写作**：直接完成章首页和全部节页面，逐目扩写既定摘要。概念、推理、示例、证据、误区和实践应形成连贯闭环。
    5. **技术核验**：实际运行能安全运行的 SQL/命令或做静态校验；不能运行的部分说明验证方法和未决项，绝不伪造“已验证”。
    6. **教学审校**：检查认知负担、术语首次出现、示例连续性、前置依赖、练习反馈和跨节桥接。
    7. **安全审校**：检查风险等级、权限、停止条件、生产适用边界、回退和敏感信息。
    8. **编辑审校**：删除重复、空话、营销语和能力归属标签；统一术语、代码风格、链接和编号。
    9. **交付报告**：列出已完成文件、验证结果、引用基线、仍需人工确认的事实，以及本章向下一章交付了什么。

    ## 十三、本章验收门槛

    只有同时满足下列条件才算完成：

    - 章首页和每个节页面都有实质正文，所有既定“目”均已覆盖，没有 TODO、占位段落或只改标题；
    - 初学 PostgreSQL 的目标读者能沿着现象、模型、证据和实验理解内容，同时资深读者不会因过度简化而被误导；
    - 每条关键 PostgreSQL 结论都可由原生证据或权威资料复核；
    - Pigsty 内容既足够具体可执行，又明确其参考实现属性；
    - 示例、对象名、数据和工作负载与 `pg36_shop` 及前置章节保持一致；
    - 命令具备上下文、权限、风险、预期、失败判断和复位信息；
    - 实验具有确定起点、可观察过程、机器或人工验收条件和安全 reset；
    - 不把玩具实验的性能数字外推到生产，不隐去版本、硬件、缓存、并发和数据量；
    - 不重复显示“能力归属”或 `[PG]`、`[平台]`、`[Pigsty]` 导航标签；
    - 与前一章不重复，与后一章有清晰交付；读者完成本章后确实获得本章目标所描述的能力；
    - 内部链接、代码格式、Markdown 标题、稳定锚点和 Hugo 构建均通过检查；
    - 末尾参考资料经过筛选，来源可靠，且正文中的重要主张能够追溯。

    现在开始执行。不要先向我复述任务，不要只返回计划；在完成必要的范围与证据检查后，直接编写并验证本章。
  PROMPT
end

def master_prompt(chapters, chapter_zero_data)
  all_outlines = ([chapter_zero_data] + chapters).map do |chapter|
    [
      "### #{chapter.fetch('id')} #{chapter.fetch('title')}",
      "",
      "**目标**：#{chapter.fetch('goal')}",
      "",
      detailed_outline(chapter, section_level: 4, item_level: 5)
    ].join("\n")
  end.join("\n\n")
  <<~PROMPT
    # 《PostgreSQL 36 计》全书总提示词

    你是这本书的首席作者、技术编辑、实验设计者和质量负责人。你同时具备 PostgreSQL 内核与应用开发、数据库平台工程、DBA/SRE、Pigsty 生产实践和技术教育经验。你的最终任务是把既定脚手架写成一部可以出版、可以实验、可以长期维护的完整教程。

    #{global_context(chapters)}

    ## 十、全书详细内容合同

    以下章、节、目及其“既定写作范围”是已经达成共识的内容架构。它们不是头脑风暴素材，而是写作合同。摘要规定每一目必须回答的核心问题，正式写作应将其扩展为连贯正文，而不是原样重复：

    #{all_outlines}

    ## 十一、全书执行策略

    1. 先冻结版本契约、术语表、实验拓扑、`pg36_shop` 数据契约和通用写作规范；
    2. 建立章节依赖与交付物清单，确保后章能直接消费前章产物；
    3. 一次只完成一章的“研究—写作—实验—审校—验收”闭环，不用一次响应草率生成整本书；
    4. 优先用 ch08 校准方法型章节、ch20 校准架构型章节、ch32 校准恢复型章节的深度，再把质量标准推广到同类章节；
    5. 仍按读者认知顺序维护跨章一致性：ch01–ch06 奠基，ch07–ch12 应用交付，ch13–ch18 扩展边界，ch19–ch24 生产规划，ch25–ch30 运营演进，ch31–ch36 事故恢复与改进；
    6. 每完成一章，运行技术、教学、安全、编辑和链接五道质量门，并更新跨章事实表；
    7. 六篇完成后各做一次横向审校；上下卷完成后各做一次路径审校；全书完成后再做版本增量、术语、引用、实验复现和重复内容审校；
    8. 不因上下文长度而降低质量。如果一次无法完成一章，应按节连续交付直到该章闭环，而不是留下摘要或半成品。

    ## 十二、总完成标准

    全书只有在以下条件全部满足时才算完成：

    - 36 章和第 0 章所有页面均有经过技术核验的完整正文；
    - 读者能从 Linux/SQL 基础平滑进入 PostgreSQL，并完成应用开发与运维管理两条专家路径；
    - `pg36_shop`、L1/L2/L3、版本契约、术语、命令风格和证据格式全书一致；
    - PostgreSQL 原理、平台职责和 Pigsty 实现边界准确，不把产品偏好包装成普遍真理；
    - 所有 R1/R2 操作具有明确风险、停止条件、授权边界和复位路径；
    - 关键实验可以按文档复现，预期与验收条件明确，性能结论不越界；
    - 全书不存在空章节、占位摘要、重复能力标签、断链、失效锚点和未经说明的版本漂移；
    - 完成技术事实审校、实验复现审校、教学审校、安全审校、语言审校和最终 Hugo 构建；
    - 附录、任务索引、技术边界索引、事故索引和卷导读与正文同步。

    现在开始承担整本书的持续写作任务。先输出一份简洁的全书执行基线和章节依赖/交付物清单，然后立即进入第一个尚未完成的章节；不要把再次生成大纲当作完成。
  PROMPT
end

def chapter_prompt(chapter, chapters)
  <<~PROMPT
    # 《PostgreSQL 36 计》#{chapter.fetch('id')} 独立写作提示词

    你是一位兼具 PostgreSQL 技术深度、Pigsty 生产经验和教学设计能力的资深技术作者。下面是完整、独立、可直接执行的章节写作任务；无需依赖本提示词之外的聊天历史。

    #{global_context(chapters)}

    #{target_context(chapter, chapters)}
  PROMPT
end

def readme(chapters, chapter_zero_data)
  lines = [
    "# 《PostgreSQL 36 计》写作提示词系列",
    "",
    "本目录由 `bin/generate_book_prompts.rb` 从当前书稿骨架生成。每份章节提示词都是独立、自包含的，可单独交给一个具备文件访问、检索与执行能力的写作代理。",
    "",
    "## 使用方式",
    "",
    "1. 用 `master-prompt.md` 驱动整本书的长期写作与质量管理；",
    "2. 用 `ch00.md` 或 `ch01.md`–`ch36.md` 一次完成一章；",
    "3. 章节提示词已经包含全书目标、读者画像、架构、36 章地图、教学原则、安全与版本契约、目标章完整目录和每目的范围摘要；",
    "4. 总提示词完整收录第 0 章与 36 章的全部节、目和范围摘要，因此文件较大；上下文预算有限时优先使用对应的独立章节提示词；",
    "5. 若目录或摘要变化，运行 `ruby bin/generate_book_prompts.rb` 重新生成；",
    "6. 旧文件 `prompt/prompt.md` 是历史头脑风暴提示，未被覆盖。",
    "",
    "## 文件",
    "",
    "- [全书总提示词](master-prompt.md)",
    "- [第 0 章（可跳过）](ch00.md)"
  ]
  chapters.each do |chapter|
    lines << "- [#{chapter.fetch('id')} #{chapter.fetch('title')}](#{chapter.fetch('id')}.md)"
  end
  lines << ""
  lines << "共 1 份总提示词、1 份第 0 章提示词和 #{chapters.length} 份正式章节提示词。"
  lines << ""
  lines << "第 0 章当前包含 #{chapter_zero_data.fetch('sections').length} 个节；正式正文包含 #{chapters.sum { |chapter| chapter.fetch('sections').length }} 个节。"
  lines.join("\n") + "\n"
end

def validate_chapter_prompt(path, chapter, chapters)
  content = path.read(encoding: "UTF-8")
  [
    "## 一、全书使命",
    "## 二、全书架构与导航约束",
    "## 三、PostgreSQL 与 Pigsty 的叙述关系",
    "## 四、教学方法",
    "## 五、贯穿案例与实验拓扑",
    "## 六、安全、版本与事实纪律",
    "## 七、正文写作风格",
    "## 八、页面与交付格式",
    "## 九、全书 36 章地图",
    "## 十、本次唯一任务",
    "## 十一、本章不可变内容合同",
    "## 十二、执行步骤",
    "## 十三、本章验收门槛"
  ].each do |marker|
    raise "Prompt marker #{marker.inspect} missing from #{path}" unless content.include?(marker)
  end

  chapters.each do |mapped_chapter|
    map_fragment = "| #{mapped_chapter.fetch('id')} |"
    raise "Global chapter map is incomplete in #{path}: #{mapped_chapter.fetch('id')}" unless content.include?(map_fragment)
  end

  raise "Target chapter title missing from #{path}" unless content.include?("**#{chapter.fetch('id')} #{chapter.fetch('title')}**")
  raise "Target chapter goal missing from #{path}" unless content.include?(chapter.fetch("goal"))
  raise "Target chapter index path missing from #{path}" unless content.include?("`docs/#{chapter.fetch('slug')}/_index.md`")

  chapter.fetch("sections").each do |section|
    section_heading = "### #{section.fetch('number')} #{section.fetch('title')}"
    section_path = "`docs/#{chapter.fetch('slug')}/#{section.fetch('slug')}.md`"
    raise "Section heading missing from #{path}: #{section.fetch('number')}" unless content.include?(section_heading)
    raise "Section path missing from #{path}: #{section_path}" unless content.include?(section_path)

    section.fetch("items").each do |item|
      item_heading = "#### #{item.fetch('number')} #{item.fetch('title')}"
      raise "Item heading missing from #{path}: #{item.fetch('number')}" unless content.include?(item_heading)
      raise "Item scope missing from #{path}: #{item.fetch('number')}" unless content.include?(item.fetch("summary"))
    end
  end
end

def validate_master_prompt(path, chapters, chapter_zero_data)
  content = path.read(encoding: "UTF-8")
  [
    "## 一、全书使命",
    "## 九、全书 36 章地图",
    "## 十、全书详细内容合同",
    "## 十一、全书执行策略",
    "## 十二、总完成标准"
  ].each do |marker|
    raise "Master prompt marker #{marker.inspect} missing from #{path}" unless content.include?(marker)
  end

  ([chapter_zero_data] + chapters).each do |chapter|
    raise "Chapter contract missing from master prompt: #{chapter.fetch('id')}" unless content.include?("### #{chapter.fetch('id')} #{chapter.fetch('title')}")
    raise "Chapter goal missing from master prompt: #{chapter.fetch('id')}" unless content.include?(chapter.fetch("goal"))

    chapter.fetch("sections").each do |section|
      raise "Section missing from master prompt: #{section.fetch('number')}" unless content.include?("#### #{section.fetch('number')} #{section.fetch('title')}")

      section.fetch("items").each do |item|
        raise "Item missing from master prompt: #{item.fetch('number')}" unless content.include?("##### #{item.fetch('number')} #{item.fetch('title')}")
        raise "Item scope missing from master prompt: #{item.fetch('number')}" unless content.include?(item.fetch("summary"))
      end
    end
  end
end

def validate_readme(path, chapters)
  content = path.read(encoding: "UTF-8")
  expected_links = ["master-prompt.md", "ch00.md"] + chapters.map { |chapter| "#{chapter.fetch('id')}.md" }
  expected_links.each do |filename|
    raise "README link missing: #{filename}" unless content.include?("(#{filename})")
    raise "README target missing: #{filename}" unless OUTPUT_PATH.join(filename).file?
  end
end

raise "Missing #{CHAPTERS_PATH}" unless CHAPTERS_PATH.file?
raise "Missing #{BOOK_PATH}" unless BOOK_PATH.file?
raise "Missing #{DOCS_PATH}" unless DOCS_PATH.directory?

chapters = load_yaml(CHAPTERS_PATH)
book = load_yaml(BOOK_PATH)
raise "Expected #{EXPECTED_CHAPTERS} chapters" unless chapters.length == EXPECTED_CHAPTERS
raise "Book navigation is not flat" unless book.fetch("navigation") == "flat-chapters-with-volume-overviews"
raise "Volume hierarchy must remain disabled" unless book.fetch("volume_hierarchy") == false

section_count = chapters.sum { |chapter| chapter.fetch("sections").length }
item_count = chapters.sum { |chapter| chapter.fetch("sections").sum { |section| section.fetch("items").length } }
raise "Expected #{EXPECTED_SECTIONS} sections, got #{section_count}" unless section_count == EXPECTED_SECTIONS
raise "Expected #{EXPECTED_ITEMS} items, got #{item_count}" unless item_count == EXPECTED_ITEMS

enrich_chapters(chapters)
chapter_zero_data = chapter_zero

if OUTPUT_PATH.exist? && !SENTINEL.file?
  raise "Refusing to overwrite #{OUTPUT_PATH}: generator sentinel is missing"
end

FileUtils.mkdir_p(OUTPUT_PATH)
SENTINEL.write("generated-by=bin/generate_book_prompts.rb\n", mode: "w", encoding: "UTF-8")
OUTPUT_PATH.join("master-prompt.md").write(master_prompt(chapters, chapter_zero_data), mode: "w", encoding: "UTF-8")
OUTPUT_PATH.join("ch00.md").write(chapter_prompt(chapter_zero_data, chapters), mode: "w", encoding: "UTF-8")
chapters.each do |chapter|
  OUTPUT_PATH.join("#{chapter.fetch('id')}.md").write(chapter_prompt(chapter, chapters), mode: "w", encoding: "UTF-8")
end
OUTPUT_PATH.join("README.md").write(readme(chapters, chapter_zero_data), mode: "w", encoding: "UTF-8")

prompt_files = OUTPUT_PATH.glob("ch[0-9][0-9].md")
raise "Expected 37 chapter prompts, got #{prompt_files.length}" unless prompt_files.length == 37

validate_master_prompt(OUTPUT_PATH.join("master-prompt.md"), chapters, chapter_zero_data)
validate_chapter_prompt(OUTPUT_PATH.join("ch00.md"), chapter_zero_data, chapters)
chapters.each do |chapter|
  validate_chapter_prompt(OUTPUT_PATH.join("#{chapter.fetch('id')}.md"), chapter, chapters)
end
validate_readme(OUTPUT_PATH.join("README.md"), chapters)

puts "Generated 1 master prompt and #{prompt_files.length} standalone chapter prompts."
puts "Output: #{OUTPUT_PATH}"
