---
title: "快速上手 PostgreSQL"
weight: 140
math: true
breadcrumbs: false
---

老冯最近多次被人问到一个问题：“如何学习 PostgreSQL”?
老冯认为，学习 PostgreSQL 的最好方式就是 Learn by doing —— 通过实践来学习，而不是通过死看书，报什么培训班之类的东西。

现在的学习条件要比以前好太多了，因为每个人都可以有一个非常耐心的高水平老师在身边随时指导 —— 有什么问题问就是了。
不过俗话说：“师傅领进门，修行在个人”。即使有 AI 助力，起步的那个入门过程依然是最难的。
所以，老冯决定写这个快速上手教程，帮助你完成快速上手的第一步。

那么，什么样的实践才是最适合上手 PostgreSQL 的呢？实话说直到今天，
老冯依然没看到一个让我觉得做的好的教程，这也是老冯写这本教程的原因 —— 
我想给初学者提供一个符合直觉，符合认知习惯的上手学习教程。


--------

## 如何入门 PG？

入门 PG 的第一步，是有一个 PG 实例，而不是有一本什么书。
老冯的建议是，你先不要去急着看什么 PG 文档和书，先拉起真实一套生产环境中的单机 PostgreSQL，
观察它，使用它，用它解决一个小而美的具体实战问题，这比吭哧吭哧傻看多少书都要有用。

老冯的建议是 —— 你不要去折腾什么 Docker 容器镜像，Postgres.App，或者直接去买什么云数据库来用。
而是直接学习在真实生产环境中的 PostgreSQL —— 原生运行在裸 Linux 上的 PG，没有各种花里胡哨的东西与中间层。
切莫花费大把时间浪费在 “环境配置” 上，这件事，花个10分钟，都嫌多。

这就是老冯的 Pigsty 能起到作用的地方 —— 为你提供一个学习 PostgreSQL 的最佳环境！
你可以参考 [ClawCloud 新手指南](/ch01/clawcloud) 搞一台高性价比的 Linux VPS 作为你的学习环境，
然后参考 [**Pigsty 快速上手**](https://pigsty.cc/docs/setup/) 教程，用一行命令，十分钟，完成安装过程。

```bash
curl -fsSL https://repo.pigsty.cc/get | bash  # 安装 Pigsty 与依赖
cd ~/pigsty; ./configure -g                   # 生成配置（使用默认单机配置模板，-g 参数会生成随机密码）
./deploy.yml                                  # 执行部署剧本，完成部署
```

是的，就是这么简单。您完全可以在不了解任何细节的情况下，使用 [**预制配置模板**](https://pigsty.cc/docs/concept/iac/template) 一键拉起一套企业级质量的 PostgreSQL。
接下来，您可以探索 [**图形用户界面**](https://pigsty.cc/docs/setup/webui/)，访问 [**PostgreSQL 数据库服务**](https://pigsty.cc/docs/setup/pgsql/)。


--------

## Pigsty 是干什么的？

Pigsty 是老冯编写的一套开源 PostgreSQL RDS 方案，目前是开源 PG RDS 中顶尖水准，Star 数也是全球 PG 开源生态里来自中国的 No.1。
简单来说，就是自建生产级 PG 数据库服务的套件。让普通研发运维也有能力在没有专业DBA/数据库专家的情况下，构建起企业级的 PostgreSQL 数据库服务。

“企业级” 一般和 “复杂” 划等号，但 Pigsty 的设计理念是让复杂的东西变得简单易用。所以我们把它设计成了一个开箱即用的方案。
而且最妙的是它可以运行在一台 1C/1G 的 Linux VPS 上，完全开源免费。


Pigsty 在北欧风格的创业公司 —— 探探中管理了 25000 核 vCPU 的数据库。
但它竟然也能完整运行在一台 1C1G 的虚拟机上！所以，我们有许多的研发同事也使用它作为自己的开发沙箱 —— 开发环境，测试环境，生产环境全部统一使用一套方案。
这意味着你学到的所有东西可以无缝衔接直接上生产实战。

更好玩的是，他还带有 Nginx，自动替你配置域名，签发 HTTPS 证书，轻松完成网站搭建与交付。
它还带有可观测性基础设施，能够让你清楚的知道整个环境中正在发生什么，而不是两眼一抹黑看着黑箱子盲人摸象。
最妙的是，它还带有开箱即用的 Claude Code 和 Opencode —— AI Agent，你甚至可以不用花钱就有一位老师随时指导你！

好的，那说了这么多，让我们来看一看，到底应该如何学习？



## 快速上手

聊了这么多前戏，现在你的手头应该有一个 Linux VPS 了吧？如果没有，可以参考 [这个教程](/ch01/clawcloud)

ssh 登陆上你的服务器，然后执行以下命令。（完整安装教程： https://pigsty.cc/docs/setup/install）

```bash
curl https://repo.pigsty.cc/get | bash -s v4.0.0; cd ~/pigsty
./configure -g
./deploy.yml
```

嘿，大概几分钟后，你就有了一个开箱即用的 PostgreSQL 开发沙箱了！让我们来看看这个箱子里到底有什么？

![](https://pigsty.cc/img/pigsty/arch.png)


真的有好多东西啊！但别的先仍一边，最核心的东西就是这个 PostgreSQL 数据库了！它默认监听本地的 `5432` 端口。


## 访问数据库

现在，让我们来试一下，退出你的 ssh 连接重新登陆上来，敲一个 `p`，神奇的事情就发生了！你通过 PostgreSQL 自带的命令行工具 `psql` 连接上了数据库！

```bash
root@s879132:~# p
psql (17.6 (Ubuntu 17.6-1.pgdg24.04+1))
Type "help" for help.

# 现在你可以输入 SQL 语句了！
postgres=#
```

让我们执行一条 SQL：

```bash
postgres=# SELECT version(); 

                                                              version
-----------------------------------------------------------------------------------------------------------------------------------
 PostgreSQL 17.6 (Ubuntu 17.6-1.pgdg24.04+1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0, 64-bit
```

如果输出结果太长，`psql` 会使用分页器显示，你可以使用 `q` 键退出分页器。

> [!Note] 按下 `Ctrl + C ` 可以中断当前的查询，再按下 `Ctrl + D` 退出 `psql` 命令行工具。

当然，如果你不熟悉命令行工具，也许会感到陌生与害怕，没关系，我们可以先用一个 [图形化的客户端工具](/ch01/gui) 来操作数据库。
并且在第二章介绍几个核心命令行工具的基础使用方法。

--------

## 数据库连接串

你是如何连接上数据库的呢？其实不论是 PG 自带的 `psql`，还是图形客户端工具，想要访问数据库，都需要一些连接参数
通常需要你输入 Host, Port, User, Password, Database 这五个关键信息！

- Host： 数据库主机的域名或者 IP 地址
- Port： PostgreSQL 的端口，默认是 5432
- User： PostgreSQL 的用户名，在 Pigsty 中，默认的超级管理员用户名是 `dbuser_dba`
- Pass： PostgreSQL 用户密码，在 Pigsty 中，默认的超级管理员密码是 `DBUser.DBA`
- Database： 你要连接的数据库名称，在 Pigsty 单机默认模板中，默认的数据库名称是 `meta`。

绝大多数客户端也接受另外一种 URL 形式的参数，也就是把上面五个要素组合起来，拼成一个 `PGURL`：
这个 URL 的形式是： `postgresql://<username>:<password>@<host>:<port>/<dbname>`，
比如，你这台数据库的默认超级管理员用户（如果没改密码），连接串就长成这样：

```bash
postgresql://dbuser_dba:DBUser.DBA@10.10.10.10:5432/meta
```

- `username`: `dbuser_dba`
- `password`: `DBUser.DBA`
- `host`: `10.10.10.10`（你可能要换成你自己的 IP，但如果是本机，可以用 127.0.0.1）
- `port`: `5432` （可以省略）
- `dbname`: `meta`


当然，不要忘了把这里的密码换成你自己的密码。在 `configure -g` 的时候，Pigsty 会随机生成一系列强密码并打印出所有的密码。
如果你找不到了，打开 `~/pigsty/pigsty.yml` 文件，它们都在那里。

```bash
vagrant@meta:~/pigsty$ ./configure -g
configure pigsty v4.0.0 begin
[ OK ] region = china
[ OK ] kernel  = Linux
[ OK ] machine = x86_64
[ OK ] package = deb,apt
[ OK ] vendor  = ubuntu (Ubuntu)
[ OK ] version = 24 (24.04)
[ OK ] sudo = vagrant ok
[ OK ] ssh = vagrant@127.0.0.1 ok
[WARN] Multiple IP address candidates found:
    (1) 192.168.121.91	    inet 192.168.121.91/24 metric 100 brd 192.168.121.255 scope global dynamic eth0
    (2) 10.10.10.10	    inet 10.10.10.10/24 brd 10.10.10.255 scope global eth1
[ OK ] primary_ip = 10.10.10.10 (from demo)
[ OK ] admin = vagrant@10.10.10.10 ok
[ OK ] mode = meta (ubuntu24.04)
[ OK ] locale  = C.UTF-8
[ OK ] generating random passwords...
    grafana_admin_password   : Zg4VXdox1Hzs2WM1Wl7p0dWJ
    pg_admin_password        : fhLp4uDXzf7iKy6XrMRTFSYi
    pg_monitor_password      : c8V0ueQMUMAxh90X8AAHkZqQ
    pg_replication_password  : ILci8LulBthxR3AeYlI6FB51
    patroni_password         : kwDndNOlWfTthEtBJqe26bqd
    haproxy_admin_password   : PSCVibCYsgOzIVJWBMnvVlfg
    minio_secret_key         : dDFJqCCYBAz8Q1im1cv4KvBc
    etcd_root_password       : RF0xptlDBkH2OjVuFjEvXEgX
    DBUser.Meta              : rNEte4RA4o2etmh0ujVXye9S
    DBUser.Viewer            : vNpTrcG7HrxQot4qC1QaahJz
    S3User.Backup            : ENJUEr8CTZw60dmM9rRJtw4B
    S3User.Meta              : lrQ8l3vmUHgi9BPLk2YioA0K
    S3User.Data              : cnwstrEMd0lnNnvwPYCRVNDv
[ OK ] random passwords generated, check and save them
[ OK ] ansible = ready
[ OK ] pigsty configured
[WARN] don't forget to check it and change passwords!
proceed with ./deploy.yml
```


--------

## 请老师登场

现在你有一个数据库了！接下来，我建议你找一位 “AI 老师”。如果你不差钱，去买一个 Claude Code 订阅，每月 20 美刀就已经强大。
如果你不想花钱，Pigsty 自带的 opencode 带来一些免费的模型，比如 GLM 4.7 ，
你也可以参考老冯的这篇教程 《[Claude Code 免翻上手教程：](https://vonng.com/db/claude-code-intro/)》 买一个订阅计划。

```bash
curl -fsSL https://repo.pigsty.cc/claude | bash   # 下载安装
source .claude/env; ccm set glm 你的APIKEY         # 配置密钥
glx           # = ccm glm; claude --dangerously-skip-per
```

当然，Pigsty 也自带了另外一个 AI Agent —— OpenCode，里面带有一些免费的 Key。
我们这里就以 opencode 为例，来看看如何让 AI 老师帮助你学习 PostgreSQL。
进入 `~/pigsty` 目录，键入 `opencode`，就会自动启动一个 TUI （终端图形界面） 的程序，你可以在对话框里聊天。

```bash
cd ~/pigsty; opencode
```

> 按下 Ctrl+P 可以切换模型，你可以选择 GLM 4.7 免费模型 

如果你想要登陆付费订阅计划，执行：`opencode auth login` 选择 Zhipu AI Coding Plan 输入密钥即可。

然后，你就可以开始提问了，老冯会在教程里面列举一些常见的问题，供你参考。然后你就可以开始和 AI 老师聊天学习了！




---------

## 现在做点什么

现在，你就问问题就好了，这些 AI Agent 干这种事还是很靠谱的。
所以关键就是你能清晰的用语言表达出你感兴趣的问题。
老冯会在后面的教程里准备一系列有趣的问题。

```bash
现在我想要学习 PostgreSQL，我是一个新手，所以请详细的告诉我需要的一切。
当前的环境里有一个 PostgreSQL 数据库实例，使用 Pigsty 部署，
可以用命令行 psql postgres://dbuser_dba@/meta 直接访问。
现在，请你检查这个 PostgreSQL 实例，告诉我关于它的基本信息，版本，系统，数据库，用户，空间使用等等。
```

```bash
请你告诉我，我应该如何用 psql 命令行工具访问数据库？连接上去之后我能做点什么？请你给我讲讲有什么基本操作，帮助我快速上手。
如果用的是 Intellij IDEA 这个图形化客户端工具，我应该如何配置连接参数？请你告诉我连接参数应该是什么样子的。
```

```bash
我现在想要了解一下向量数据库扩展 vector 这个扩展怎么用，你能简单向我展示一下它的功能吗？给我一些可以上手实践的例子。
请你帮我设计一系列例子，演示它的功能，你可以把这些例子和说明写成一个文档，放在 ~/vector.md 这里。
```

```bash
请你利用当前环境中的 Nginx ，帮我实现一个最简单的带登陆的页面，在数据库中保存登陆状态。
数据库可以用 postgres://dbuser_meta@/meta，密码在 ~/pigsty/pigsty.yml 里面。
用什么语言工具我不管，反正我希望尽可能简单。你可以 sudo，python 包管理器用 uv 。
放在 /www/login 目录下，可以通过浏览器访问。你的设计思路和解释可以写入一个文档：~/login.md 。
```

你可以尽情的开 YOLO 模式折腾，反正搞砸了，你可以直接销毁重建，两分钟的事：

```bash
./pgsql-rm.yml  # 抹掉当前数据库集群
./pgsql.yml     # 重新当前数据库集群
```

如果你有一些重要的数据已经放进数据库里了，也可以利用 [**即时克隆**](https://pigsty.cc/docs/pgsql/admin/db) 功能，
瞬间克隆出一个一样的数据库/实例，而且不占用额外的存储 —— 用来随便折腾。 



---------

## 当然，如果你确实想 “系统学习”

如果你确实想要 “系统性” 的学习 PostgreSQL，那么阅读一遍 PostgreSQL 官方文档是必不可少的。
这是一份极好的文档，内容详实，覆盖面广，值得反复阅读。国内唐成老师的《PostgreSQL 修炼之道，从小工到专家》围绕文档进行解读，也是一本不错的入门书籍。

但还是那句话，光看书是没用的，你必须要有一个真实的数据库环境，用真实（或者拍脑袋）的应用与实践场景来动手，才是王道。



