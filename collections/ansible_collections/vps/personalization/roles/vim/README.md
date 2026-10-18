# Vim Role

## 1. 概述
本角色用于安装 Vim 并部署一套经过优化的系统级和用户级 Vim 配置（`.vimrc`）。
同时遵循 `auroraops-stateful-role-template` 生命周期。

## 2. 生命周期
- `preflight.yml`：只读，检查旧 vim 状态，记录基线
- `apply.yml`：只写入，安装 vim，部署 vimrc
- `verify.yml`：验目标状态
- `rollback.yml`：按基线恢复原状

## 3. 变量说明 (Defaults)
本角色目前主要通过模板进行配置，暂无外部默认变量。

## 4. 内部逻辑
- **备份**: 如果存在现有的 `/etc/vim/vimrc`，则将其备份为 `.bak`。
- **安装**: 确保 `vim` 软件包已安装。
- **配置部署**:
  - 将 `vimrc.j2` 模板部署到 `/etc/vim/vimrc` (系统级)。
  - 将 `vimrc.j2` 模板部署到 `/root/.vimrc` (root 用户级)。

## 5. 维护与排查
- 如果 Vim 配置未生效，请检查 `~/.vimrc` 是否覆盖了系统级的配置。
- 检查 `/etc/vim/vimrc` 的读取权限。

## 依赖与边界
- 角色只配置用户级 vimrc 与插件清单，不安装 vim 二进制本身，依赖基础系统已提供 `vim`。
- 插件通过 `vim_plug` 管理器懒加载；首次 `vim` 打开时自动安装缺失插件（需网络出口）。
- 需要在 `zsh` / 用户创建（`user_management`）之后收敛，否则 `~/.vimrc` 归属用户错误。