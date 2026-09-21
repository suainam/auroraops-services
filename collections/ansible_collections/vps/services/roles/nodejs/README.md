# Node.js Role

## 1. 概述

本 Role 是一个**包管理器角色**，负责在 Debian 13 系统上：
1. 安装 Node.js 运行时环境
2. 管理全局 npm 包的安装
3. 配置通过 npm 安装的工具 (如 Bitwarden CLI)
4. 管理 Node.js 应用 (OpenCode, OpenClaw)

**架构模式**: 与 `docker_apps` 一致，采用 `nodejs_apps` 列表控制应用的部署和验证。
组件仅在显式加入 `nodejs_apps` 列表后才会被部署/验证。

**Phase**: 3 (Core Services)

## 2. 架构设计

### 2.1 角色定位

```
AuroraOps 包管理器角色体系
├── nodejs        → 管理 npm 包 (bw cli, typescript, etc.)
├── docker_apps   → 管理 Docker 容器 (vaultwarden, redis, etc.)
└── python        → 管理 pip 包 (ansible, etc.)
```

`nodejs` 角色类似于 `docker_apps`，它只负责**安装和基础配置**，不负责业务逻辑。

### 2.2 Vaultwarden 生态依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                    vps.services Collection                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ docker_apps 角色  │                                           │
│  │ (容器管理)        │                                           │
│  │                  │                                           │
│  │ vaultwarden.yml  │ ──→ 部署 Vaultwarden 服务端容器            │
│  │ (phase2)         │     (密码管理服务器)                       │
│  └──────────────────┘                                           │
│           │                                                      │
│           │ 提供服务                                              │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ nodejs 角色       │                                           │
│  │ (npm 包管理)      │                                           │
│  │                  │                                           │
│  │ npm             │ ──→ 安装全局 npm 包 (@bitwarden/cli 等)
│  │ bitwarden       │ ──→ 配置 bw CLI (登录、session)           │
│  │ (phase3)         │                                           │
│  └──────────────────┘                                           │
│           │                                                      │
│           │ 提供 bw 命令                                          │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ plugins/lookup/   │                                           │
│  │ vaultwarden.py   │ ──→ Ansible Lookup 插件                   │
│  │ (collection级别)  │     在 playbook 中获取密码                 │
│  └──────────────────┘                                           │
│           │                                                      │
│           │ 被其他角色使用                                        │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ 其他需要密码的角色 │                                           │
│  │ postgresql, etc. │ ──→ lookup('vps.services.vaultwarden', ..)│
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 部署顺序 (重要!)

| 顺序 | 组件 | Phase | 命令 | 说明 |
|------|------|-------|------|------|
| 1 | Vaultwarden 服务端 | phase2 | `make deploy-services.docker_apps.vaultwarden` | 先部署密码服务器 |
| 2 | Node.js + npm | phase3 | `make deploy-services.nodejs.nodejs_install` | 安装运行时 |
| 3 | npm 包 | phase3 | `make deploy-services.nodejs.npm` | 安装全局 npm 包 |
| 4 | bw 配置登录 | phase3 | `make deploy-services.nodejs.bitwarden_login` | 配置并登录 |
| 5 | 使用 lookup 插件 | phase3+ | 在 playbook 中使用 | 获取密码 |

**一键部署**:
```bash
# 部署完整 nodejs 角色 (包含所有 nodejs_apps 中的应用)
make deploy-services.nodejs

# 或者只部署 bw 相关
make deploy-services.nodejs.npm deploy-services.nodejs.bitwarden_login
```

### 2.4 nodejs_apps 列表管理

与 `docker_apps` 的 `docker_apps_containers` 一致，`nodejs_apps` 控制哪些组件被部署和验证：

```yaml
# inventories/group_vars/all/nodejs.yml - 全局默认
nodejs_apps_global:
  - npm
  - bitwarden

# inventories/host_vars/<host>.yml - 主机扩展
nodejs_apps_host:
  - opencode
  - openclaw
```

最终列表通过 `merge_list_vars.yml` 合并为 `nodejs_apps`，可用 `nodejs_apps_exclude` 排除。

## 3. 变量说明

### 3.1 Node.js 配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_version` | `22.x` | Node.js 主版本号 (NodeSource 格式) |
| `nodejs_install_npm_user` | `root` | npm 全局包安装用户 |
| `nodejs_npm_global_packages` | 见下方 | 全局安装的 npm 包列表 |

### 3.2 Bitwarden CLI 配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_bw_server_url` | `https://bws.msuai.top` | Vaultwarden 服务器地址 |
| `nodejs_bw_session_file` | `{{ ansible_env.HOME \| default('/root') }}/.bw_session` | Session key 存储文件 |
| `nodejs_bw_test_item` | `"AuroraOps/Database/postgresql"` | 用于验证 lookup 的测试项名称 |

### 3.3 Vault 变量 (secrets/vault.yml)

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `vault_vaultwarden_user_name` | 是 | Vaultwarden 登录邮箱 |
| `vault_vaultwarden_password` | 是 | Vaultwarden 主密码 |
| `vault_vaultwarden_client_id` | 2FA时必需 | API Key client_id |
| `vault_vaultwarden_client_secret` | 2FA时必需 | API Key client_secret |

## 4. Sub-Tags

| Sub-Tag | 说明 | 命令 |
|---------|------|------|
| `nodejs_install` | Node.js 安装 (apt) | `make deploy-services.nodejs.nodejs_install` |
| `npm` | npm 配置 + 全局包安装 | `make deploy-services.nodejs.npm` |
| `npm_config` | npm 配置 (镜像源等) | `make deploy-services.nodejs.npm_config` |
| `npm_packages` | 全局 npm 包安装 | `make deploy-services.nodejs.npm_packages` |
| `bitwarden_login` | Bitwarden CLI 登录配置 | `make deploy-services.nodejs.bitwarden_login` |
| `bitwarden_sync` | vault.yml → Vaultwarden 同步 | `make deploy-services.nodejs.bitwarden_sync` |
| `opencode_install` | OpenCode 安装 (官方脚本或 npm) | `make deploy-services.nodejs.opencode_install` |
| `opencode_config` | OpenCode 全局配置部署 | `make deploy-services.nodejs.opencode_config` |
| `opencode_project_config` | OpenCode 项目配置部署 | `make deploy-services.nodejs.opencode_project_config` |
| `opencode_server` | OpenCode Server 服务部署 | `make deploy-services.nodejs.opencode_server` |
| `openclaw` | OpenClaw AI Bot 部署 | `make deploy-services.nodejs.openclaw` |

## 5. Vaultwarden Lookup 插件

### 5.1 插件位置

```
collections/ansible_collections/vps/services/
├── plugins/
│   └── lookup/
│       └── vaultwarden.py   ← Collection 级别的 lookup 插件
└── roles/
    └── nodejs/              ← 负责安装和配置 bw CLI
```

**设计说明**: Lookup 插件放在 collection 的 `plugins/` 目录而非角色内部，因为它是**全局工具**，可被任何角色使用。

### 5.2 使用方法

```yaml
# 获取密码 (默认)
db_password: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/Database/postgresql') }}"

# 获取用户名
db_user: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/Database/postgresql', field='username') }}"

# 获取 TOTP 验证码
totp_code: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/GitHub/2fa', field='totp') }}"

# 获取备注 (Note 类型)
api_token: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/Cloudflare/main', field='notes') }}"

# 获取自定义字段
api_key: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/Service/api', field='api_key') }}"

# 禁用缓存 (每次都从 vault 获取)
secret: "{{ lookup('vps.services.vaultwarden', 'AuroraOps/temp/secret', cache=False) }}"
```

### 5.3 插件参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `field` | str | `password` | 要获取的字段 (password/username/notes/totp/uri) |
| `session_file` | str | `~/.bw_session` | Session 文件路径 |
| `cache` | bool | `True` | 是否启用内存缓存 |
| `cache_timeout` | int | `300` | 缓存超时时间 (秒) |

### 5.4 前置条件

使用 lookup 插件前必须确保：

1. **Vaultwarden 服务端已部署** (或使用外部 Bitwarden 服务)
2. **bw CLI 已安装**: `make deploy-services.nodejs.npm`
3. **bw CLI 已登录**: `make deploy-services.nodejs.bitwarden_login`
4. **Session 已加载**: `source ~/.bw_session` (新 shell 自动加载)

> **注意**: lookup plugin 在**控制节点**执行。若控制节点无 `bw` CLI，verify 中通过远程 `bw get` 测试。

### 5.5 错误处理

```yaml
# 使用 errors='ignore' 避免项目不存在时报错
password: "{{ lookup('vps.services.vaultwarden', 'maybe/not-exist', errors='ignore') | default('fallback') }}"
```

## 6. Vault → Vaultwarden 同步 (bw_sync)

### 6.1 功能说明

`bitwarden_sync` 子任务将 `secrets/vault.yml` 中的密钥同步到 Vaultwarden，实现：
- **约定优于配置**: 通过 `bw_sync_secrets_mapping` 映射表定义同步规则
- **幂等性**: 只创建不存在的项目，已存在的跳过
- **分类管理**: 自动创建 `AuroraOps/<category>/<name>` 结构

### 6.2 映射表配置

映射表位于 `inventories/group_vars/all/bw_sync.yml`:

```yaml
bw_sync_secrets_mapping:
  # Login 类型 (用户名 + 密码)
  - category: "Database"
    name: "postgresql"
    type: "login"
    username_default: "postgres"
    password_var: "postgresql_db_admin_password"

  # Note 类型 (纯文本/token)
  - category: "Cloudflare"
    name: "main"
    type: "note"
    content_var: "certbot_cloudflare_api_token"
```

#### 当前分类清单

| 分类 | 说明 | 示例 |
|------|------|------|
| Database | 数据库凭据 | postgresql, redis |
| Cloudflare | API Token & Account ID | main, small |
| Backup | 备份密码 | rustic |
| Proxy | 代理服务凭据 | hysteria, singbox |
| Service | 应用服务 | flare, cliproxyapi, gcli2api |
| Monitoring | 监控 API Key | health-checks |
| GitHub | GitHub Token | auroraops-pat |
| OpenClaw | AI Bot Gateway | telegram, gemini, zai, openrouter, discord, gateway |
| OpenCode | AI Coding Agent | server-password, context7, landian |
| System | 系统凭据 | root, admin, zerotier |
| Rclone | 云存储 Token | onedrive, gdrive |
| Vaultwarden | bw CLI 自身凭据 | master, api-key |

### 6.3 使用方法

```bash
# Dry-run (检查模式)
make check-services.nodejs.bitwarden_sync

# 实际同步
make deploy-services.nodejs.bitwarden_sync
```

### 6.4 添加新密钥

1. 在 `secrets/vault.yml` 中添加变量
2. 在 `inventories/group_vars/all/bw_sync.yml` 的 `bw_sync_secrets_mapping` 中添加映射
3. 运行 `make deploy-services.nodejs.bitwarden_sync`

#### 变量命名规范

- vault.yml 中的敏感变量统一使用 `vault_` 前缀（如 `vault_openclaw_telegram_token`）
- bw_sync 映射中的 `content_var` / `password_var` 必须与 vault.yml 中的**实际变量名**完全一致
- 添加新服务时，优先归入已有分类；如需新建分类，在 bw_sync.yml 中使用注释分隔块标注

#### 维护 Checklist

当 vault.yml 中的变量**重命名**或**新增**时：

1. 搜索 `bw_sync.yml` 中是否有引用旧名，更新为新名
2. 新增变量需添加对应映射条目
3. 运行 `make deploy-services.nodejs.bitwarden_sync` 验证同步

## 7. Bitwarden CLI 详细配置

### 7.1 认证方式

**方式 1: API Key 登录** (推荐，适用于 2FA 账户)
- 需要在 vault.yml 中配置 `vault_vaultwarden_client_id` 和 `vault_vaultwarden_client_secret`
- 登录后需要用密码解锁 vault

**方式 2: 密码登录** (适用于非 2FA 账户)
- 直接使用邮箱和密码登录
- 登录成功后直接返回 session key

### 7.2 获取 API Key

1. 登录 Vaultwarden Web 界面
2. Settings -> Security -> Keys -> View API Key
3. 复制 `client_id` 和 `client_secret`
4. 添加到 `secrets/vault.yml`:
   ```yaml
   vault_vaultwarden_client_id: "user.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   vault_vaultwarden_client_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```

### 7.3 Session 管理

- Session key 保存在 `~/.bw_session`
- 已自动添加到 `.bashrc`，新 shell 自动加载
- Session 有效期由 Vaultwarden 服务端控制

### 7.4 bw CLI 版本说明

**必须使用 2024.7.2 版本**，原因：
- 新版本 (2025.x+) 的 API 与 Vaultwarden 不兼容
- 会出现 `userDecryptionOptions` 相关错误

## 8. OpenCode 配置

### 8.1 OpenCode 概述

OpenCode 是一个 AI 驱动的代码助手，支持两种模式：
- **CLI 模式**: 交互式终端界面 (TUI)
- **Server 模式**: 无头服务器，通过 HTTP API 访问

### 8.2 安装方式

本角色支持两种安装方式，通过 `nodejs_opencode_install_method` 变量控制：

#### 方式 1: 官方脚本安装 (推荐，默认)

```yaml
nodejs_opencode_install_method: "script"  # 默认值
```

**特点**:
- ✅ 官方推荐方式
- ✅ 自动选择正确的平台二进制
- ✅ 安装到用户目录 (`~/.opencode/bin/opencode`)
- ✅ 自动添加到 PATH (`.bashrc`/`.zshrc`)，新建 `.bashrc` 时权限固定为 `0644`
- ✅ 创建全局符号链接 (`/usr/local/bin/opencode`)
- ⚠️ 需要网络访问 `https://opencode.ai`

**安装位置**:
- 二进制: `~/.opencode/bin/opencode`
- 符号链接: `/usr/local/bin/opencode` (确保在所有环境下可访问)

#### 方式 2: npm 全局包安装 (备选)

```yaml
nodejs_opencode_install_method: "npm"
nodejs_opencode_version: "1.1.56"  # 指定版本
```

**特点**:
- ✅ 使用 npm 包管理器
- ✅ 版本控制更精确
- ✅ 与其他 npm 包统一管理
- ⚠️ 可能选择错误的平台二进制 (如 x64 vs arm64)

**安装位置**: `/usr/local/bin/opencode` (npm global bin)

**选择建议**:
- **VPS/云服务器**: 使用 `script` 方式（默认）
- **容器环境**: 使用 `npm` 方式（便于版本锁定）
- **离线环境**: 使用 `npm` 方式（可预下载包）

### 8.3 安装配置变量

Role 内部和新 inventory 推荐统一使用 `nodejs_*`。历史 `opencode_*` 输入仍由 defaults 单向回退兼容，但不再作为 Role 内部权威。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_opencode_enabled` | `false` | 是否启用 OpenCode 全局配置 |
| `nodejs_opencode_project_enabled` | `false` | 是否启用 OpenCode 项目配置 |
| `nodejs_opencode_install_method` | `script` | 安装方式: `script` 或 `npm` |
| `nodejs_opencode_version` | `1.1.56` | OpenCode 版本 (仅 npm 方式) |
| `nodejs_opencode_install_user` | `root` | 安装用户 |
| `nodejs_opencode_add_to_path` | `true` | 是否添加到 PATH (仅 script 方式) |

### 8.4 配置文件结构

OpenCode 配置采用分层架构，配置文件分布在以下位置：

| 文件位置 | 说明 |
|---------|------|
| `vars/opencode_base.yml` | 基础配置（最小化，只包含必需项） |
| `vars/opencode_providers.yml` | Provider 配置（Google Antigravity 等） |
| `vars/opencode_mcp.yml` | MCP 服务器配置（Context7, gh_grep） |
| `vars/opencode_project.yml` | 项目配置（Agent, Command, Permission） |
| `host_vars/<host>.yml` | 主机个性化配置（Landian API 等） |

**配置合并顺序**:
```
vars/opencode_base.yml
  ↓ 合并
vars/opencode_providers.yml
  ↓ 合并
vars/opencode_mcp.yml
  ↓ 合并
host_vars/<host>.yml (`nodejs_opencode_personal_config`，兼容旧名 `opencode_personal_config`)
  ↓ 部署到
~/.config/opencode/opencode.json (全局配置)

vars/opencode_project.yml
  ↓ 部署到
/root/AuroraOps/.opencode/opencode.json (项目配置)
```

### 8.5 配置变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_opencode_config_dir_root` | `/root/.config/opencode` | root 用户配置目录 |
| `nodejs_opencode_config_dir_admin` | `/home/{{ admin_user }}/.config/opencode` | admin 用户配置目录 |
| `nodejs_opencode_project_dir` | `/root/AuroraOps` | 项目目录 |
| `nodejs_opencode_personal_enabled` | `false` | 是否启用个性化配置；兼容旧名 `opencode_personal_enabled` |
| `nodejs_opencode_personal_config` | `{}` | 个性化配置；兼容旧名 `opencode_personal_config` |

### 8.6 Server 模式配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_opencode_server_enabled` | `false` | 是否启用无头服务器模式 |
| `nodejs_opencode_server_port` | `4096` | 监听端口 |
| `nodejs_opencode_server_hostname` | `127.0.0.1` | 监听地址（安全起见绑定本地） |
| `nodejs_opencode_server_user` | `root` | 运行用户 |
| `nodejs_opencode_server_working_directory` | `/root` | 工作目录 |
| `nodejs_opencode_server_service_name` | `opencode-server` | systemd 服务名称 |
| `nodejs_opencode_server_password` | `""` | Server 访问密码（建议从 vault 获取） |

### 8.7 配置示例

**全局配置** (在 `host_vars/<host>.yml`):
```yaml
# 启用全局配置
nodejs_opencode_enabled: true

# 启用个性化配置（Landian API）
nodejs_opencode_personal_enabled: true
nodejs_opencode_personal_config:
  provider:
    landian:
      npm: "@ai-sdk/openai-compatible"
      name: "Landian API"
      options:
        baseURL: "https://hk2.terminal.pub/v1"
        apiKey: "{{ vault_opencode_landian_api_key }}"
        timeout: 600000
      models:
        claude-sonnet-4-5-20250929:
          name: "Claude 4.5 Sonnet"
          limit:
            context: 200000
            output: 8192
```

**项目配置** (在 `host_vars/<host>.yml`):
```yaml
# 启用项目配置（仅在有 AuroraOps 目录的主机上）
nodejs_opencode_project_enabled: true
```

**Server 模式配置**:
```yaml
nodejs_opencode_server_enabled: true
nodejs_opencode_server_port: 4096
nodejs_opencode_server_hostname: "127.0.0.1"
nodejs_opencode_server_password: "{{ vault_opencode_server_password }}"
```

### 8.8 部署命令

```bash
# 完整部署 OpenCode (安装 + 全局配置 + 项目配置 + Server)
make deploy-services.nodejs.opencode_install \
     deploy-services.nodejs.opencode_config \
     deploy-services.nodejs.opencode_project_config \
     deploy-services.nodejs.opencode_server

# 或者使用简化命令（如果 nodejs_opencode_enabled=true）
make deploy-services.nodejs

# 只安装 OpenCode
make deploy-services.nodejs.opencode_install

# 只部署全局配置
make deploy-services.nodejs.opencode_config

# 只部署项目配置
make deploy-services.nodejs.opencode_project_config

# 只部署 Server 服务
make deploy-services.nodejs.opencode_server

# 验证安装
make verify-services.nodejs

# 检查配置（dry-run）
make check-services.nodejs.opencode_config
```

### 8.9 安装方式切换

**从官方脚本切换到 npm**:
```bash
# 1. 卸载官方脚本安装的版本
make rollback-services.nodejs.opencode_install

# 2. 修改配置
# inventories/host_vars/<host>.yml
nodejs_opencode_install_method: "npm"
nodejs_opencode_version: "1.1.56"

# 3. 重新安装
make deploy-services.nodejs.opencode_install
```

**从 npm 切换到官方脚本**:
```bash
# 1. 卸载 npm 版本
make rollback-services.nodejs.opencode_install

# 2. 修改配置
# inventories/host_vars/<host>.yml
nodejs_opencode_install_method: "script"

# 3. 重新安装
make deploy-services.nodejs.opencode_install
```

### 8.10 OpenCode CLI 使用

```bash
# 启动 TUI 模式
opencode

# 启动 Server 模式 (手动)
opencode serve --port 4096 --hostname 127.0.0.1

# 查看版本
opencode --version

# 查看帮助
opencode --help

# 卸载 OpenCode
opencode uninstall
```

### 8.11 OpenCode Server API

**Health Check**:
```bash
curl http://127.0.0.1:4096/global/health
# 响应: {"healthy":true,"version":"1.1.56"}
```

#### 8.11.1 连接方式

OpenCode Server 支持三种连接方式：

**方式 1: SSH 隧道 + opencode attach (推荐)**

```bash
# 1. 建立 SSH 隧道
ssh -L 4096:127.0.0.1:4096 -N hdy

# 2. 本地连接 (新终端)
opencode attach http://localhost:4096 -p "密码"
```

特点：
- ✅ 最安全（只监听 127.0.0.1）
- ✅ 支持 Terminal TUI 完整功能
- ✅ 支持 WebSocket 交互

**方式 2: Nginx 反向代理 + Basic Auth**

通过域名访问，需要 Basic Auth 认证：

```bash
# 用户名: opencode
# 密码: 从 vault 获取 vault_opencode_server_password
curl -u "opencode:密码" https://opencode.msuai.top/
```

或者浏览器直接访问 `https://opencode.msuai.top`，输入用户名和密码。

特点：
- ✅ 可通过浏览器访问 Web 界面
- ✅ 支持远程访问（无需 SSH 隧道）
- ⚠️ 需要配置 Basic Auth

**方式 3: 直接本地访问**

仅限服务器本地：

```bash
# SSH 登录服务器
ssh hdy

# 直接访问
curl http://127.0.0.1:4096/
# 或
opencode attach http://127.0.0.1:4096 -p "密码"
```

#### 8.11.2 Nginx 反向代理配置

```nginx
location / {
    proxy_pass http://127.0.0.1:4096;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 8.12 Antigravity 插件配置

#### 8.12.1 插件概述

[opencode-antigravity-auth](https://github.com/NoeFabris/opencode-antigravity-auth) 是一个 OpenCode 插件，通过 Google OAuth 认证访问 Antigravity 和 Gemini CLI 配额，支持：

- **Claude Opus 4.5/4.6, Sonnet 4.5** 和 **Gemini 3 Pro/Flash**
- **多账号支持** - 自动轮换，配额耗尽时切换
- **双配额系统** - Antigravity 和 Gemini CLI 配额
- **Thinking 模型** - 支持扩展思考模式
- **自动恢复** - 处理 session 错误和工具失败

**⚠️ 使用风险警告**:
- 使用此插件可能违反 Google 服务条款
- 新账号和 Pro/Ultra 订阅账号有较高封号风险
- 建议使用已建立的 Google 账号

#### 8.12.2 审查总结 (2026-02-11)

**完成的工作**:
1. ✅ 修复 `opencode_providers.yml` YAML 缩进错误（Google provider models 结构）
2. ✅ 统一 localhost 和 cc15 的 Landian 模型配置格式
3. ✅ 添加 Antigravity 插件自动安装支持（`npm install opencode-antigravity-auth@latest`）
4. ✅ 简化 Antigravity 部署流程（移除无效的自动部署模式）

**关键发现**:
- ⚠️ **插件必须手动认证**: 即使通过 Ansible 部署了 `antigravity-accounts.json`，插件仍需要通过 `opencode auth login` 流程来完成初始化
- ⚠️ 这是插件的设计要求，无法通过自动化绕过
- ✅ 因此移除了无效的 `opencode_antigravity_auto_deploy` 变量，只保留手动认证模式

**部署流程（最终方案）**:

**Ansible 自动完成**:
1. 安装 `opencode-antigravity-auth@latest` 插件
2. 配置 `opencode.json`（plugin + models）
3. 显示认证指引

**用户手动完成**（必需）:
```bash
opencode auth login
systemctl restart opencode-server
```

**配置变量**:
```yaml
# defaults/main.yml
nodejs_opencode_antigravity_enabled: false  # 是否启用 Antigravity 插件（默认关闭）
```

**配置合并流程**:
```
vars/opencode_base.yml (plugin 声明)
  ↓ 合并
vars/opencode_providers.yml (Google Antigravity models)
  ↓ 合并
vars/opencode_mcp.yml (MCP 服务器)
  ↓ 合并
host_vars/<host>.yml (nodejs_opencode_personal_config: Landian API)
  ↓ 部署到
~/.config/opencode/opencode.json
```

**验证结果**:
- ✅ localhost: OpenCode server 运行正常，Landian 和 Google Antigravity 模型均可用
- ✅ cc15: OpenCode server 运行正常，Landian 模型可用，Google Antigravity 需手动认证

#### 8.12.3 配置变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `nodejs_opencode_antigravity_enabled` | `false` | 是否启用 Antigravity 插件 |

#### 8.12.4 部署流程

**Ansible 自动完成**:
1. ✅ 安装 `opencode-antigravity-auth@latest` 插件
2. ✅ 配置 `opencode.json`（plugin + models）
3. ✅ 显示认证指引

**用户手动完成**（必需）:
```bash
opencode auth login
```

**重要说明**: 
- ⚠️ 即使通过 Ansible 部署了 `antigravity-accounts.json`，插件仍需要通过 `opencode auth login` 流程来完成初始化
- ⚠️ 这是插件的设计要求，无法通过自动化绕过

**配置示例**:
```yaml
# inventories/host_vars/<host>.yml
nodejs_opencode_antigravity_enabled: true
```

#### 8.12.5 支持的模型

**Antigravity 配额模型**:
| 模型 | Variants | 说明 |
|------|----------|------|
| `antigravity-gemini-3.1-pro` | low, high | Gemini 3.1 Pro；省略 `thinkingLevel` 时由上游动态决定 |
| `antigravity-gemini-3-flash` | minimal, low, medium, high | Gemini 3 Flash with thinking |
| `antigravity-claude-sonnet-4-5` | - | Claude Sonnet 4.5 |
| `antigravity-claude-sonnet-4-5-thinking` | low, max | Claude Sonnet with extended thinking |
| `antigravity-claude-opus-4-5-thinking` | low, max | Claude Opus 4.5 with extended thinking |
| `antigravity-claude-opus-4-6-thinking` | low, max | Claude Opus 4.6 with extended thinking |

**Gemini CLI 配额模型**:
| 模型 | 说明 |
|------|------|
| `gemini-2.5-flash` | Gemini 2.5 Flash |
| `gemini-2.5-pro` | Gemini 2.5 Pro |
| `gemini-3-flash-preview` | Gemini 3 Flash (preview) |
| `gemini-3-pro-preview` | Gemini 3 Pro (preview) |

#### 8.12.6 部署命令

```bash
# 1. 部署 Antigravity 插件
make deploy-services.nodejs.opencode_config \
     deploy-services.nodejs.opencode_antigravity

# 2. SSH 到目标服务器
ssh <host>

# 3. 手动认证（必需步骤）
opencode auth login

# 4. 重启 OpenCode Server
systemctl restart opencode-server

# 5. 验证服务状态
systemctl status opencode-server
journalctl -u opencode-server -n 50
```

#### 8.12.7 手动认证流程

1. **SSH 到目标服务器**:
```bash
ssh <host>
```

2. **运行认证命令**:
```bash
opencode auth login
```

3. **按照提示操作**:
   - 浏览器会自动打开 Google OAuth 页面
   - 登录 Google 账号并授权
   - 返回终端，选择是否配置模型（选择 **No**，因为 Ansible 已配置）

4. **验证认证**:
```bash
# 检查账号文件
cat ~/.config/opencode/antigravity-accounts.json | jq '.accounts[] | {email, enabled}'

# 重启服务
systemctl restart opencode-server

# 检查日志
journalctl -u opencode-server -f
```

5. **多账号设置**（可选）:
```bash
# 再次运行 auth login 添加更多账号
opencode auth login
```

#### 8.12.8 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 主配置 | `~/.config/opencode/opencode.json` | OpenCode 配置（包含 plugin 声明） |
| 账号文件 | `~/.config/opencode/antigravity-accounts.json` | OAuth 账号和 token |
| 插件配置 | `~/.config/opencode/antigravity.json` | 插件配置（可选） |
| 日志目录 | `~/.config/opencode/antigravity-logs/` | 调试日志 |

#### 8.12.9 故障排查

**问题 1: Google API key is missing**

**原因**: 未运行 `opencode auth login` 或插件未正确初始化

**解决**:
```bash
# 1. 检查插件是否安装
ls ~/.config/opencode/node_modules/opencode-antigravity-auth

# 2. 运行认证流程（必需）
opencode auth login

# 3. 重启服务
systemctl restart opencode-server

# 4. 检查日志
journalctl -u opencode-server -n 50
```

**问题 2: 403 Permission Denied (rising-fact-p41fc)**

**原因**: 插件使用默认 project ID，Gemini CLI 模型失败

**解决**:
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或使用现有项目
3. 重新运行 `opencode auth login` 并选择正确的项目

**问题 3: 账号被封禁**

**原因**: Google 检测到异常使用模式

**预防措施**:
- ❌ 不要使用新创建的 Google 账号
- ❌ 不要使用刚订阅 Pro/Ultra 的账号
- ✅ 使用已建立的 Google 账号
- ✅ 避免频繁切换账号
- ✅ 合理控制 API 调用频率

**问题 4: 配额耗尽**

**查看配额**:
```bash
opencode auth login
# 选择 "Check quotas" 选项
```

**配额重置时间**:
- Gemini Flash: 每日重置
- Claude: 每周重置

**解决方案**:
- 添加多个 Google 账号（自动轮换）
- 等待配额重置
- 使用其他 provider（如 Landian）

### 8.13 故障排查

**问题 1: 安装失败 (script 方式)**
```bash
# 检查网络连接
curl -I https://opencode.ai

# 手动安装
curl -fsSL https://opencode.ai/install | bash

# 切换到 npm 方式
# 修改 nodejs_opencode_install_method: "npm"
make deploy-services.nodejs.opencode_install
```

**问题 2: npm 安装选择了错误的二进制**
```bash
# 症状: "Illegal instruction" 错误
# 原因: npm 包选择了不兼容的平台二进制（如 x64 vs arm64）

# 解决方案: 切换到官方脚本安装
# 修改 nodejs_opencode_install_method: "script"
make rollback-services.nodejs.opencode_install
make deploy-services.nodejs.opencode_install
```

**问题 3: OpenCode 命令找不到 (PATH 问题)**
```bash
# 症状: "opencode: command not found"
# 原因: PATH 未正确配置或符号链接缺失

# 解决方案 1: 检查符号链接
ls -la /usr/local/bin/opencode
# 应该指向: /root/.opencode/bin/opencode

# 解决方案 2: 重新部署安装
make deploy-services.nodejs.opencode_install

# 解决方案 3: 手动创建符号链接
sudo ln -sf ~/.opencode/bin/opencode /usr/local/bin/opencode

# 解决方案 4: 临时添加到 PATH
export PATH="$HOME/.opencode/bin:$PATH"
```

**问题 4: Server 服务无法启动**
```bash
# 检查服务状态
systemctl status opencode-server

# 查看日志
journalctl -u opencode-server -n 50

# 手动测试
~/.opencode/bin/opencode serve --port 4096 --hostname 127.0.0.1
```

**问题 5: 版本不一致**
```bash
# 检查当前版本
opencode --version

# npm 方式: 更新到指定版本
# 修改 nodejs_opencode_version: "1.1.56"
make deploy-services.nodejs.opencode_install

# script 方式: 重新安装最新版
make rollback-services.nodejs.opencode_install
make deploy-services.nodejs.opencode_install
```

**问题 6: 项目配置未部署**
```bash
# 确认项目目录存在
ls -la /root/AuroraOps

# 确认配置已启用
# inventories/host_vars/<host>.yml
nodejs_opencode_project_enabled: true

# 重新部署项目配置
make deploy-services.nodejs.opencode_project_config

# 验证配置文件
ls -la /root/AuroraOps/.opencode/opencode.json
```

## 9. npm 全局包配置

```yaml
# 简单格式 (安装最新版)
nodejs_npm_global_packages:
  - "typescript"
  - "yarn"

# 指定版本格式 (推荐)
nodejs_npm_global_packages:
  - {name: "@bitwarden/cli", version: "2024.7.2"}
  - {name: "typescript", version: "5.0.0"}
```

## 10. 依赖关系总结

### 10.1 本角色依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| Debian 12 | 系统 | 仅支持 Debian 12 |
| apt | 系统 | 用于安装 Node.js |
| secrets/vault.yml | 配置 | Vaultwarden 凭据 |

### 10.2 被依赖关系

| 依赖方 | 依赖内容 | 说明 |
|--------|----------|------|
| vps.services.vaultwarden lookup | bw CLI | 需要 bw 命令可用且已登录 |
| 其他需要密码的角色 | lookup 插件 | 通过 lookup 获取密码 |

### 10.3 可选依赖

| 依赖项 | 说明 |
|--------|------|
| `use_domestic_mirrors` | 启用国内 npm 镜像 |
| Vaultwarden 服务端 | 如果使用 lookup 插件 |

## 11. 常用命令

```bash
# === 部署 ===
make deploy-services.nodejs                  # 完整部署
make deploy-services.nodejs.bitwarden_login  # 只配置 bw CLI

# === 验证 ===
make verify-services.nodejs                  # 运行验证任务

# === 手动检查 ===
node -v                                      # Node.js 版本
npm -v                                       # npm 版本
npm list -g --depth=0                        # 全局包列表
bw --version                                 # bw CLI 版本
bw status                                    # bw 登录状态
opencode --version                           # OpenCode 版本

# === bw CLI 使用 ===
source ~/.bw_session                         # 加载 session
bw sync                                      # 同步 vault
bw list items                                # 列出所有项目
bw list items --search "github"              # 搜索项目
bw get password "item-name"                  # 获取密码
bw get totp "item-name"                      # 获取 TOTP

# === 故障排查 ===
cat ~/.bw_session                            # 检查 session 文件
source ~/.bw_session && bw status            # 检查登录状态
make deploy-services.nodejs.bitwarden_login  # 重新登录
```

## 12. 故障排查

### 12.1 bw CLI 登录失败

```bash
# 检查服务器是否可达
curl -I https://bws.msuai.top

# 检查凭据是否正确
ansible-vault view secrets/vault.yml | grep vaultwarden

# 重新部署
make deploy-services.nodejs.bitwarden_login
```

### 12.2 Lookup 插件报错 "No session found"

```bash
# 确保 session 文件存在
ls -la ~/.bw_session

# 加载 session
source ~/.bw_session

# 检查状态
bw status

# 如果 locked，重新部署
make deploy-services.nodejs.bitwarden_login
```

### 12.3 Lookup 插件报错 "Item not found"

```bash
# 检查项目是否存在
source ~/.bw_session
bw list items --search "your-item-name"

# 同步 vault
bw sync
```

## 13. Rollback (回滚)

### 13.1 回滚命令

```bash
# 回滚整个 nodejs 角色
make rollback-services.nodejs

# 回滚 OpenCode Server 服务
make rollback-services.nodejs.nodejs_opencode_server

# 回滚 OpenCode 配置
make rollback-services.nodejs.nodejs_opencode

# 回滚 Bitwarden CLI
make rollback-services.nodejs.bitwarden_login
```

### 13.2 回滚操作说明

**OpenCode 回滚**:
1. 停止并删除 OpenCode Server systemd 服务
2. 使用 `opencode uninstall` 命令卸载 OpenCode
3. 删除全局符号链接 (`/usr/local/bin/opencode`)
4. 删除全局配置目录（`~/.config/opencode`）
5. 删除项目配置目录（`/root/AuroraOps/.opencode`）
6. 从 shell 配置文件中移除 PATH 设置

**Bitwarden CLI 回滚**:
1. 卸载 `@bitwarden/cli` npm 包
2. 删除 session 文件 (`~/.bw_session`)
3. 从 shell 配置文件中移除 BW_SESSION 环境变量

**Node.js 回滚**:
1. 卸载所有全局 npm 包
2. 卸载 Node.js 和 npm
3. 删除 NodeSource 仓库和 GPG key

### 13.3 注意事项

- 回滚操作会删除所有相关配置和数据
- 建议在回滚前备份重要配置
- OpenCode 的 `uninstall` 命令会删除 `~/.opencode` 目录
- 回滚不会影响其他角色的配置

## 14. 验证输出示例

```bash
$ make verify-services.nodejs

# 预期输出:
# [nodejs] Node.js version: v22.x.x
# [nodejs] npm version: 10.x.x
# [nodejs] Installed global npm packages: @bitwarden/cli
# [bw] Bitwarden CLI version: 2024.7.2
# [bw] Bitwarden CLI status: unlocked | Server: https://bws.msuai.top
# [bw] Session file /root/.bw_session: EXISTS
# [bw] Vault access: OK
# [bw] Vaultwarden lookup plugin: OK (retrieved 18 chars)
# [opencode] OpenCode version: 1.1.56
# [opencode] Root config: EXISTS
# [opencode] Admin config: EXISTS
# [opencode-server] Service: opencode-server
# [opencode-server] Status: active
# [opencode-server] Port 4096: LISTENING
```

## 15. OpenClaw AI Bot Gateway 服务
本角色也同时负责 OpenClaw 服务的部署和自定义设定。

### 15.1 个性化代理 (Personas)

- **主代理 (Main Agent)**: `仪玄 (Yixuan)` - 《绝区零》云岿山第十三代掌门风格。
- **子代理 (Sub Agent)**: `艾莲 (Ellen Joe)` - 《绝区零》维多利亚家政鲨鱼女仆风格。

代理配置文件存放于 `/root/.openclaw/agents/` 下对应的子目录，且拥有各自的 `soul.md` 提示词。覆盖 `openclaw.json` 前创建的远端备份会保留原文件权限，避免敏感配置因备份而扩大可读范围。

### 15.2 相关命令

```bash
# 仅部署 OpenClaw 更改（推荐安全操作）：
make deploy-services.nodejs.openclaw
```
