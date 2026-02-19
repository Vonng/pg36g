---
title: "PG 图形客户端工具"
weight: 150
math: true
breadcrumbs: false
---

PostgreSQL 最强的的客户端永远都是自带的 `psql` 命令行工具，但对于初学者来说，使用图形化的客户端工具会更容易上手。


## Intellij IDEA

PostgreSQL 生态有许许多多的 GUI 图形工具，老冯的经验是，Intellij IDEA 全家桶自带的 Database Tool 最好用。
Intellij IDEA 全家桶的 Database Tool 还是在很多任务上省掉老冯不少时间，毕竟是专业做 IDE 起家的，编辑器的体验没得说。下位免费替代是 VS Code。

不过，这是一个收费商业软件 —— 如果你有开源项目，可以申请免费的许可证。如果你是学生或者老师，可以申请免费的教育许可证。
如果你是是公司员工，可以找公司报销一个。如果你是野路子玩家，也可以去搜一个验证码或者认证服务器，或者干脆无限循环用那个 30 天试用许可证。

![pggui-intellij.jpg](pggui-intellij.jpg)


## pgAdmin

如果你想要使用不收费的工具，pgAdmin 是 PostgreSQL “官方” 开发的图形化客户端管理工具，你可以使用 Docker 拉起它，并且从浏览器中访问。
Pigsty 自带了 pgAdmin 的模板，通常在 Pigsty 中只需要两行命令就可以把它拉起来。

Pigsty: [pgAdmin 教程](https://pigsty.cc/docs/app/pgadmin/)

```bash
cd ~/pigsty
./docker.yml              # 安装 Docker 
./app.yml -e app=pgadmin  # 安装 pgAdmin
```

访问 8885 端口，默认用户名 `admin@pigsty.cc`，密码是 `pigsty`。

pgAdmin 是一个 Python 糊的工具，功能非常丰富，但界面有点老旧，使用起来也有些繁琐。
但如果你想要从浏览器中管理 PG 实例，这可能是最合适的工具。

![pggui-pgadmin.jpg](pggui-pgadmin.jpg)


## DBeaver

另一个支持许多数据库的开源图形化客户端工具是 DBeaver，它支持 PostgreSQL、MySQL、Oracle、SQL Server 等多种数据库。

这个也是开源免费的，界面挫一点，但也能用。

![pggui-dbeaver.jpg](pggui-dbeaver.jpg)


## VS Code

最近微软官方出品了一个 VS Code 扩展插件，PostgreSQL ，免费不要钱，能凑合用。

![pggui-vscode.jpg](pggui-vscode.jpg)


## 其他

除此之外，也有许多其他图形工具可以使用，比如 Navicat，以及各种各样的商业工具，但老冯的看法是没必要折腾。


## 建议

图形界面这个东西有个能用的就行，太依赖图形界面对学习来说不是一件好事，因为你会浪费很多时间在 GUI 界面上，而不是数据库的本质上，老冯的建议是：

- 想要最好的就去整个 Intellij（或者专门的 DataGrip）
- 开源免费 + 通过浏览器管理： pgAdmin
- 开源免费 + 桌面客户端工具： DBeaver



## 使用

不管是什么工具，使用起来都是一个套路，你需要 “连接到 PostgreSQL 数据库”，通常需要你输入 Host, Port, User, Password, Database 这五个关键信息！

- Host： 数据库主机的域名或者 IP 地址
- Port： PostgreSQL 的端口，默认是 5432
- User： PostgreSQL 的用户名，在 Pigsty 中，默认的超级管理员用户名是 `dbuser_dba`
- Pass： PostgreSQL 用户密码，在 Pigsty 中，默认的超级管理员密码是 `DBUser.DBA`
- Database： 你要连接的数据库名称，在 Pigsty 单机默认模板中，默认的数据库名称是 `meta`。

绝大多数客户端也接受另外一种 URL 形式的参数，也就是把上面五个要素组合起来，拼成一个 `PGURL`：

```bash
postgresql://dbuser_dba:DBUser.DBA@10.10.10.10:5432/meta
```

> [!NOTE] 请记得把 IP 地址，密码换成你自己的！

如果你之前申请了域名，并且指向了数据库服务器，你也可以用域名来访问（比如我这里的 `pgsql.cc` 替代 IP 地址的 `host`）：

```bash
postgresql://dbuser_dba:DBUser.DBAJP@pgsql.cc/meta
```

当然，不要忘了把这里的密码换成你自己的密码

> [!WARNING] 什么？你跟我说没改过？不要心存侥幸，裸奔云服务器分分钟让你见识赛博世界的险恶 ;-）
>
> 在你往这台 VPS 放任何重要的东西之前，请务必阅读安全加固部分的教程！服务器被黑了，老冯可不负责！




