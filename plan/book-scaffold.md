# 《PostgreSQL 36 计》内容脚手架说明

## 结构

站点按“章 → 节页面 → 目标题”组织。36 个正文章直接位于 `docs/` 顶层：

```text
docs/
├── upper-volume.md              # 上卷导读，weight 100
├── postgresql-pigsty-map/       # ch01，weight 110
│   ├── _index.md
│   ├── 01.md
│   └── ...
├── psql-workflow/               # ch02
├── ...                          # ch03–ch18
├── lower-volume.md              # 下卷导读，weight 285
├── deployment-baseline/         # ch19，weight 290
├── ...                          # ch20–ch35
├── postmortem-platform-improvement/ # ch36
├── ch00/
├── guide/
├── appendices/
├── indexes/
├── _index.md
├── preface.md
└── toc.md
```

- “上卷／下卷”是两个顶层导读索引页，与 36 章并列；它们不是目录，不拥有或包裹章节；
- 上卷页按权重排在 ch01 前，下卷页按权重排在 ch18 与 ch19 之间；
- 六篇是完整目录与首页中的教学分组，也不增加 URL 层级；
- 每章使用顶层语义 slug；例如 ch19 的规范地址是 `/deployment-baseline/`；
- 两个卷页使用 `/upper-volume/` 与 `/lower-volume/`，旧 `/volume-1/` 与 `/volume-2/` 继续兼容；
- `/ch01/`–`/ch36/` 与原两卷嵌套地址继续作为兼容别名；
- 普通目录、节页面和导航链接不显示分类标签；相关分类仅保留在 front matter 和“技术边界索引”正文中；
- 每个节是单独的 Markdown 页面；
- 每个目使用 `{#item-19-2-1}` 形式的稳定锚点，并有一段写作摘要。

## 单一目录来源

- 编辑源：`plan/book-outline-final.md`
- 机器可读章节数据：`data/chapters.yaml`
- 全书、概念卷与教学分组数据：`data/book.yaml`
- 生成器：`bin/scaffold_book.rb`

`data/*.yaml` 与 `docs/` 脚手架由生成器从最终目录产生，不应分别手工维护。

## 当前规模

- 正式章节：36
- 正式节页面：242
- 正式目摘要：772
- 第 0 章节页面：3
- 完整目录中的目链接：781（含第 0 章 9 目）
- Hugo 内容源文件：302（含两个卷导读页与生成标记）

## 生成与验证

首次生成要求 `docs/` 为空：

```bash
make scaffold
```

在尚未开始手工扩写正文时，可以刷新生成内容：

```bash
make scaffold-refresh
```

`scaffold-refresh` 会覆盖带生成标记的脚手架页面。开始逐目写正文后，不应再直接运行该命令；应先修改生成模型或把需要保留的正文从生成区分离。

完整验证：

```bash
make check-book
```

检查器会验证章节编号、页面数、目摘要、锚点、旧 URL 别名、归档文件数、Hugo 构建及所有内部 Markdown 链接。

## 旧内容归档

重建前的完整 `docs/` 已移动到：

```text
archive/2026-07-29-pre-scaffold/docs/
```

归档包含当时未提交的修改、未跟踪页面与图片，共 76 个内容文件；两个 `.DS_Store` 不纳入 Git。恢复或迁移旧正文前应先阅读归档目录中的 `README.md`，不要直接覆盖新脚手架。

第一版“两卷嵌套”生成脚手架另行封存于：

```text
archive/2026-07-29-nested-volume-scaffold/docs/
```

它仅用于比较或回溯导航结构；当前扁平脚手架才是后续写作基线。
