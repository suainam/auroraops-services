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
- 角色通过 `apt` 安装 `vim`、`curl`、`git`（Debian/Ubuntu），不假定系统已自带；基础镜像缺少这些包时由本角色补齐。
- 插件管理器 vim-plug 从 `vim_plug_url` 下载 `plug.vim` 到每个受管用户的 `~/.vim/autoload/`，首次在用户下打开 `vim` 执行 `:PlugInstall` 才会拉取插件（需网络出口）。
- 部署系统级 `/etc/vim/vimrc` 与每个受管用户的 `~/.vimrc`，`.vimrc` 归属对应用户；创建用户的角色应在本角色之前完成，否则文件归属错乱。
- 首次部署前会备份既有系统级与用户级 vimrc，基线记录在 `vim_baseline_fact_path`，rollback 按基线恢复。