---
title: "本地 Vagrant 环境搭建"
weight: 200
math: true
breadcrumbs: false
---


Pigsty 需要 Linux 环境，您可以使用 [**Vagrant**](https://www.vagrantup.com/) 轻松创建本地 linux 虚拟机。

您还需要一个虚拟机提供商，（比如笔记本电脑的 [VirtualBox](https://www.virtualbox.org/) 和服务器的 libvirt）


--------

## MacOS + Virtualbox 组合

如果你希望在自己的 MacOS 笔记本上创建虚拟机，那么最简单的方式就是使用默认的 vagrant + Virtualbox 组合。

你可以直接使用 homebrew 包管理器来一键安装这两个组件（需要你输入密码获取管理员权限）

```bash
brew install vagrant virtualbox ansible
```



--------

## Ubuntu + Libvirtd 组合

从 HashiCorp 官方仓库安装 Vagrant： 

```bash
echo "deb [trusted=yes] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt -y install vagrant
```

安装 libvirt 和相关组件：

```bash
# 安装 libvirt 和相关组件
sudo apt -y install qemu-kvm qemu-system libvirt-daemon-system libvirt-clients bridge-utils virtinst virt-manager dnsmasq-base

# 把当前用户加入 kvm 和 libvirt 组
sudo usermod -aG kvm,libvirt $USER

# 启动并设为开机自启
sudo systemctl enable --now libvirtd

# 重新登录（或执行 newgrp）让组生效
newgrp libvirt
virsh list --all   # 正常应不报错并显示空列表
```

安装 libvirt Provider 插件（会编译本地扩展）

```bash
# 为编译插件准备依赖
sudo apt -y install build-essential gcc make pkg-config ruby ruby-dev libvirt-dev libxml2-dev libxslt1-dev zlib1g-dev

# 安装 vagrant-libvirt 插件（需要科学上网）
vagrant plugin install vagrant-libvirt
```

您需要选择选择支持 libvirt 的 Vagrant Box，大部份 Pigsty 默认选用的 Box 都提供了 libvirt 支持。 

```bash
echo "export VM_PROVIDER=libvirt" >> ~/.bash_profile
```



--------

## RockyLinux + Libvirtd 组合


--------

## Windows + Hyper-V 组合







## 入门 [#get-started]

您可以在 macOS 上使用 [**homebrew**](https://brew.sh/) 安装 vagrant、virtualbox、ansible：

```bash title="在 macos 上安装"
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install vagrant virtualbox ansible
```

您已准备就绪！使用 `make` 快捷方式创建虚拟机：

```bash title="~/pigsty"
make meta       # 1 节点开发箱，用于快速启动、开发、测试和实验
make full       # 4 节点沙盒，用于 HA 测试和功能演示
make simu       # 36 节点模拟箱，用于生产环境模拟
...
make meta9      # 使用 bento/rockylinux-9 镜像创建单例元节点
make full22     # 使用 generic/ubuntu2204 镜像创建 4 节点沙盒
make simu12     # 使用 generic/debian12 镜像创建 36 节点模拟环境
```

--------

## 配置 [#configuration]

您必须在启动前在 [`Vagrantfile`](https://github.com/pgsty/pigsty/blob/main/vagrant/Vagrantfile) 中定义虚拟机。
默认的 Vagrantfile 定义了一个 el9（[`bento/rockylinux-9`](https://app.vagrantup.com/bento/boxes/rockylinux-9)）1 节点虚拟机，使用本地 virtualbox VM 提供商。

{{< filetree/container >}}
  {{< filetree/folder name="vagrant" >}}
    {{< filetree/folder name="spec" state="closed" >}}
      {{< filetree/file name="[meta.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/meta.rb)" >}}
      {{< filetree/file name="[full.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/full.rb)" >}}
      {{< filetree/file name="[simu.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/simu.rb)" >}}
      {{< filetree/file name="..." >}}
    {{< /filetree/folder >}}
    {{< filetree/file name="[Vagrantfile](https://github.com/pgsty/pigsty/blob/main/vagrant/Vagrantfile)" >}}
  {{< /filetree/folder >}}
{{< /filetree/container >}}

我们在 [`vagrant/spec`](https://github.com/pgsty/pigsty/tree/main/vagrant/spec) 文件夹中有一系列预定义的 VM 规格

|                                 模板                                 |  节点  |      规格       |         注释         |  别名  |
|:-------------------------------------------------------------------------:|:-------:|:---------------:|:-----------------------:|:-------:|
| [meta.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/meta.rb) | 1 节点  |    2c4g x 1     |    单节点元数据     | 开发箱  |
| [dual.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/dual.rb) | 2 节点  |    1c2g x 2     |       双节点        |         |
| [trio.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/trio.rb) | 3 节点  |    1c2G x 3     |       三节点       |         |
| [full.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/full.rb) | 4 节点  | 2c4g + 1c2g x 3 |  全功能 4 节点   | 沙盒 |
| [simu.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/simu.rb) | 36 节点 |      杂项       |   生产环境模拟   | 模拟箱 |
|  [oss.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/oss.rb)  | 3 节点  |    1c2g x 3     | 3 节点 OSS 构建环境 |         |
|  [pro.rb](https://github.com/pgsty/pigsty/blob/main/vagrant/spec/pro.rb)  | 5 节点  |    1c2g x 5     | 5 节点 PRO 构建环境 |         |

每个规格文件包含一个描述 VM 节点的 `Specs` 变量。例如，`full.rb` 包含：

```ruby
# full: pigsty 全功能 4 节点沙盒，用于 HA 测试、教程和实践

Specs = [
  { "name" => "meta"   , "ip" => "10.10.10.10" ,  "cpu" => "2" ,  "mem" => "4096" ,  "image" => "bento/rockylinux-9"  },
  { "name" => "node-1" , "ip" => "10.10.10.11" ,  "cpu" => "1" ,  "mem" => "2048" ,  "image" => "bento/rockylinux-9"  },
  { "name" => "node-2" , "ip" => "10.10.10.12" ,  "cpu" => "1" ,  "mem" => "2048" ,  "image" => "bento/rockylinux-9"  },
  { "name" => "node-3" , "ip" => "10.10.10.13" ,  "cpu" => "1" ,  "mem" => "2048" ,  "image" => "bento/rockylinux-9"  },
]
```

您可以使用规格与 [`config`](https://github.com/pgsty/pigsty/tree/main/vagrant/config) 脚本，它将根据规格和环境变量（资源、镜像、vm 提供商等...）渲染 `Vagrantfile`。

```bash
cd ~/pigsty
vagrant/config [spec] [image] [scale] [provider]

vagrant/config meta                # 使用 1 节点规格，默认 el8 镜像
vagrant/config dual el9            # 使用 2 节点规格，使用 el9 镜像
vagrant/config trio d12 2          # 使用 3 节点规格，使用 debian12 镜像，双倍 cpu/mem 资源
vagrant/config full u22 4          # 使用 4 节点规格，使用 ubuntu22 镜像，使用 4x cpu/mem 资源         
vagrant/config simu u24 1 libvirt  # 使用 36 节点规格，使用 ubuntu24 镜像，使用 libvirt 作为提供商而不是 virtualbox 
```

您可以使用环境变量 `VM_SCALE` 扩展资源单位，默认值为 `1`。

例如，`VM_SCALE=2 vagrant/config meta` 将使 meta 规格的 cpu / mem 资源翻倍

```bash
Specs = [
  { "name" => "meta" , "ip" => "10.10.10.10", "cpu" => "8" , "mem" => "16384" , "image" => "bento/rockylinux-9" },
]
```

--------

## 快捷方式 [#shortcuts]

配置后，您可以使用 `vagrant up` 命令创建虚拟机。

Pigsty 模板将使用您的 `~/.ssh/id_rsa[.pub]` 作为 vagrant 置备的默认 ssh 密钥。
在开始之前确保您有有效的 ssh 密钥对，您可以通过以下方式生成一个：`ssh-keygen -t rsa -b 2048`

有一些包装 vagrant 命令的快捷方式，您可以使用它们来管理虚拟机。

```bash title="~/pigsty/vagrant"
make         # = make start
make new     # 销毁现有 vm 并创建新的
make ssh     # 将 VM ssh 配置写入 ~/.ssh/     （必需）
make dns     # 将 VM DNS 记录写入 /etc/hosts （可选）
make start   # 启动 VM 并写入 ssh 配置    （up + ssh） 
make up      # 使用 vagrant up 启动 VM
make halt    # 关闭 VM （down,dw）
make clean   # 销毁 VM （clean/del/destroy）
make status  # 显示 VM 状态 （st）
make pause   # 暂停 VM （suspend,pause）
make resume  # 恢复 VM （resume）
make nuke    # 使用 virsh 销毁所有 vm 和卷（如果使用 libvirt） 
```

--------

## 版本 [#version]

Pigsty 目前使用以下 vagrant 盒子进行测试：

```bash title="x86_64"
$ vagrant box list

el8 :  bento/rockylinux-8     (libvirt, 202502.21.0, (amd64))
el9 :  bento/rockylinux-9     (libvirt, 202502.21.0, (amd64))

d11 :  generic/debian11       (libvirt, 4.3.12, (amd64))
d12 :  generic/debian12       (libvirt, 4.3.12, (amd64))

u20 :  generic/ubuntu2004     (libvirt, 4.3.12, (amd64))
u22 :  generic/ubuntu2204     (libvirt, 4.3.12, (amd64))
u24 :  bento/ubuntu-24.04     (libvirt, 20250316.0.0, (amd64))
```

它们并非都有 `arm64` 架构支持，所以在使用 Apple Silicon MacOS 时要注意。

```bash title="aarch64"
bento/rockylinux-9 (virtualbox, 202502.21.0, (arm64))
bento/ubuntu-24.04 (virtualbox, 202502.21.0, (arm64))
```

您可以在 https://app.vagrantup.com/bento/boxes 上找到支持的 Box 镜像

--------

## 注意事项 [#caveat]

{{< callout type="warning" >}}

**VirtualBox 网络配置：** 当使用较旧版本的 VirtualBox 作为 Vagrant 提供商时，需要额外设置才能使用默认的 `10.x.x.x` CIDR 作为仅主机网络：将其添加到 `/etc/vbox/networks.conf`

```bash
echo "10.0.0.0/8" | sudo tee -a /etc/vbox/networks.conf
```

{{< /callout >}}
