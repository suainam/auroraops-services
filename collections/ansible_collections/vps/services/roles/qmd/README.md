---
name: AuroraOps QMD Role
description: AuroraOps 项目中 QMD (Quick My Documents) 本地知识库搜索引擎的安装和配置指南。包含变量说明、数据目录管理和故障排查。
keywords: qmd, auroraops, ansible, knowledge-base, search, local, installation, configuration
category: automation
tags: [qmd, auroraops, ansible, knowledge-base, search, 搜索引擎, 安装, 配置]
---

# Role: vps.services.qmd

## 1. 概述
该角色用于安装和配置 QMD (Quick My Documents) - 一个本地知识库搜索引擎。

## 2. 变量说明
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `qmd_enabled` | `true` | 是否启用 qmd 安装。 |
| `qmd_local_dir` | `~/.cache/qmd` | 本地 qmd 数据目录。 |
| `qmd_services_base_dir` | `services_base_dir` 或 `/opt/dockers/services` | 服务根目录；兼容旧 inventory 输入 `services_base_dir`。 |
| `qmd_services_dir` | `{{ qmd_services_base_dir }}/qmd` | 服务符号链接目录。 |
| `qmd_services_user` | `services_user` 或当前用户 | 符号链接属主；兼容旧 inventory 输入 `services_user`。 |
| `qmd_services_group` | `services_group` 或当前用户 | 符号链接属组；兼容旧 inventory 输入 `services_group`。 |
| `qmd_collections` | `[]` | 需要索引的 collection 列表。 |

### qmd_collections 格式
```yaml
qmd_collections:
  - { name: "auroraops", path: "/root/AuroraOps", mask: "*.md" }
  - { name: "docs", path: "/root/docs" }
```

## 3. 内部逻辑
- **Bun 安装**: 使用官方脚本安装 Bun 运行时环境到 `/usr/local/bin`。
- **PATH 配置**: 自动将 `/usr/local/bin` 添加到 `~/.profile`，确保 qmd 命令可用。
- **QMD 安装**: 通过 Bun 全局安装 qmd 包。
- **目录管理**: 创建符号链接 `/opt/dockers/services/qmd` 指向 `~/.cache/qmd`。
- **回滚处理**: 保留用户数据目录，仅移除安装的软件包。

## 4. 依赖关系
- 运行时: Bun (通过脚本安装，安装到 /usr/local/bin)
- 系统包: unzip
- PATH: 自动配置 (添加到 ~/.profile)

## 5. 维护与排查
- **版本检查**: `bun --version` / `qmd --version`
- **PATH 验证**: `echo $PATH` 或 `source ~/.profile && which qmd`
- **数据位置**: `~/.cache/qmd/index.sqlite`
- **符号链接验证**: `ls -la /opt/dockers/services/qmd`
- **回滚说明**: 回滚操作保留用户数据在 `~/.cache/qmd` 目录
