#!/usr/bin/env ruby
# frozen_string_literal: true

require "fileutils"
require "pathname"
require "yaml"

ROOT = Pathname.new(__dir__).parent.expand_path
OUTLINE_PATH = ROOT.join("plan/book-outline-final.md")
DOCS_DIR = ROOT.join("docs")
DATA_DIR = ROOT.join("data")
SCAFFOLD_SENTINEL = DOCS_DIR.join(".scaffold-generated")

CHAPTER_SLUGS = %w[
  postgresql-pigsty-map
  psql-workflow
  logical-data-model
  data-types-constraints
  query-transaction-locks
  development-standards
  query-plans-statistics
  slow-query-diagnosis
  index-design
  concurrency-isolation
  schema-change-release
  database-to-service
  functions-triggers-procedures
  extensions-ecosystem
  search
  spatiotemporal
  analytics-distributed
  data-platform-boundaries
  deployment-baseline
  high-availability
  backup-recovery
  connection-pooling-routing
  authentication-authorization-security
  slo-sop-governance
  observability
  capacity-benchmarking
  configuration-tuning
  vacuum-freeze-bloat
  logical-replication-migration
  version-upgrade
  incident-response
  pitr
  failover-rebuild
  overload-resource-incidents
  data-rescue-forensics
  postmortem-platform-improvement
].freeze

VOLUMES = [
  {
    "id" => "volume-1",
    "slug" => "upper-volume",
    "number" => 1,
    "title" => "上卷：应用开发",
    "subtitle" => "从 PostgreSQL 工程认知到应用交付与能力扩展",
    "summary" => "上卷面向应用开发者与数据库工程实践者，沿着“认识系统—可靠建模—正确查询—性能与并发—安全交付—能力扩展”的路径，建立从 PostgreSQL 原理到 Pigsty 实验闭环的完整开发能力。",
    "weight" => 100,
    "chapter_range" => (1..18),
    "aliases" => ["/volume-1/", "/dev/"]
  },
  {
    "id" => "volume-2",
    "slug" => "lower-volume",
    "number" => 2,
    "title" => "下卷：运维管理",
    "subtitle" => "从生产服务规划到日常运营、事故恢复与改进",
    "summary" => "下卷面向 DBA、平台工程师与生产负责人，沿着“规划交付—高可用与备份—安全接入—可观测运营—迁移升级—事故恢复与复盘”的路径，把 PostgreSQL 知识转化为可持续运行的数据库服务能力。",
    "weight" => 285,
    "chapter_range" => (19..36),
    "aliases" => ["/volume-2/", "/ops/", "/dba/"]
  }
].freeze

PARTS = [
  {
    "id" => "part-1",
    "number" => 1,
    "title" => "第一篇：筑基——建立 PostgreSQL 工程认知",
    "short_title" => "筑基",
    "chapter_range" => (1..6)
  },
  {
    "id" => "part-2",
    "number" => 2,
    "title" => "第二篇：应用——从 SQL 正确走向稳定交付",
    "short_title" => "应用",
    "chapter_range" => (7..12)
  },
  {
    "id" => "part-3",
    "number" => 3,
    "title" => "第三篇：扩展——扩大 PostgreSQL 的能力边界",
    "short_title" => "扩展",
    "chapter_range" => (13..18)
  },
  {
    "id" => "part-4",
    "number" => 4,
    "title" => "第四篇：规划——建设可交付的 PostgreSQL 服务",
    "short_title" => "规划",
    "chapter_range" => (19..24)
  },
  {
    "id" => "part-5",
    "number" => 5,
    "title" => "第五篇：运营——用证据驱动日常维护与演进",
    "short_title" => "运营",
    "chapter_range" => (25..30)
  },
  {
    "id" => "part-6",
    "number" => 6,
    "title" => "第六篇：出山——按响应目标演练恢复与改进",
    "short_title" => "出山",
    "chapter_range" => (31..36)
  }
].freeze

CAPABILITY_NAMES = {
  "PG" => "PostgreSQL 原生能力",
  "平台" => "通用平台职责",
  "Pigsty" => "Pigsty 参考实现"
}.freeze

def volume_for(number)
  VOLUMES.find { |volume| volume["chapter_range"].cover?(number) }
end

def part_for(number)
  PARTS.find { |part| part["chapter_range"].cover?(number) }
end

def extract_idiom_and_functional_title(title, number)
  if number >= 31 && title.include?("——")
    functional, idiom = title.split("——", 2)
    [idiom.strip, functional.strip]
  elsif title.include?("：")
    idiom, functional = title.split("：", 2)
    [idiom.strip, functional.strip]
  else
    ["", title.strip]
  end
end

def parse_chapters(text)
  chapters = []
  chapter = nil
  section = nil

  text.each_line do |line|
    if (match = line.match(/^## ch(\d{2}) (.+)$/))
      number = match[1].to_i
      idiom, functional_title = extract_idiom_and_functional_title(match[2].strip, number)
      chapter = {
        "id" => format("ch%02d", number),
        "number" => number,
        "title" => match[2].strip,
        "idiom" => idiom,
        "functional_title" => functional_title,
        "slug" => CHAPTER_SLUGS.fetch(number - 1),
        "goal" => "",
        "sections" => []
      }
      volume = volume_for(number)
      part = part_for(number)
      chapter["volume"] = volume["id"]
      chapter["volume_title"] = volume["title"]
      chapter["part"] = part["id"]
      chapter["part_title"] = part["title"]
      chapter["aliases"] = [
        format("/ch%02d/", number),
        "/#{volume['id']}/#{chapter['slug']}/"
      ]
      chapters << chapter
      section = nil
    elsif chapter && (match = line.match(/^\*\*本章目标\*\*：(.+)$/))
      chapter["goal"] = match[1].strip
    elsif chapter && (match = line.match(/^### \[(PG|平台|Pigsty)\] (\d+\.\d+) (.+)$/))
      section_number = match[2]
      section_index = section_number.split(".").last.to_i
      section = {
        "id" => "#{chapter['id']}-s#{format('%02d', section_index)}",
        "number" => section_number,
        "index" => section_index,
        "slug" => format("%02d", section_index),
        "capability" => match[1],
        "title" => match[3].strip,
        "items" => []
      }
      chapter["sections"] << section
    elsif section && (match = line.match(/^#### (\d+\.\d+\.\d+) (.+)$/))
      item_number = match[1]
      section["items"] << {
        "id" => "item-#{item_number.tr('.', '-')}",
        "number" => item_number,
        "title" => match[2].strip
      }
    end
  end

  chapters
end

def parse_chapter_zero(text)
  block = text[/^# 第 0 章（可跳过）：(.+?)$\n(.*?)^---$/m, 0]
  raise "Cannot find chapter zero in outline" unless block

  title_match = block.match(/^# 第 0 章（可跳过）：(.+)$/)
  chapter = {
    "id" => "ch00",
    "number" => 0,
    "title" => title_match[1].strip,
    "goal" => "为尚未拥有实验环境的读者准备 Pigsty L1 沙箱，并完成首次 PostgreSQL 连通；已有符合版本契约的环境可以整章跳过。",
    "slug" => "ch00",
    "aliases" => ["/ch0/", "/ch00/"],
    "sections" => []
  }
  section = nil

  block.each_line do |line|
    if (match = line.match(/^## (0\.\d+) (.+)$/))
      section_index = match[1].split(".").last.to_i
      section = {
        "id" => "ch00-s#{format('%02d', section_index)}",
        "number" => match[1],
        "index" => section_index,
        "slug" => format("%02d", section_index),
        "capability" => "准备",
        "title" => match[2].strip,
        "items" => []
      }
      chapter["sections"] << section
    elsif section && (match = line.match(/^### (0\.\d+\.\d+) (.+)$/))
      section["items"] << {
        "id" => "item-#{match[1].tr('.', '-')}",
        "number" => match[1],
        "title" => match[2].strip
      }
    end
  end

  chapter
end

def extract_block(text, start_heading, end_heading)
  match = text.match(/^#{Regexp.escape(start_heading)}$\n(.*?)^#{Regexp.escape(end_heading)}$/m)
  raise "Cannot extract block #{start_heading}" unless match

  match[1].sub(/\n---\s*\z/, "").strip
end

def yaml_front_matter(metadata)
  YAML.dump(metadata) + "---\n\n"
end

def write_document(path, metadata, body)
  FileUtils.mkdir_p(path.dirname)
  path.write(yaml_front_matter(metadata) + body.rstrip + "\n", mode: "w", encoding: "UTF-8")
end

def chapter_url(chapter)
  "/#{chapter['slug']}/"
end

def volume_url(volume)
  "/#{volume['slug']}/"
end

def section_url(chapter, section)
  "#{chapter_url(chapter)}#{section['slug']}/"
end

def strip_markdown(text)
  text.gsub(/`([^`]+)`/, '\1').gsub(/\*\*([^*]+)\*\*/, '\1')
end

def summary_focus(title)
  plain = strip_markdown(title)

  if plain.match?(/^(用|从|把|建立|生成|输出|产出|完成|执行|保存|比较|注入|验证|运行|创建|核对|选择|识别|记录|配置|安装|观察|测量|恢复|重建|汇总|找出|更新|修正|将|设计|证明|冻结|暂停|区分)/)
    "把这一动作拆成可执行内容，交代输入、操作顺序、预期结果和验收证据"
  elsif plain.match?(/(风险|边界|代价|陷阱|失败|误判|不等于|不是|不能|避免|防止|何时|条件|限制|不可|不要|绝不)/)
    "解释相关结论成立的条件、常见失败方式及其生产风险，给出可以停止或转向的判断线"
  elsif plain.match?(/[与、]/)
    "对照其中涉及的概念或组件，说明它们各自的职责、组合方式和容易混淆的分界"
  elsif plain.match?(/(为什么|如何|什么|何种)/)
    "回答标题提出的问题，先建立可验证的解释，再讨论适用范围与反例"
  else
    "解释它的核心语义、它与本节主问题的关系，以及读者需要形成的工程判断"
  end
end

def evidence_sentence(capability)
  case capability
  when "PG"
    "内容将优先使用 PostgreSQL 原生 SQL、系统目录、日志、执行计划或可重复实验作为证据"
  when "平台"
    "内容将从服务目标、职责边界、运行证据和安全动作四个角度组织，并区分通用职责与具体实现"
  when "Pigsty"
    "内容将先说明平台应提供的通用能力，再给出 Pigsty 的具体映射，并回到 SQL、配置或原生组件复核"
  else
    "内容将给出环境准备步骤、成功检查和失败后的安全复位方式"
  end
end

def item_summary(item, section, chapter, ordinal)
  leads = [
    "本目将围绕",
    "这一目准备围绕",
    "这里将围绕",
    "本目计划围绕"
  ]
  endings = [
    "并为本节后续实验提供判断依据。",
    "最终形成可供验证、评审或决策使用的依据。",
    "同时明确它与相邻概念及后续章节的边界。",
    "并指出正文必须保留的反例、风险提示与验收点。"
  ]
  lead = leads[ordinal % leads.length]
  ending = endings[(ordinal / leads.length) % endings.length]
  section_title = strip_markdown(section["title"])

  "#{lead}“#{strip_markdown(item['title'])}”展开，#{summary_focus(item['title'])}。#{evidence_sentence(section['capability'])}，使它在“#{section_title}”这一节中承担清晰的认知或实践任务，#{ending}"
end

def section_intro(section, chapter)
  "本节聚焦“#{strip_markdown(section['title'])}”，在第 #{chapter['number']} 章的学习路径中承担明确的认知或实践任务。页面先用各目的摘要固定写作范围，后续正文将沿着概念、证据、实践与风险边界逐步展开。"
end

def chapter_metadata(chapter)
  {
    "title" => "第 #{chapter['number']} 章 #{chapter['title']}",
    "linkTitle" => format("%02d %s", chapter["number"], chapter["title"]),
    "weight" => 100 + chapter["number"] * 10,
    "aliases" => chapter["aliases"],
    "type" => "docs",
    "math" => true,
    "breadcrumbs" => true,
    "comments" => false,
    "book_kind" => "chapter",
    "book_id" => chapter["id"],
    "book_number" => chapter["number"],
    "book_part" => chapter["part"],
    "book_status" => "scaffold"
  }
end

def section_metadata(chapter, section)
  metadata = {
    "title" => "#{section['number']} #{section['title']}",
    "linkTitle" => "#{section['number']} #{section['title']}",
    "weight" => section["index"] * 10,
    "type" => "docs",
    "math" => true,
    "breadcrumbs" => true,
    "comments" => false,
    "book_kind" => "section",
    "book_chapter" => chapter["id"],
    "book_number" => section["number"],
    "book_capability" => section["capability"],
    "book_status" => "scaffold"
  }
  if chapter["volume"]
    metadata["aliases"] = [
      "/#{chapter['volume']}/#{chapter['slug']}/#{section['slug']}/"
    ]
  end
  metadata
end

def chapter_index_body(chapter)
  volume = volume_for(chapter["number"])
  lines = []
  lines << "> **骨架状态**：本章已经建立“章 → 节页面 → 目摘要”的完整索引；当前摘要用于固定写作范围，后续再逐目扩写、验证和审校。"
  lines << ""
  lines << "## 本章目标"
  lines << ""
  lines << chapter["goal"]
  lines << ""
  lines << "## 所属位置"
  lines << ""
  lines << "- 卷别：[#{chapter['volume_title']}](#{volume_url(volume)})（独立导读页，不构成章节父目录）"
  lines << "- 教学分组：#{chapter['part_title']}"
  lines << "- 兼容入口：#{chapter['aliases'].map { |entry| "`#{entry}`" }.join('、')}"
  lines << ""
  lines << "## 本章目录"
  lines << ""

  chapter["sections"].each do |section|
    lines << "### [#{section['number']} #{section['title']}](#{section['slug']}/)"
    lines << ""
    section["items"].each do |item|
      lines << "- [#{item['number']} #{item['title']}](#{section['slug']}/##{item['id']})"
    end
    lines << ""
  end

  lines << "## 写作与验收提示"
  lines << ""
  lines << "- 本章各节是独立页面，目的标题使用稳定锚点；"
  lines << "- PostgreSQL 结论优先回到原生证据，Pigsty 内容标明参考实现边界；"
  lines << "- 实验正文补写时必须同时补齐验证、风险等级与复位路径。"
  lines.join("\n")
end

def section_body(chapter, section, global_ordinal)
  lines = []
  lines << "> **本节定位**：#{section_intro(section, chapter)}"
  lines << ""

  section["items"].each_with_index do |item, index|
    lines << "## #{item['number']} #{item['title']} {##{item['id']}}"
    lines << ""
    lines << item_summary(item, section, chapter, global_ordinal + index)
    lines << ""
  end

  lines << "---"
  lines << ""
  lines << "[返回本章目录](../) · [查看全书目录](/toc/) · [查看索引中心](/indexes/)"
  lines.join("\n")
end

def volume_page_body(volume, chapters)
  volume_chapters = chapters.select { |chapter| volume["chapter_range"].cover?(chapter["number"]) }
  volume_parts = PARTS.select { |part| volume["chapter_range"].cover?(part["chapter_range"].begin) }
  lines = []
  lines << "> **本卷导读**：#{volume['summary']}"
  lines << ""
  lines << "## 本卷定位"
  lines << ""
  lines << volume["subtitle"]
  lines << ""
  lines << "本页是位于顶层导航中的导读与索引页，不是章节父目录。下面各章仍与本页并列，使用独立的顶层 URL；读者既可以按本卷路径顺序学习，也可以直接进入任意章节。"
  lines << ""
  lines << "## 本卷索引"
  lines << ""

  volume_parts.each do |part|
    lines << "### #{part['title']}"
    lines << ""
    volume_chapters.select { |chapter| part["chapter_range"].cover?(chapter["number"]) }.each do |chapter|
      lines << "#### [ch#{format('%02d', chapter['number'])} #{chapter['title']}](#{chapter_url(chapter)})"
      lines << ""
      lines << chapter["goal"]
      lines << ""
      chapter["sections"].each do |section|
        lines << "- [#{section['number']} #{section['title']}](#{section_url(chapter, section)})"
      end
      lines << ""
    end
  end

  lines << "## 前后衔接"
  lines << ""
  if volume["number"] == 1
    lines << "- 开始前：[全书导读](/guide/) · [第 0 章（可跳过）](/ch00/)"
    lines << "- 完成本卷后：[下卷：运维管理](#{volume_url(VOLUMES.last)})"
  else
    lines << "- 前置路径：[上卷：应用开发](#{volume_url(VOLUMES.first)})"
    lines << "- 完成本卷后：[附录与速查](/appendices/) · [索引中心](/indexes/)"
  end
  lines.join("\n")
end

def root_index_body(chapters)
  lines = []
  lines << "> 从 SQL 到生产：PostgreSQL 与 Pigsty 实战"
  lines << ""
  lines << "本书默认读者已经掌握 Linux 与通用 SQL，以 PostgreSQL 为核心知识对象，以 Pigsty 为统一实验载体、观察窗口和生产参考实现。"
  lines << ""
  lines << "## 开始阅读"
  lines << ""
  lines << "- [全书导读：读者假设、安全、版本与实验契约](/guide/)"
  lines << "- [第 0 章：准备实验环境（可跳过）](/ch00/)"
  lines << "- [完整目录：章、节、目](/toc/)"
  lines << "- [上卷导读与索引：应用开发](#{volume_url(VOLUMES.first)})"
  lines << "- [下卷导读与索引：运维管理](#{volume_url(VOLUMES.last)})"
  lines << "- [索引中心：角色、任务、能力、事故与分区](/indexes/)"
  lines << "- [序言：定位、利益披露与命名原则](/preface/)"
  lines << ""

  lines << "## 36 章正文"
  lines << ""
  lines << "36 个章节直接作为顶层导航项；“上卷／下卷”各自拥有一个并列的导读索引页，但不形成章节父目录或中间 URL 层级。"
  lines << ""

  PARTS.each do |part|
    lines << "### #{part['title']}"
    lines << ""
    chapters.select { |chapter| part["chapter_range"].cover?(chapter["number"]) }.each do |chapter|
      lines << "- [ch#{format('%02d', chapter['number'])} #{chapter['title']}](#{chapter_url(chapter)})"
    end
    lines << ""
  end

  lines << "## 脚手架说明"
  lines << ""
  lines << "当前站点已经建立全部章、节与目的页面骨架。每个“节”是独立页面，每个“目”都有稳定锚点和一段写作摘要；页面状态统一标记为 `scaffold`，不把摘要冒充已经完成的正文。"
  lines.join("\n")
end

def full_toc_body(chapter_zero, chapters)
  lines = []
  lines << "> 本页列出全书的章、节、目。36 个正文章直接位于顶层；节标题链接到独立页面，目标题链接到页面内的稳定锚点。"
  lines << ""
  lines << "## 前置内容"
  lines << ""
  lines << "- [全书导读](/guide/)"
  lines << "- [第 0 章 #{chapter_zero['title']}](/ch00/)"
  chapter_zero["sections"].each do |section|
    lines << "  - [#{section['number']} #{section['title']}](/ch00/#{section['slug']}/)"
    section["items"].each do |item|
      lines << "    - [#{item['number']} #{item['title']}](/ch00/#{section['slug']}/##{item['id']})"
    end
  end
  lines << ""

  lines << "## 36 章正文"
  lines << ""

  VOLUMES.each do |volume|
    lines << "### [#{volume['title']}](#{volume_url(volume)})"
    lines << ""
    lines << volume["subtitle"]
    lines << ""
    PARTS.select { |part| volume["chapter_range"].cover?(part["chapter_range"].begin) }.each do |part|
      lines << "#### #{part['title']}"
      lines << ""
      chapters.select { |chapter| part["chapter_range"].cover?(chapter["number"]) }.each do |chapter|
        lines << "##### [ch#{format('%02d', chapter['number'])} #{chapter['title']}](#{chapter_url(chapter)})"
        lines << ""
        chapter["sections"].each do |section|
          lines << "- [#{section['number']} #{section['title']}](#{section_url(chapter, section)})"
          section["items"].each do |item|
            lines << "  - [#{item['number']} #{item['title']}](#{section_url(chapter, section)}##{item['id']})"
          end
        end
        lines << ""
      end
    end
  end

  lines << "## 附录"
  lines << ""
  ("A".."F").each do |letter|
    lines << "- [附录 #{letter}](/appendices/#{letter.downcase}/)"
  end
  lines.join("\n")
end

def chapter_zero_index_body(chapter)
  lines = []
  lines << "> **可跳过说明**：#{chapter['goal']}"
  lines << ""
  lines << "## 本章目录"
  lines << ""
  chapter["sections"].each do |section|
    lines << "### [#{section['number']} #{section['title']}](#{section['slug']}/)"
    lines << ""
    section["items"].each do |item|
      lines << "- [#{item['number']} #{item['title']}](#{section['slug']}/##{item['id']})"
    end
    lines << ""
  end
  lines.join("\n")
end

def capabilities_index_body(chapters)
  lines = []
  lines << "> 按二级小节的主要责任归属索引。混合小节只标主责，具体正文仍需说明边界。"
  lines << ""
  CAPABILITY_NAMES.each do |capability, label|
    lines << "## [#{capability}] #{label}"
    lines << ""
    chapters.each do |chapter|
      chapter["sections"].select { |section| section["capability"] == capability }.each do |section|
        lines << "- [#{section['number']} #{section['title']}](#{section_url(chapter, section)}) — ch#{format('%02d', chapter['number'])} #{chapter['functional_title']}"
      end
    end
    lines << ""
  end
  lines.join("\n")
end

def chapter_ref(chapters, number)
  chapter = chapters.fetch(number - 1)
  "[ch#{format('%02d', number)}《#{chapter['functional_title']}》](#{chapter_url(chapter)})"
end

def roles_index_body(chapters)
  [
    "> 角色路线用于系统阅读；跨章跳读前仍应检查前置依赖。",
    "",
    "## 应用开发者",
    "",
    "- #{chapter_ref(chapters, 1)} 至 #{chapter_ref(chapters, 18)}",
    "- 生产接入补读：#{chapter_ref(chapters, 22)}、#{chapter_ref(chapters, 23)}、#{chapter_ref(chapters, 25)}",
    "",
    "## DBA / SRE",
    "",
    "- 基础：#{chapter_ref(chapters, 1)}、#{chapter_ref(chapters, 2)}、#{chapter_ref(chapters, 5)} 至 #{chapter_ref(chapters, 10)}",
    "- 主线：#{chapter_ref(chapters, 19)} 至 #{chapter_ref(chapters, 36)}",
    "",
    "## 架构师与平台工程师",
    "",
    "- #{chapter_ref(chapters, 1)}、#{chapter_ref(chapters, 6)}、#{chapter_ref(chapters, 12)}、#{chapter_ref(chapters, 14)}",
    "- #{chapter_ref(chapters, 17)} 至 #{chapter_ref(chapters, 24)}，最后阅读 #{chapter_ref(chapters, 36)}",
    "",
    "## 事故处置",
    "",
    "- 先读 #{chapter_ref(chapters, 31)}，再按[事故症状索引](/indexes/incidents/)进入 ch32–ch35。",
    "- 不建议脱离备份、高可用和维护前置知识直接照抄事故命令。"
  ].join("\n")
end

def tasks_index_body(chapters)
  rows = [
    ["设计可靠模式", "3,4", "1,2"],
    ["查慢 SQL / 设计索引", "7,8,9", "5"],
    ["处理并发错误", "10", "5"],
    ["安全改表与发布", "11,12", "6,7,8,9,10"],
    ["选择扩展", "14,15,16,17,18", "7,8,9,10,11,12"],
    ["建设高可用与备份", "19,20,21,22", "1,5"],
    ["建立安全与治理", "23,24,25", "19,20,21,22"],
    ["压测、调优与维护", "26,27,28,29,30", "7,8,9,10,11,25"],
    ["误操作恢复", "31,32", "21"],
    ["主库或 DCS 故障", "31,33", "20"],
    ["连接风暴与资源耗尽", "31,34", "22,25,26,27,28"],
    ["数据损坏与抢救", "31,35", "21,28,30"]
  ]
  lines = [
    "> 按实际任务查找入口。章节链接始终同时显示编号与功能标题，避免重排后语义丢失。",
    "",
    "| 任务 | 首选章节 | 必要前置 |",
    "|---|---|---|"
  ]
  rows.each do |task, targets, prerequisites|
    target_links = targets.split(",").map { |n| chapter_ref(chapters, n.to_i) }.join("、")
    prereq_links = prerequisites.split(",").map { |n| chapter_ref(chapters, n.to_i) }.join("、")
    lines << "| #{task} | #{target_links} | #{prereq_links} |"
  end
  lines.join("\n")
end

def incidents_index_body(chapters)
  [
    "> 先按症状选择“首个安全动作”，再进入正式章节。症状相似不代表修复动作相同。",
    "",
    "| 症状或场景 | 首个安全动作 | 目标章节 | 明确禁止 |",
    "|---|---|---|---|",
    "| 误删、误更新、错误 DDL | 停止继续写入并确定影响时间窗 | #{chapter_ref(chapters, 32)} | 不覆盖仍可取证的原集群 |",
    "| 主节点、复制或 DCS 异常 | 保护旧主并核对角色、时间线与 DCS 事实 | #{chapter_ref(chapters, 33)} | 不在未 fencing 时提升第二个主库 |",
    "| 连接、延迟、CPU、内存、I/O 表象 | 先判流量型还是保留型 | #{chapter_ref(chapters, 34)} | 判型前不做破坏性清理 |",
    "| XID 回卷风险 | 检查 `backend_xmin`、复制槽 `xmin`、`pg_prepared_xacts` | #{chapter_ref(chapters, 28)}、#{chapter_ref(chapters, 34)} | 不用一般摘流代替解除保留 |",
    "| WAL 撑满磁盘 | 检查归档失败、复制槽和未完成备份 | #{chapter_ref(chapters, 21)}、#{chapter_ref(chapters, 34)}、#{chapter_ref(chapters, 35)} | **绝不手工删除 `pg_wal`** |",
    "| checksum、索引、collation 或逻辑不一致 | 停写、克隆并保存原始证据 | #{chapter_ref(chapters, 35)} | 不在唯一副本上反复试错 |"
  ].join("\n")
end

def partition_index_body(chapters)
  entries = [
    [4, "4.6", "分区决策门：分区键、唯一约束与引用限制"],
    [7, "7.4", "规划时/执行时裁剪与父表统计"],
    [11, "11.4", "在线分区化与版本相关锁行为"],
    [16, "16.2", "时间分区在时序场景中的应用"],
    [28, "28.5", "按分区维护、冻结与生命周期"]
  ]
  lines = [
    "> 分区不是一章讲完的孤立技巧，而是跨建模、计划、发布、场景与维护的五触点能力。",
    ""
  ]
  entries.each_with_index do |(chapter_number, section_number, description), index|
    chapter = chapters.fetch(chapter_number - 1)
    section = chapter["sections"].find { |candidate| candidate["number"] == section_number }
    lines << "## #{index + 1}. #{description}"
    lines << ""
    lines << "- 入口：[#{section['number']} #{section['title']}](#{section_url(chapter, section)})"
    lines << "- 所属章节：#{chapter_ref(chapters, chapter_number)}"
    lines << ""
  end
  lines.join("\n")
end

def parse_appendices(text)
  block = text[/^# 附录与速查（不计入 36 章）$\n(.*?)^---$\n\n# 内容生产与发布顺序/m, 1]
  raise "Cannot find appendix block" unless block

  appendices = []
  appendix = nil
  block.each_line do |line|
    if (match = line.match(/^## 附录 ([A-F])：(.+)$/))
      appendix = {
        "letter" => match[1],
        "title" => match[2].strip,
        "items" => []
      }
      appendices << appendix
    elsif appendix && (match = line.match(/^- (.+?)[；。]?$/))
      appendix["items"] << match[1].strip
    end
  end
  appendices
end

def appendix_summary(title, appendix_title, index)
  "本目将围绕“#{strip_markdown(title)}”建立附录级速查内容，重点提供可直接定位的定义、适用范围、版本或风险提示。它服务于“#{appendix_title}”的查阅场景，不替代对应章节中的原理、实验与决策过程。"
end

def validate_model(chapter_zero, chapters)
  expected_numbers = (1..36).to_a
  actual_numbers = chapters.map { |chapter| chapter["number"] }
  raise "Chapter sequence mismatch: #{actual_numbers.inspect}" unless actual_numbers == expected_numbers
  raise "Chapter slug count mismatch" unless CHAPTER_SLUGS.length == 36
  raise "Chapter zero must have 3 sections" unless chapter_zero["sections"].length == 3

  chapters.each do |chapter|
    unless (5..8).cover?(chapter["sections"].length)
      raise "#{chapter['id']} has #{chapter['sections'].length} sections"
    end
    raise "#{chapter['id']} has no goal" if chapter["goal"].empty?
    chapter["sections"].each do |section|
      unless (2..4).cover?(section["items"].length)
        raise "#{section['id']} has #{section['items'].length} items"
      end
    end
  end
end

def generated_data_file?(path)
  path.file? && path.read(encoding: "UTF-8").start_with?("# Generated from plan/book-outline-final.md")
end

def write_data_files(chapters, refresh: false)
  FileUtils.mkdir_p(DATA_DIR)
  chapters_path = DATA_DIR.join("chapters.yaml")
  book_path = DATA_DIR.join("book.yaml")
  if chapters_path.exist? && (!refresh || !generated_data_file?(chapters_path))
    raise "Refusing to overwrite non-generated #{chapters_path}"
  end
  if book_path.exist? && (!refresh || !generated_data_file?(book_path))
    raise "Refusing to overwrite non-generated #{book_path}"
  end

  chapters_path.write(
    "# Generated from plan/book-outline-final.md by bin/scaffold_book.rb.\n" +
      YAML.dump(chapters),
    mode: "w",
    encoding: "UTF-8"
  )
  book_path.write(
    "# Generated from plan/book-outline-final.md by bin/scaffold_book.rb.\n" +
      YAML.dump(
        {
          "title" => "PostgreSQL 36 计",
          "subtitle" => "从 SQL 到生产：PostgreSQL 与 Pigsty 实战",
          "status" => "scaffold",
          "source_outline" => "plan/book-outline-final.md",
          "navigation" => "flat-chapters-with-volume-overviews",
          "volume_hierarchy" => false,
          "volume_overview_pages" => true,
          "volumes" => VOLUMES.map { |volume| volume.reject { |key, _| key == "chapter_range" } },
          "parts" => PARTS.map { |part| part.reject { |key, _| key == "chapter_range" } }
        }
      ),
    mode: "w",
    encoding: "UTF-8"
  )
end

def write_scaffold(text, chapter_zero, chapters)
  write_document(
    DOCS_DIR.join("_index.md"),
    {
      "title" => "PostgreSQL 36 计",
      "linkTitle" => "首页",
      "cascade" => { "type" => "docs" },
      "breadcrumbs" => false,
      "comments" => false
    },
    root_index_body(chapters)
  )

  guide_body = text[/^# 全书导读（不可跳过，不计入 36 章）$\n(.*?)^---$/m, 1]
  raise "Cannot extract guide" unless guide_body
  write_document(
    DOCS_DIR.join("guide/_index.md"),
    {
      "title" => "全书导读",
      "linkTitle" => "导读",
      "weight" => 1,
      "type" => "docs",
      "breadcrumbs" => true,
      "comments" => false,
      "book_kind" => "guide"
    },
    guide_body.strip
  )

  preface_body = <<~MARKDOWN
    > 从 SQL 到生产：PostgreSQL 与 Pigsty 实战

    ## 为什么写这本书

    本书面向已经掌握 Linux 与通用 SQL、希望系统完成 PostgreSQL 应用开发和生产落地的读者。正文从对象与模型开始，经过查询、并发、扩展、部署、运营和恢复，最终把数据库知识变成可验证的工程能力。

    ## PostgreSQL 与 Pigsty

    PostgreSQL 是全书的核心知识对象；Pigsty 既是统一实验载体和观察窗口，也是把 PostgreSQL、HA、备份、接入与监控组合成生产服务的一种参考实现。书中会明确标注 PostgreSQL 原生能力、通用平台职责与 Pigsty 特有实现，不把参考实现冒充唯一架构。

    ## 作者关系与利益披露

    作者是 Pigsty 的作者与维护者，因此对其设计、能力与使用方式拥有直接经验，也天然存在偏好。全书要求 Pigsty 结论尽量回到 PostgreSQL 原生 SQL、配置或组件证据验证，并在可能造成迁移误解的位置说明跨平台职责映射。

    ## 关于“36 计”

    “36 计”表示 36 个递进的实战单元，是目录与教学节奏的品牌表达，不把章节强行附会为古代计策。事故篇优先使用功能标题检索，成语仅作为副标题。

    ## 当前状态

    当前版本已经完成“章、节、目”脚手架：36 个正文章直接作为顶层导航项；“上卷／下卷”各有一个并列的导读索引页，但不构成章节父目录。每个节是独立页面，每个目都有一段写作摘要。摘要用于冻结范围，不代表正文已经完成。
  MARKDOWN
  write_document(
    DOCS_DIR.join("preface.md"),
    {
      "title" => "序言",
      "linkTitle" => "序言",
      "weight" => 2,
      "type" => "docs",
      "breadcrumbs" => true,
      "comments" => false,
      "book_kind" => "preface"
    },
    preface_body
  )

  write_document(
    DOCS_DIR.join("ch00/_index.md"),
    {
      "title" => "第 0 章（可跳过）#{chapter_zero['title']}",
      "linkTitle" => "第 0 章 准备实验环境",
      "weight" => 3,
      "aliases" => chapter_zero["aliases"],
      "type" => "docs",
      "breadcrumbs" => true,
      "comments" => false,
      "book_kind" => "chapter-zero",
      "book_status" => "scaffold"
    },
    chapter_zero_index_body(chapter_zero)
  )

  ordinal = 0
  chapter_zero["sections"].each do |section|
    write_document(
      DOCS_DIR.join("ch00/#{section['slug']}.md"),
      section_metadata(chapter_zero, section),
      section_body(chapter_zero, section, ordinal)
    )
    ordinal += section["items"].length
  end

  VOLUMES.each do |volume|
    write_document(
      DOCS_DIR.join("#{volume['slug']}.md"),
      {
        "title" => volume["title"],
        "linkTitle" => volume["title"],
        "weight" => volume["weight"],
        "aliases" => volume["aliases"],
        "type" => "docs",
        "breadcrumbs" => true,
        "comments" => false,
        "book_kind" => "volume-overview",
        "book_number" => volume["number"],
        "book_status" => "scaffold"
      },
      volume_page_body(volume, chapters)
    )
  end

  chapters.each do |chapter|
    chapter_dir = DOCS_DIR.join(chapter["slug"])
    write_document(chapter_dir.join("_index.md"), chapter_metadata(chapter), chapter_index_body(chapter))
    chapter["sections"].each do |section|
      write_document(
        chapter_dir.join("#{section['slug']}.md"),
        section_metadata(chapter, section),
        section_body(chapter, section, ordinal)
      )
      ordinal += section["items"].length
    end
  end

  write_document(
    DOCS_DIR.join("toc.md"),
    {
      "title" => "完整目录",
      "linkTitle" => "目录",
      "weight" => 4,
      "type" => "docs",
      "breadcrumbs" => false,
      "comments" => false,
      "book_kind" => "table-of-contents"
    },
    full_toc_body(chapter_zero, chapters)
  )

  write_document(
    DOCS_DIR.join("indexes/_index.md"),
    {
      "title" => "索引中心",
      "linkTitle" => "索引",
      "weight" => 910,
      "type" => "docs",
      "breadcrumbs" => true,
      "comments" => false,
      "book_kind" => "index-hub"
    },
    <<~MARKDOWN
      > 除按章、节、目顺序阅读外，还可以按角色、任务、技术边界、事故症状或分区能力查找内容。

      ## 索引入口

      - [按角色阅读](/indexes/roles/)
      - [按任务查找](/indexes/tasks/)
      - [技术边界索引](/indexes/capabilities/)
      - [事故症状与首个安全动作](/indexes/incidents/)
      - [分区能力五触点](/indexes/partition/)
      - [完整编号目录](/toc/)
    MARKDOWN
  )

  index_pages = {
    "roles.md" => ["按角色阅读", 10, roles_index_body(chapters)],
    "tasks.md" => ["按任务查找", 20, tasks_index_body(chapters)],
    "capabilities.md" => ["技术边界索引", 30, capabilities_index_body(chapters)],
    "incidents.md" => ["事故症状与首个安全动作", 40, incidents_index_body(chapters)],
    "partition.md" => ["分区能力五触点", 50, partition_index_body(chapters)]
  }
  index_pages.each do |filename, (title, weight, body)|
    write_document(
      DOCS_DIR.join("indexes/#{filename}"),
      {
        "title" => title,
        "linkTitle" => title,
        "weight" => weight,
        "type" => "docs",
        "breadcrumbs" => true,
        "comments" => false,
        "book_kind" => "index"
      },
      body
    )
  end

  appendices = parse_appendices(text)
  write_document(
    DOCS_DIR.join("appendices/_index.md"),
    {
      "title" => "附录与速查",
      "linkTitle" => "附录",
      "weight" => 900,
      "type" => "docs",
      "breadcrumbs" => true,
      "comments" => false,
      "book_kind" => "appendices"
    },
    appendices.map { |appendix| "- [附录 #{appendix['letter']}：#{appendix['title']}](#{appendix['letter'].downcase}/)" }.join("\n")
  )
  appendices.each_with_index do |appendix, appendix_index|
    lines = [
      "> 本附录先建立可检索骨架，后续随正文与版本基线同步补充。",
      ""
    ]
    appendix["items"].each_with_index do |item, item_index|
      number = "#{appendix['letter']}.#{item_index + 1}"
      lines << "## #{number} #{item} {#appendix-#{appendix['letter'].downcase}-#{item_index + 1}}"
      lines << ""
      lines << appendix_summary(item, appendix["title"], item_index)
      lines << ""
    end
    write_document(
      DOCS_DIR.join("appendices/#{appendix['letter'].downcase}.md"),
      {
        "title" => "附录 #{appendix['letter']}：#{appendix['title']}",
        "linkTitle" => "附录 #{appendix['letter']} #{appendix['title']}",
        "weight" => (appendix_index + 1) * 10,
        "type" => "docs",
        "breadcrumbs" => true,
        "comments" => false,
        "book_kind" => "appendix",
        "book_status" => "scaffold"
      },
      lines.join("\n")
    )
  end
end

unless OUTLINE_PATH.file?
  warn "Missing outline: #{OUTLINE_PATH}"
  exit 1
end

refresh = ARGV.include?("--refresh")
docs_nonempty = DOCS_DIR.exist? && !DOCS_DIR.children.empty?

if refresh && docs_nonempty && (!SCAFFOLD_SENTINEL.file? || SCAFFOLD_SENTINEL.read(encoding: "UTF-8").strip != "generated-by=bin/scaffold_book.rb")
  warn "Refusing to refresh #{DOCS_DIR}: scaffold sentinel is missing or invalid."
  exit 1
end

if docs_nonempty && !refresh
  warn "Refusing to overwrite non-empty #{DOCS_DIR}. Archive or move it first."
  exit 1
end

text = OUTLINE_PATH.read(encoding: "UTF-8")
chapters = parse_chapters(text)
chapter_zero = parse_chapter_zero(text)
validate_model(chapter_zero, chapters)

write_data_files(chapters, refresh: refresh)
write_scaffold(text, chapter_zero, chapters)
SCAFFOLD_SENTINEL.write("generated-by=bin/scaffold_book.rb\n", mode: "w", encoding: "UTF-8")

section_count = chapters.sum { |chapter| chapter["sections"].length }
item_count = chapters.sum { |chapter| chapter["sections"].sum { |section| section["items"].length } }
puts "Generated #{chapters.length} chapters, #{section_count} section pages, and #{item_count} item summaries."
puts "Generated chapter zero with #{chapter_zero['sections'].length} section pages."
puts "Content root: #{DOCS_DIR}"
puts "Data source: #{DATA_DIR.join('chapters.yaml')}"
