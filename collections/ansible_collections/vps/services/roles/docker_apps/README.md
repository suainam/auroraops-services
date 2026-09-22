# Role: docker_apps

## 1. 概述
本角色负责部署和管理 VPS 上的 Docker 应用程序。**所有应用现在使用 `container_deployer` Meta 角色进行统一部署**，实现了标准化的容器管理流程。

### 已迁移至 container_deployer 的应用
- **CLIProxyAPI**: 已迁移至 `vps.services.cliproxyapi`，由统一 Role 负责 native/Docker 分支；`docker_apps` 不再拥有其任务。
- ✅ **New API Suite**: API 管理平台 (PostgreSQL + Redis, Compose 模式)
- ✅ **Manifest**: LLM 可观测与评估面板 (PostgreSQL, Compose 模式)
- ✅ **SillyTavern**: AI 聊天前端
- ✅ **Vaultwarden**: 密码管理器
- ✅ **GCLI2API**: Gemini CLI 认证工具
- ✅ **Flare**: 导航面板
- ✅ **Gemini Balance**: Gemini 配额管理
- ✅ **ShellCrash**: OpenClash Shell 工具
- ✅ **Sub-Store**: 私有订阅聚合与 Mihomo/sing-box 格式输出
- ✅ **opcotoai-toolkit**: SMTP Console 与 gateway（旧 Grok 已迁移到独立 `grok_register` Role）
- ✅ **DS2API**: DeepSeek Web API 兼容服务（固定 Release 镜像）
- ✅ **Vertex AI Proxy**: OpenAI-compatible Gemini proxy（本地构建镜像，SSE 入口）

Sub-Store 的 `aurora-singbox` 是幂等 upsert：如果旧版本已经创建了同名
`local` 订阅，后续部署也必须将它 PATCH 为当前 `sub_store_source_url` 的
`remote` Provider。只判断“名称是否存在”会保留旧短 ID/旧节点，造成聚合订阅
与当前 Singbox 服务端不一致。

### Container Deployer 优势
- **代码量减少 44%**: 507行 → 284行
- **统一日志管理**: 所有容器默认 json-file, 5m, 3 files
- **标准化结构**: 统一的部署模式和健康检查；Docker 健康检查间隔统一为 `1800s`
- **易于扩展**: 新增应用只需调用 container_deployer
- **安全配置**: 所有端口绑定 127.0.0.1 (仅本地访问)

## 2. 部署架构

### 2.1 Container Deployer Meta 角色
所有应用通过 `vps.services.container_deployer` Meta 角色部署，支持两种模式：

#### 单容器模式
```yaml
- include_role:
    name: vps.services.container_deployer
  vars:
    cdp_name: "gcli2api"
    cdp_image: "{{ gcli2api_image }}"
    cdp_dirs: ["", "auths", "logs"]
    cdp_networks: [{name: "sweb"}]
    cdp_ports: ["127.0.0.1:{{ docker_apps_app_port_gcli2api_api }}:7861"]
  tags: [deploy, services, docker_apps, gcli2api, phase2]
```

#### Compose 模式
```yaml
- include_role:
    name: vps.services.container_deployer
  vars:
    cdp_name: "newapi-suite"
    cdp_compose_enabled: true
    cdp_compose_template: "newapi_suite_compose.yml.j2"
  tags: [deploy, services, docker_apps, newapi_suite, phase2]
```

#### opcotoai-toolkit 服务边界

`opcotoai-toolkit` Compose 只管理 `gateway` 与 `smtp`。gateway 配置由 AuroraOps 渲染为 SMTP-only，不再引用上游旧 `grok` 服务；独立 `grok-register` 由 `vps.services.grok_register` 管理，并通过宿主 Nginx 的 `/grok/` 路由暴露。

服务边界收缩时显式启用 orphan 清理，但不删除命名卷。若旧容器引用的镜像已丢失，可执行：

```bash
make rollback-services.docker_apps.opcotoai_toolkit
make deploy-services.docker_apps.opcotoai_toolkit
make verify-services.docker_apps.opcotoai_toolkit
```

该 rollback 只移除 Compose 容器和生成的 Compose 文件，保留 `smtp-data` 与 `mail-console-data`。

### 2.2 Phase 标签规范
**重要**: 所有 docker_apps 任务统一使用 `phase2` 标签，与 playbook 保持一致。

```yaml
tags: [deploy, services, docker_apps, {app_name}, phase2]
```

## 3. 变量说明
所有应用的日志级别已统一设置为 **warning/warn**，以减少不必要的日志输出，降低磁盘 I/O 和 CPU 占用：

| 应用 | 日志级别配置 | 配置位置 | 说明 |
|------|-------------|---------|------|
| **SillyTavern** | `minLogLevel: 2` (WARN) | `sillytavern_config.yaml.j2` | 不再打印 INFO 级别的文件同步日志 |
| **Gemini Balance** | `LOG_LEVEL=warning` | `gemini.env` | 减少调度任务和启动信息日志 |
| **Singbox** | `"level": "warn"` | `singbox_config.json.j2` | 不再打印每个连接的详细信息 |
| **GCLI2API** | `LOG_LEVEL: warning` | `main.yml` (环境变量) | 应用级别日志已限制 |
| **CLIProxyAPI** | 默认 | - | 包含 PostgreSQL 支持 (可选) |
| **Vaultwarden** | `LOG_LEVEL=warn` | `vaultwarden.env` | 仅记录警告和错误 |
| **Flare** | 默认 | - | 使用应用默认日志级别 |
| **New API Suite** | 默认 | - | 包含 New API (Master Mode) 和 Neko Tool (Local Build)，支持 PostgreSQL 和 Redis (可选) |
| **Manifest** | 默认 | - | 使用宿主机 PostgreSQL，依赖 `BETTER_AUTH_*` 配置 |

> **注意**: GCLI2API 的 HTTP 服务器访问日志（健康检查日志）由 Web 框架控制，不受 `LOG_LEVEL` 环境变量影响。如需完全禁用，需修改启动命令。

### 日志管理策略
所有应用的日志级别已统一设置为 **warning/warn**，以减少不必要的日志输出，降低磁盘 I/O 和 CPU 占用：

| 应用 | 日志级别配置 | 配置位置 | 说明 |
|------|-------------|---------|------|
| **SillyTavern** | `minLogLevel: 2` (WARN) | `sillytavern_config.yaml.j2` | 不再打印 INFO 级别的文件同步日志 |
| **Gemini Balance** | `LOG_LEVEL=warning` | `gemini.env` | 减少调度任务和启动信息日志 |
| **Singbox** | `"level": "warn"` | `singbox_config.json.j2` | 不再打印每个连接的详细信息 |
| **GCLI2API** | `LOG_LEVEL: warning` | `main.yml` (环境变量) | 应用级别日志已限制 |
| **CLIProxyAPI** | 默认 | - | **PostgreSQL 支持** (可选) |
| **Vaultwarden** | `LOG_LEVEL=warn` | `vaultwarden.env` | 仅记录警告和错误 |
| **Flare** | 默认 | - | 使用应用默认日志级别 |
| **New API Suite** | 默认 | - | **PostgreSQL + Redis 支持** (可选) |
| **Manifest** | 默认 | - | **宿主机 PostgreSQL + Better Auth** |

> **注意**: GCLI2API 的 HTTP 服务器访问日志（健康检查日志）由 Web 框架控制，不受 `LOG_LEVEL` 环境变量影响。如需完全禁用，需修改启动命令。

## 3. 变量说明

Role 内部统一使用 `docker_apps_*` 前缀变量。现有 inventory 中的旧名称仍可使用，并由 `defaults/main.yml` 单向回退到新名称；新配置应优先使用本节列出的前缀名称。Sing-box 与 Vaultwarden 变量暂保持原合同，留待对应 protected scope 专项迁移。

### 基础配置
| 变量名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `backup_source_docker_dir` | string | `/opt/dockers` | Docker 数据存储根目录 |
| `backup_base_dir` | string | `/opt/backups/docker` | 备份文件存储根目录 |
| `docker_apps_docker_user_uid` | string | `1000` | 容器文件所有者 UID；兼容 `docker_user_uid` |
| `docker_apps_docker_user_gid` | string | `1000` | 容器文件所有者 GID；兼容 `docker_user_gid` |
| `gemini_balance_enabled` | bool | `false` | 是否部署 Gemini Balance |

### 应用开关
本角色采用细粒度开关，支持在 `host_vars` 中按需开启或关闭特定应用。

| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `docker_apps_gcli2api_enabled` | `true` | GCLI2API 部署 |
| `docker_apps_ds2api_enabled` | `false` | DS2API 镜像预拉取开关；主机加入容器列表后按需启用 |
| `docker_apps_ds2api_pull` | `false` | DS2API 首次部署或升级时显式开启镜像拉取 |
| `docker_apps_sillytavern_enabled` | `true` | SillyTavern 部署 |
| `docker_apps_vaultwarden_enabled` | `true` | Vaultwarden 部署 |
| `docker_apps_flare_enabled` | `true` | Flare 部署 |
| `docker_apps_singbox_enabled` | `true` | Singbox 核心代理 |
| `docker_apps_sub_store_enabled` | `false` | Sub-Store 相关能力开关；仅在部署主机显式启用 |
| `docker_apps_sub_store_pull` | `false` | Sub-Store 镜像拉取开关；已有本地镜像默认不访问 Docker Hub，首次部署或升级时显式设置为 `true` |
| `cliproxyapi_enabled` | `true` | 统一 CLIProxyAPI Role；`cliproxyapi_deploy_mode` 选择 native 或 Docker |
| `docker_apps_newapi_suite_enabled` | `true` | New API 套件 |
| `docker_apps_gemini_balance_enabled` | `false` | Gemini Balance (需手动启用) |
| `docker_apps_shellcrash_enabled` | `false` | ShellCrash (通常仅 NAS 使用) |


DS2API 的 `docker_apps_ds2api_admin_key` 和 `docker_apps_ds2api_config` 必须来自 Ansible Vault。配置文件只在 `/opt/dockers/ds2api/data/config.json` 不存在时 seed，避免覆盖 WebUI/Admin API 后续修改；容器只绑定宿主回环地址，公网入口由 Nginx 单独管理。

Vertex AI Proxy 通过 `docker_apps_containers_host` 中的 `vertex` 启用，源码包由 `vertex_source_archive` 提供并用 `vertex_source_sha256` 固定。持久化目录为 `/opt/dockers/vertex-proxy/{config,logs,assets}`；`config.json` 与 `api_keys.txt` 仅首次 seed，后续由管理面板维护。管理密码与 API key 必须来自 `vault_vertex_admin_password`、`vault_vertex_api_key`。
### 智能与安全增强 (Advanced)
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `docker_apps_singbox_reality_short_id_count` | `4` | REALITY 自动生成的随机 ID 数量；兼容 `singbox_reality_short_id_count` |
| `docker_apps_singbox_reality_sni_candidates` | (List) | 智能 SNI 候选域名；兼容 `singbox_reality_sni_candidates` |
| `docker_apps_singbox_inbound_listen` | `::` | 公网入站监听地址；兼容 `singbox_inbound_listen` |
| `docker_apps_singbox_certificate_domain` | `msuai.top` | TLS 证书域名；兼容 `singbox_certificate_domain` |
| `docker_apps_country_flags` | (Dict) | ISO 国家代码到 Emoji 国旗的映射表 |
| `docker_apps_warp_memory` | `192m` | WARP 本地 SOCKS 代理容器内存上限 |
| `docker_apps_warp_memory_reservation` | `96m` | WARP 本地 SOCKS 代理容器内存预留 |
| `docker_apps_warp_cpus` | `0.25` | WARP 本地 SOCKS 代理容器 CPU 上限 |

### CLIProxyAPI 认证（由 `vps.services.cliproxyapi` 管理）

`cliproxyapi_api_keys` 必须定义在 Ansible Vault 中，作为完整列表渲染到
CLIProxyAPI 的 `api-keys`；native 与 Docker 分支共用同一组 API key、Provider 和 OAuth
凭据目录。

Provider 配置通过 `cliproxyapi_ai_providers_file` 从独立加密文件载入；认证 JSON 通过
`cliproxyapi_auths_dir` 同步到对应分支的数据目录。已有 Docker 配置只增量重写托管的
Provider/API key/别名区块，保留管理面板写入的其他字段。

完整配置 seed 使用 `cliproxyapi_config_seed_file`，仅首次创建 Docker 配置文件时生效；
native 分支每次部署渲染统一模板。

### 端口配置 (Overridable via group_vars)
建议遵循 `docs/Port_Allocation_Standard.md` 规范。

| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `docker_apps_app_port_newapi` | `30001` | New API HTTP；兼容 `app_port_newapi` |
| `docker_apps_app_port_neko_key_tool` | `30010` | Neko API Key Tool；兼容 `app_port_neko_key_tool` |
| `cliproxyapi_docker_app_port` | `30011` | CLIProxyAPI Docker 分支；native 使用 `cliproxyapi_bind_address` |
| `docker_apps_app_port_manifest` | `30013` | Manifest；兼容 `app_port_manifest` |
| `app_port_sub_store` | `30015` | Sub-Store，仅绑定回环地址 |
| `app_port_sillytavern` | `30002` | SillyTavern WEB UI |
| `app_port_clawbot` | `30003` | Clawbot Gateway |
| `docker_apps_app_port_flare` | `30004` | Flare Dashboard；兼容 `app_port_flare` |
| `docker_apps_app_port_gcli2api_web`| `30005` | GCLI2API Web UI；兼容 `app_port_gcli2api_web` |
| `docker_apps_app_port_gcli2api_api`| `30006` | GCLI2API API；兼容 `app_port_gcli2api_api` |
| `docker_apps_app_port_vaultwarden_http`| `30007` | Vaultwarden HTTP；WebSocket 集成在主端口 |
| `docker_apps_app_port_gemini_balance`| `30009` | Gemini Balance；兼容 `app_port_gemini_balance` |
| `docker_apps_app_port_ds2api` | `30019` | DS2API API/WebUI，仅绑定回环地址 |
| `app_port_vertex` | `30020` | Vertex AI Proxy，仅绑定回环地址 |
| `app_port_singbox_hysteria` | `30051` | Singbox Hysteria2 |
| `app_port_singbox_reality_aws` | `30052` | Singbox VLESS AWS |
| `app_port_singbox_reality_cf` | `30053` | Singbox VLESS CF |
| `app_port_singbox_grpc` | `30054` | Singbox VLESS gRPC |

### 镜像版本控制 (Image Versions)
镜像版本统一声明在 `inventories/group_vars/all/versions.yml`。消费端只引用 `*_image` 变量，不再在执行路径内回退到 `latest`。

| 变量名 | 默认值 |
| :--- | :--- |
| `sillytavern_image` | `ghcr.io/sillytavern/sillytavern:1.17.0` |
| `singbox_image` | `ghcr.io/sagernet/sing-box:v1.13.21` |
| `sub_store_image` | `xream/sub-store:2.36.29` |
| `vaultwarden_version` | `1.37.2` |
| `vaultwarden_registry` | `vaultwarden` |
| `vaultwarden_image` | `{{ vaultwarden_registry }}/server:{{ vaultwarden_version }}` |
| `gcli2api_image` | `ghcr.io/su-kaka/gcli2api:latest` |
| `ds2api_image` | `ghcr.io/ouqiting/ds2api:v3.5.0` | 固定上游 Release；不使用 `latest` |
| `vertex_image` | `vertex-proxy:20260809-0a2df82` | 本地构建标签，与源码包摘要配套 |
| `gemini_balance_image` | `ghcr.io/snailyp/gemini-balance:2.2.8` |
| `cliproxyapi_image` | `eceasy/cli-proxy-api:v7.3.2` |
| `flare_image` | `soulteary/flare:0.5.1` |
| `newapi_image` | `calciumion/new-api:v1.0.0-rc.4` |
| `manifest_image` | `manifestdotbuild/manifest:sha-2b14bc3` |
| `shellcrash_image` | `juewuy/shellcrash:latest` |
GCLI2API 使用可变 `latest` 标签；其 focused deploy 会显式拉取镜像，使同标签的新 digest 能替换运行容器。


### CLIProxyAPI Antigravity 模型目录
模型能力目录由 CLIProxyAPI 官方仓库维护，保存于 `files/cliproxyapi_antigravity_models.json`。更新目录无需手工编辑 YAML：

```bash
make refresh-cliproxyapi-models
```

该命令只更新模型目录，不读取或写入 Vault，也不会自动部署。部署前应检查生成文件的 diff；`auto` 不作为模型别名。直接调用 CLIProxyAPI 时，省略 thinking level 才交给上游默认行为；通过 OMP 调用时，`:auto` 会先由 OMP 在本地解析为具体等级，再发送给 CLIProxyAPI。

#### 思考强度与模型别名

CLIProxyAPI 的 Antigravity 请求同时存在两个相互独立的概念：

- **模型别名**：客户端看到的 `gemini-3.8-flash` 可以由官方目录映射到上游模型名 `gemini-3.8-flash-high`。`-high` 属于模型路由名称，不表示本次请求一定使用 high 思考强度。
- **请求强度**：OpenAI 兼容请求的 `reasoning_effort` 才决定本次请求的思考等级；CLIProxyAPI 会将其映射为 Antigravity 的 `thinkingLevel`。因此必须同时查看日志中的 `model` 和 `level`，不能只根据模型名或 `/v1/models` 判断强度。

在已验证的 OMP v18.2.1 → CLIProxyAPI v7.3.2 链路中，OMP 的 `:auto` 是本地按 prompt 分类的模式，不会保证把字面量 `auto` 透传给上游：

| 请求 | OMP 结果 | CLIProxyAPI debug 日志 | 含义 |
| --- | --- | --- | --- |
| `cliproxy/gemini-3.8-flash:auto` + `hi` | `resolved=low` | `model=gemini-3.8-flash-high ... level=low` | 上游 alias 带 `high`，本次强度仍为 low |
| `cliproxy/gemini-3.8-flash:high` | 显式 high | `model=gemini-3.8-flash-high ... level=high` | 本次强度为 high |

诊断思考强度时，可临时在运行配置中启用 `debug: true`，然后只筛选 `thinking: original config from request` 和 `thinking: processed config to apply` 日志；完成验证后必须恢复 `debug: false` 并确认容器为 healthy。不要把包含请求内容或认证信息的原始 debug 日志复制到聊天、Issue 或提交中。

实现参考：[CLIProxyAPI v7.3.2 配置中的 debug 开关](https://raw.githubusercontent.com/router-for-me/CLIProxyAPI/v7.3.2/config.example.yaml)、[CLIProxyAPI Antigravity 思考参数转换](https://raw.githubusercontent.com/router-for-me/CLIProxyAPI/v7.3.2/internal/translator/antigravity/openai/chat-completions/antigravity_openai_request.go)、[OMP v18.2.1 thinking 解析](https://raw.githubusercontent.com/can1357/oh-my-pi/v18.2.1/packages/coding-agent/src/thinking.ts)。

## 3. 内部逻辑
1.  **数据恢复 (安全无损)**:
    - 从本地或云端中转目录提取备份。
    - **优先策略**: 优先匹配名为 `*_current.tar.gz` 的固定文件名（由 `backup` 角色通过哈希校验生成）。
    - **安全机制**: 使用 `rsync -auvt` (archive + update + verbose + times) 进行增量恢复。
    - **非破坏性**: 仅更新旧文件或添加新文件，**绝不删除**宿主机上已存在但备份中没有的文件（例如用户手动安装的扩展或插件）。
    - **备份源**: 依次尝试恢复 Full Backup (如果存在), Seeds (配置), DB (数据)，确保最终状态是最新的混合体。

2.  **环境准备**: 确保目录结构存在，创建 `sweb` 外部网络。
3.  **应用部署**:
    *   **GCLI2API**: 独立部署，挂载 `creds` 目录。
*   **SillyTavern**:
        - 部署 `config.yaml` 模板。
        - **数据初始化**: 启动时使用 `rsync -au` 从镜像同步默认配置、插件到宿主机。
        - **扩展安装**: 扩展目录 (`extensions/`) 不再从镜像同步。用户需通过 **Web UI → Extensions → Download Extensions & Assets** 手动安装，这样扩展会有 git 仓库，支持后续更新。
        - 配置持久化卷。
        - **代理配置**: SillyTavern 的 `requestProxy` 和容器环境变量 (`http_proxy`/`https_proxy`/`all_proxy`) 仅在 `docker_apps_hysteria2_client_enabled: true` 时启用；旧 `hysteria2_client_enabled` 仍兼容。公网 VPS (如 hdy) 无需代理，局域网主机 (如 NAS) 需要启用 hysteria2-client。
    *   **Vaultwarden**:
        - `vault_vaultwarden_admin_token` 在 `secrets/vault.yml` 中以明文保存。
        - 部署时通过 `command.argv + stdin` 将明文交给远端交互式 `vaultwarden hash`，校验 Argon2id PHC 输出后再写入 `vaultwarden.env`；明文不进入 shell 命令文本或日志。
        - `vault_vaultwarden_smtp_username` / `vault_vaultwarden_smtp_password` 也从 `secrets/vault.yml` 注入。
        - `vaultwarden_version` 是版本唯一权威；主机只覆盖 `vaultwarden_registry`，避免主服务与 standby 镜像版本漂移。
        - 客户端最低版本与验证证据以本 role 的 focused verify 为准；它会读取容器运行版本、确认声明镜像并检查本地 `/alive`。仓库不再维护独立的 compatibility JSON 镜像。
        - Vaultwarden 1.29+ 将 WebSocket 集成到主 HTTP 端口；主容器不再映射旧的独立 3012 端口，Nginx `/notifications/hub` 仍启用 WebSocket 转发。
        - `docker_apps_vaultwarden_pull` 默认 `false`，保持日常部署不访问 registry；版本升级时通过 `ANSIBLE_EXTRA_ARGS='-e docker_apps_vaultwarden_pull=true'` 仅为 Vaultwarden 显式开启拉取。
        - Release 检查、专用 canary 账号和客户端缓存处理以本 role 的 focused verify 输出为准；历史 Compatibility Guide 已不在本仓库维护。
    *   **Singbox**: 整合核心代理服务，支持 VLESS-Reality、Hysteria2、Trojan-WS、AnyTLS 和 TUIC v5。出站集成 Cloudflare WARP Local Proxy (`127.0.0.1:40000`) 解耦 AI 流量（OpenAI / Anthropic / Google），顶层强化 RFC1918/Loopback/CGNAT 私网防御，并对高敏路由实行 Fail-Closed 防漏底。TUIC 启用 `bbr` 拥塞控制、`alpn: h3` 与 `heartbeat: 10s` 保活，gRPC 启用 `idle_timeout: 15s` 与 `ping_timeout: 5s` 保活以消除超时。Reality key 与 short ID 仅在缺失时生成并持久化；Base64 URI 文本由独立模板渲染，YAML/JSON 客户端配置继续使用既有字段合同。低内存 NAT 主机可使用原生 Alpine/OpenRC 模式；原生配置变更通过独立 handler 重启服务；平台判断使用 Ansible facts。定向部署只更新 Singbox 自身，不再隐式执行 Nginx Role；需要调整订阅路由时显式执行 `make deploy-services.nginx.nginx_site_config`。
        - Relay 模式支持通过 `singbox_relay_upstreams` 与 `singbox_extra_nodes` 扩展跨地域中转能力。对于 HK NAT 节点（`nat-hk084`、`nat-hk2d16`），在 `inventories/prod.ini` 中聚合至 `[nat_hk]` 子组，统一由共享配置 owner 路径 `inventories/group_vars/nat_hk.yml` 管理；通过共享开关 `nat_hk_jp_relay_enabled`（`true`/`false`）控制额外节点与上游列表，无需在各单机 `host_vars` 重复声明。端口合同明确遵循：直连出站保留原端口不变（VLESS-Reality TCP `30052`、Hysteria2 UDP `30051`），新增中转端口为 VLESS-Reality TCP `30054` 与 Hysteria2 UDP `30053`，经公网落地到 `nat-jp3` 的 Hysteria2（UDP `30051`）。Make 部署顺序必须遵循“落地优先再到入口”，在 `nat-jp3` 就绪后，再切至 HK 节点执行定向生命周期：`make switch_remote.<host>` → `make check-services.docker_apps.singbox` → `make deploy-services.docker_apps.singbox` → `make verify-services.docker_apps.singbox`（或通过 NAT 统一入口 `make nat-deploy` / `make nat-verify`）。注意：macOS 环境下 `curl --noproxy '*'` 仍会受系统 TUN 虚拟网卡劫持，此前依赖它的测试证据作废；物理直连对照必须显式绑定物理网卡（如 `en0`，`IP_BOUND_IF=25`）或使用隔离 listener，UDP `nc -u` 成功仅代表本地 send 成功，不能作为远端握手依据。
        - NAT provider 的 compact YAML 与完整订阅使用同一节点集合，均包含本机 `singbox_nodes` 及启用的 `singbox_extra_nodes`；因此 HK→JP relay 节点会随 NAT provider 进入 Sub-Store 聚合。
    *   **Sub-Store**: 仅监听 `127.0.0.1:30015`，以现有 Singbox YAML 订阅为单一节点源，幂等创建 `aurora-singbox` 订阅。Mihomo 主链接由完整配置模板提供代理组、DNS 和规则，并通过私有 HTTP `proxy-provider` 动态加载 Sub-Store 转换后的节点；sing-box JSON 继续直接由 Sub-Store 输出。Nginx 只暴露精确订阅后缀，管理 API 和前端不对公网开放。可选 Capability Registry 位于 `/opt/dockers/sub_store/data/capability-registry.json`，由 `sub-store-capability-profiler.service/.timer` 驱动；内置 adapter 为每个节点启动仅监听 loopback 的临时 sing-box 实例，不修改生产 Clash/Mihomo/sing-box 数据面。节点有效观测采用 TTL + hysteresis：连续有效失败可驱逐，adapter/目标基础设施故障不推进节点状态；全量 probe infrastructure failure 保留上一次 registry/LKG 并让 oneshot 失败。能力契约中 `ai` 由 OpenAI/Claude/Gemini 三个独立 API 网络可达事实汇总（401/403 代表域名/API 网络可达，至少 2/3 通过才为 `pass`）；`hk_tw_media` 使用 Bilibili 港澳台区域 API，`international_media` 使用 Netflix full-unlock 代表事实，旧 `bilibili`/`media` capability 保持兼容映射；`low_rtt` 使用 3 次基准探测（至少 2 次成功且 p95 ≤ 250ms）。Provider 清单由 `inventories/group_vars/all/sub_store_providers.yml` 统一管理；该文件可整文件使用 Ansible Vault 加密并随仓库提交。默认 cc15 自有订阅由 inventory 自动注入，外部订阅仅需在清单中新增 `name/url/enabled`，并可选设置 `additional-prefix` 控制节点展示前缀；未设置时回退为 `[name]`。启用 `sub_store_nat_provider_discovery_enabled` 后，`nat_nodes`（可配置为其他 inventory group）中的启用 NAT 会自动叠加到 effective provider catalog；地址、Web 端口和 token 均从 host vars/共享变量读取，退网节点通过 `sub_store_retired_provider_names` 排除，无需手工复制到加密 provider 清单。profiler 会复用同一个 Sub-Store 转换模板逐条读取，无需修改 Python。profiler 每小时只作为增量调度器：先静态剔除无协议、无有效名称和套餐/流量/到期等元数据条目；新节点、配置/名称提示变化立即探测，未变化节点按 `hash(node_id) % 24` 分桶，每 24h 完成一次全量 reconciliation。Pure 的出口/IP 信誉路径只对家宽/住宅/ISP/原生等名称提示候选和 owned 节点执行；IEPL/IPLC/专线等只表示线路质量，不直接作为 Pure 提示。Pure 信誉研判默认每 24h 刷新，首次冷启动、出口 fingerprint 变化或 24h TTL 到期时调用 xykt/IPQuality 多源启发式探测。刷新失败时 Pure 降为 `unknown`，不延用旧 `pass`。`pure` 使用 xykt/IPQuality 核心模型：综合判定 ISP/residential、机房/hosting 标记与代理/威胁特征；原生住宅与非机房判定为 `pass`，机房/数据中心或高危网络判定为 `fail`，信号不完整或网络不可达时保持 `unknown`。该方案不依赖商业 API key。Registry 只持久化白名单 geo/risk/service facts 与出口 IP 的不可逆 fingerprint，不保存 raw IP、token、UUID、password、完整 URI 或响应正文；节点展示前缀由 Provider catalog 的 `additional-prefix` 控制，缺省回退为 `[name]`；Provider 仅作为 provenance 展示，不参与稳定 node identity。
    *   **Sub-Store Capability Pools (#221)**: 直接消费 #220 Registry，不重新联网探测，也不复制节点内容。现有 CC15 Sub-Store 继续负责 Provider 抓取和 ClashMeta 转换；capability profile 通过每个 source subscription 的精确 tokenized provider 路径保留 Provider 边界，并直接复用 #220 catalog 的 `additional-prefix` 做 Mihomo `override.additional-prefix`。同步器把 Registry 选出的 provider-prefixed 节点名编译为 5 个精确 filter，并原子刷新单一完整 profile；用户层统一展示为 `AI 服务`、`快速节点`、`纯净节点`、`B站港澳台`、`国际媒体`。Provider 的订阅名、展示前缀、稳定 `provider-id` 和来源路由彼此解耦；所有 provider source、分组引用和 per-provider filter 都使用稳定 `provider-id`，不再依赖 catalog 的列表序号，调整 Provider 顺序不会把过滤器绑定到别的来源。选择策略按业务语义拆分：各 Provider 内的 `· 稳定` 子组使用 `url-test` 每 60 秒测量延迟，当前节点与该 Provider 内最快节点差距超过 50ms 才切换，探测失败则自动换候选；Provider 之间使用按构造顺序的 stable-first `fallback`，仅在当前 Provider 健康失败后切换。AI/Pure/媒体能力池的自动路径同样是 Provider 间 `fallback`、Provider 内 `url-test`；`快速节点` 仍使用跨普通 Provider 的 latency-first `url-test`。Profile 同时下发 work-mac 迁移后的通用 TUN、DNS/fake-IP、process/path 与规则策略，客户端只需刷新订阅，不需要额外策略脚本；原始 Provider 仍保留为手工 fallback。
    *   **Sub-Store provider groups (#254)**: Provider 的物理 `provider-id`、`additional-prefix` 与可选 `provider-group` 分离；同一逻辑组（如 `hk-nat`）聚合多个物理 source，默认/稳定/Capability 组引用逻辑组，节点仍保留各自 `[hk084]`、`[hk2d16]` 前缀与物理 provenance。
    *   **Sub-Store regional automatic selection**: `⚡ 自动优选` uses hidden, Registry-country-backed pools for 港澳、台湾、日本、新加坡、美国、欧洲（含英国）和其他；each regional pool uses conservative latency testing, while the top-level group fails over by region and does not churn a healthy exit across countries. Service groups separately expose YouTube, verified international media, Spotify, Telegram, GitHub, Microsoft and Apple routing; UDP/443 is rejected to force TCP fallback while other UDP remains direct.
    *   **Sub-Store Capability Pools routing source**: capability profile 的规则维护在 `templates/sub_store_capability_profile/rules.yaml`；Bilibili 专用规则、显式 `bilibili.com -> DIRECT` 与 `bilibili-hmt` 必须位于 `cn-domains`/`GEOIP,CN` 之前。通用 TUN/DNS 配置由 profile 下发（对齐 `work-mac.yaml` 拓扑体系，包含 DoH fallback，以及针对 `geosite:cn`、tunnel 隧道域名与 `sub_store_capability_private_fake_ip_filter` 列表内私有域名的 `nameserver-policy` 国内 DNS 锁固）；敏感公司域名、固定排除 IP 和内网 Fake-IP 过滤规则全部通过 `vault_sub_store_capability_private_*` 加密存储并注入，公开 Inventory 无任何隐私泄露，且严格遵守 Fail-Closed 契约。
    *   **New API Suite**:
        -   整合了 New API 和 Neko API Key Tool (查询工具)。
        -   使用 Docker Compose 进行原子化管理。
        -   **New API**: 运行在 **Master Node** 模式 (`NODE_TYPE: "master"`)，作为主节点服务。
        -   **Neko API Key Tool**: 采用 **本地构建模式 (Local Build)**。每次部署时会拉取 GitHub `main` 分支的最新源码并在本地构建 Docker 镜像，以确保前端资源始终为最新版。
        -   支持 SQLite (默认) 或 PostgreSQL (推荐)。
        -   支持 Redis 缓存 (推荐)。
        -   自动创建 PostgreSQL 数据库 (需启用 `vps.applications.postgresql`)。
    *   **Manifest**:
        -   使用 Docker Compose 部署单服务 `manifest` 容器。
        -   复用宿主机 PostgreSQL，不启动 Compose 内置 `postgres` 服务。
        -   认证配置使用 `docker_apps_manifest_auth_secret` 与 `docker_apps_manifest_auth_url`。
        -   复用宿主机 PostgreSQL，数据库密码来自 `postgresql_db_admin_password`。
        -   支持单项回滚: `make rollback-services.docker_apps.manifest`。
    *   **其他应用**: Vaultwarden, Gemini, Flare 的标准容器部署。

## 3.1 Singbox 订阅系统

定向生命周期入口保持为：

```bash
make check-services.docker_apps.singbox
make deploy-services.docker_apps.singbox
make verify-services.docker_apps.singbox
```

该入口只选择 Singbox、容器列表合并和公共 Docker Apps setup，不执行其他应用或 Nginx。`singbox` tag 负责静态任务选择，`docker_apps_target=singbox` 提供运行时防御性过滤。

### 节点配置
Singbox 支持以下协议和传输方式：

| 协议 | 传输 | 端口 | 特性 |
|------|------|------|------|
| VLESS | TCP | 30052, 30053 | Reality + Vision |
| VLESS | gRPC | 30054 | Reality + gRPC 伪装 |
| Hysteria2 | UDP | 30051 | Salamander 混淆 |
| Trojan | WS | 30056 | Nginx WebSocket 复用 (CDN 友好) |

#### Nginx Multiplexing (Trojan 回退机制)
为避免在 VPS 防火墙暴露非标准大号端口，我们引入了 `trojan-fallback` 层：
1. **隐藏端口**: Trojan 服务监听在 `127.0.0.1:30056`。
2. **CDN 友好穿透**: 采用 WebSocket 作为传输层，通过 `handclap6764.suai.eu.org` 的 Nginx Server Block 接收公网 443 HTTPS 流量。
3. **精准路由**: Nginx 解密 TLS 后，基于特定的无意义路径变量 (`singbox_trojan_path: "/cleft5-trimester-affected"`)，通过 `Upgrade: websocket` 无缝转发到 Sing-box 内核的 Trojan 端口。

### 订阅格式
自动生成两种订阅格式：

1. **Base64 URI 订阅** (`/x9a8b7c6d5e4f3`)
   - 适用客户端: v2rayNG, Shadowrocket
   - 托管: Nginx (Port 443)

2. **JSON 订阅** (`/x9a8b7c6d5e4f3.json`)
   - 适用客户端: Hiddify, sing-box
   - 托管: Nginx (Port 443)

### 端口跳跃支持
服务端已配置 iptables DNAT 规则支持端口跳跃（30100-30200 → 30051），但客户端支持有限：

| 客户端 | 版本 | 支持状态 |
|--------|------|---------|
| v2rayNG | 2.0.2 + xray-core v26.1.13 | ❌ URI 解析器不支持 |
| Hiddify | 2.0.5 (sing-box < 1.11.0) | ❌ 不支持 `server_ports` |
| sing-box | 1.11.0+ | ✅ 支持 `server_ports` |

当前配置使用单端口以确保最大兼容性，待客户端升级后可启用 `hopping_range` 变量。

Alpine/native 部署会先检查 `sing-box` 与 `sing-box-openrc` 是否已安装；只有缺包时
才刷新 apk index。这样小配置变更不会因 NAT 包源短暂不可达而阻断服务重启，新节点
首次安装仍会自动更新索引。
如果 OpenRC 在一次中断的重启后留下 `starting` 标记且进程已不存在，角色会在启动前
清理这个 stale 状态，避免后续一键部署误判服务已启动。

### NAT Hysteria2 多端口回退

受限 NAT 主机可在 `nat_singbox_hysteria_fallback_ports` 中声明额外 UDP
端口。角色会在一次 sing-box 部署中复制主 Hysteria2 节点的凭据、混淆和
TLS 参数，为每个端口创建备用入站和订阅节点；默认值为空，不影响普通主机。
客户端的自动延迟/稳定代理组可在主端口不可用时选择备用节点。该机制不是
端口 hopping，也不改变主端口；供应商仍必须逐个配置公网 UDP 到同号内部端口。

### 故障修复历史
- ✅ 修复 DNS 配置警告（添加 `route.default_domain_resolver`）
- ✅ 修复订阅换行符问题（Jinja2 空白控制）
- ✅ 修复 vless-grpc URI 参数错误（移除 flow，添加 serviceName）
- ✅ 测试并兼容 Hysteria2 端口跳跃（暂时禁用以确保兼容性）
- ✅ **[2026-01-29]** 改造 YAML 订阅为 mihomo (Clash Meta) 格式，支持代理组和路由规则
- ✅ **[2026-01-29]** 修复外部节点 `sni` 字段缺失导致的模板渲染错误
- ✅ **[2026-01-29]** 修复 dry-run 模式下 systemd 检查失败问题
- ✅ **[2026-02-01]** 修复 HDY 主机 IPv6 连接失败问题（主机无 IPv6，禁用 Singbox IPv6 监听）
- ✅ **[2026-02-02]** 修复 sing-box 1.12.0+ `domain_strategy` 弃用警告
- ✅ **[2026-02-07]** 实现 **智能国旗系统**：部署时根据 GeoIP 自动为节点补全归属地 Emoji 图标
- ✅ **[2026-02-07]** 实现 **REALITY 安全加固**：支持 Short ID 随机化、持久化存储以及智能 SNI 域名伪装
- ✅ **[2026-02-07]** 引入 **细粒度应用开关**：支持 `docker_apps_<app>_enabled` 变量控制，防止误安装
- ✅ **[2026-02-07]** 修复 Hysteria2 URI 格式：纠正 `obfs-password` 及 YAML 布尔值兼容性问题
- ✅ **[2026-02-07]** 新增 **MTU 自动探测**：自动获取服务器到公网的路径 MTU，为性能调优做准备（移除 outbound 中的 `domain_strategy` 配置，参考官方迁移文档）
- ✅ **[2026-02-08]** 修复 Hysteria2 测速失败：移除带宽限制(`up_mbps`/`down_mbps`)和`ignore_client_bandwidth`，统一使用 IPv4 监听(`0.0.0.0`)，避免与客户端协商失败
- ✅ **[2026-02-08]** **移除 Cloudflare Optimizer**：该功能设计存在根本性错误，会导致 DNS 回环（Error 1000），已彻底删除相关代码（见下方警告）
- ✅ **[2026-02-27]** **分流架构重构 (cc15)**：实现 Nginx (443) 负责伪装与订阅，Sing-box (8443) 负责多协议共享，彻底解决 `fallback` 兼容性问题
- ✅ **[2026-02-27]** **精品化伪装站**: 升级至 Glassmorphism 响应式前端，提升反探测能力
- ✅ **[2026-02-27]** **路由阻断增强**: 正式启用 BT/测速/广告/CN 域名的全量阻断与审计逻辑
- ✅ **[2026-02-28]** **Sing-box 1.12+ 深度迁移**:
    - ⚠️ **移除废弃字段**: 删除了 `dns.json.j2` 和 `route_*.json.j2` 中的 `download_detour` 及废弃的手动 DNS 重定向规则，解决 `detour to an empty direct outbound` 致命错误。
    - ⚠️ **重定向解析逻辑**: 强制引入 `route.default_domain_resolver` 并要求远程节点（如 `public-relay-fallback`）显式配置 `domain_resolver: "cf-dns"`，解决 1.12+ 警告并确保 IP 拨号前的域名解析健壮性。
    - 🛡️ **安全加固**: 标签 `direct` 统一重命名为 `direct-out`，避免与引擎内部保留词冲突导致解析逻辑异常。
    - ⚡ **跨节点连通性**: 正式开启 `cc15` 的 `40052` (ZeroTier Relay) 防火墙端口，确保 `hdy` 分流节点可稳定握手。
- ✅ **[2026-04-12]** **V2RayNG 连接 Hysteria2 失败 (io: read/write on closed pipe)**:
    - **问题现象**: V2RayNG 2.0.x 连接 hysteria2 节点失败，日志显示 `io: read/write on closed pipe`
    - **根本原因**: V2RayNG 使用的 xray 内核与 Hysteria2 协议存在兼容性问题（2025年中旬某版本更新导致）
    - **解决方案**: 升级 V2RayNG 到 2.0.18 或使用 sing-box 内核
    - **参考**: [GitHub Issue #8933](https://github.com/2dust/v2rayN/issues/8933)

### 2026-02-08 vless-cf-best Cloudflare gRPC 522 问题排查

**问题描述**：
- ✅ vless-grpc 正常工作（直接连接）
- ✅ vless-cf-best 关闭云朵能工作
- ❌ vless-cf-best 开启云朵报 522 错误

**排查过程**：

| 步骤 | 检查项 | 结果 |
|------|--------|------|
| 1 | DNS A 记录 | 指向真实服务器 IP ✅ |
| 2 | Nginx 443 监听 | 正常监听 ✅ |
| 3 | TLS 版本 | 调整为 TLS 1.2+ ✅ |
| 4 | gRPC 路径 | Hiddify 发送 `/TunService/Tun` |
| 5 | serviceName 配置 | vless-cf-best: `TunService`, vless-grpc: `""` |
| 6 | Cloudflare gRPC 开关 | 开启 ✅ |

**根本原因**：
Cloudflare CDN 与源服务器之间的 gRPC 连接不稳定，可能原因：
1. Cloudflare gRPC 代理层存在 Bug 或限制
2. 网络路由问题
3. Cloudflare 安全功能（如 Bot Fight Mode）误拦截

**服务端验证**：
关闭云朵后，gRPC 连接完全正常（`POST /TunService/Tun HTTP/2.0" 200`），证明服务器链路无问题。

**客户端差异**：
- **Hiddify**: 强制发送 `serviceName=TunService`（路径 `/TunService/Tun`）
- **v2rayNG**: 发送空 serviceName（路径 `/`）

**解决方案**：
1. **主力使用 vless-grpc**：直接连接，稳定可靠
2. **保留 vless-cf-best 配置**：以备 Cloudflare 未来修复 gRPC 问题
3. **如需使用 Cloudflare CDN**：可考虑使用 vless-WS+TLS+CDN 方案（gRPC 在 Cloudflare 表现不稳定）

**服务端配置**：
```yaml
# vless-cf-best (Cloudflare CDN)
- name: "☁️ vless-cf-best"
  type: "vless"
  transport: "grpc"
  service_name: "TunService"
  behind_nginx: true

# vless-grpc (直接连接)
- name: "🇺🇸 vless-grpc"
  type: "vless"
  transport: "grpc"
  service_name: ""  # 空字符串，客户端使用默认 /
```

**参考**：[Cloudflare gRPC 官方文档](https://developers.cloudflare.com/network/grpc-connections/)

---

### ⚠️ Cloudflare Optimizer 已移除（重要警告）

**问题背景**：
原 `singbox_optimizer.yml` 和 `singbox_optimizer.sh.j2` 试图通过 CloudflareSpeedTest 自动更新 DNS A 记录，使用最快的 Cloudflare CDN IP。

**设计错误**：
```
错误逻辑：
CloudflareSpeedTest 找到最快的 CDN IP (如 104.21.x.x) 
    ↓
直接填到 DNS A 记录 (proxied=false)
    ↓
客户端直接连接 104.21.x.x 
    ↓
❌ Cloudflare 错误 1000：DNS points to prohibited IP
```

**正确做法**：
```
正确逻辑：
DNS A 记录始终指向真实服务器 IP (如 38.76.195.215)
    ↓
Cloudflare 代理开启 (orange cloud)
    ↓
客户端通过 Cloudflare 任播网络连接
    ↓
✅ 正常访问
```

**已删除文件**：
- `tasks/singbox_optimizer.yml`
- `templates/singbox_optimizer.sh.j2`

**兼容变量**：
- Role 内部使用 `docker_apps_singbox_optimizer_subdomain`；旧 `singbox_optimizer_subdomain` 仍作为 inventory 输入回退，实际用于 vless-cf-best 节点配置。

**如果之前启用过 Optimizer**：
1. 立即检查 DNS A 记录是否指向真实服务器 IP
2. 确保 Cloudflare 代理为**开启**状态（橙色云朵）
3. 清除本地 crontab：`crontab -e` 删除 optimizer 定时任务

### 2026-02-01 HDY IPv6 问题修复

**问题描述**: Singbox 容器尝试连接 IPv6 地址 `2001:b28:f23f:f005::a:443`，但服务器不支持 IPv6，导致大量 `network is unreachable` 错误。

**问题现象**:
```
ERROR [xxx] connection: open connection to [2001:b28:f23f:f005::a]:443 using outbound/direct[direct]: dial tcp [2001:b28:f23f:f005::a]:443: connect: network is unreachable
```

**解决方案**:
1. Role 内部权威为 `docker_apps_singbox_inbound_listen`，默认值为 `::`；
2. Sing-box 入站模板统一消费该 prefixed 变量；
3. `host_vars/hdy.yml` 仍可使用旧输入 `singbox_inbound_listen: "0.0.0.0"`，由 defaults 单向兼容到内部权威。

**验证方法**:
```bash
# 确认 Singbox 只监听 IPv4
docker exec singbox cat /etc/sing-box/config.json | jq '.inbounds[0].listen'
# 应输出: "0.0.0.0"
```

详细技术总结见: `docs/Retrospectives/Singbox_Subscription_Fix_Summary.md`

### 2026-02-02 sing-box 1.12.0+ 配置兼容性修复

**问题描述**: 升级到 sing-box v1.12.17 后，日志出现以下警告和错误：
```
WARN[0000] legacy domain strategy options is deprecated in sing-box 1.12.0 and will be removed in sing-box 1.14.0
FATAL[0000] decode config at /etc/sing-box/config.json: outbounds[0].bind4: json: unknown field "bind4"
```

**原因分析**: 
1. sing-box 1.12.0 移除了 outbound 中的 `domain_strategy` 字段（现在使用 `domain_resolver` 替代）
2. 之前配置的 `domain_strategy: ipv4_only` 在 outbound 中已弃用

**解决方案**:
1. 从 `singbox_config.json.j2` 模板中移除 `outbounds[*].domain_strategy` 配置
2. 对于简单服务端配置，无需替代方案（不依赖特定 DNS 策略）
3. 如需强制 IPv4，可继续通过 `host_vars` 中的旧输入 `singbox_inbound_listen: "0.0.0.0"` 实现；Role 内部会映射为 `docker_apps_singbox_inbound_listen`

**官方迁移文档**:
- 迁移指南: https://sing-box.sagernet.org/migration/#migrate-outbound-domain-strategy-option-to-domain-resolver
- 关键变更: `domain_strategy` 在 Dial Fields 中已弃用，应使用 `domain_resolver` 替代
- 仅在需要特定出站 DNS 策略时使用 `domain_resolver`，简单服务端配置可直接移除

**验证方法**:
```bash
# 检查配置是否包含弃用字段
docker exec singbox cat /etc/sing-box/config.json | jq '.outbounds[].domain_strategy'
# 应输出: null（无该字段）

# 检查日志是否有弃用警告
docker logs singbox 2>&1 | grep "domain strategy" | head -5
# 应无输出
```

## 3.2 New API 高级配置
New API 支持使用宿主机的 PostgreSQL 和 Redis 以提升性能。

### 运行模式说明
*   **New API**: 强制配置为 `NODE_TYPE: "master"`。这意味着它是一个独立的主控节点，不依赖其他节点。
*   **Neko API Key Tool**: 配置为 **源码构建**。部署脚本会自动 Clone 官方仓库的 `main` 分支到 `/opt/dockers/neko-api-key-tool-src` 并构建镜像 `neko-api-key-tool:local`。

### 启用外部数据库/缓存
在 `inventories/group_vars/all.yml` 中配置：
```yaml
docker_apps_newapi_use_postgres: true
docker_apps_newapi_use_redis: true

# 如果使用 vps.applications.postgresql 的默认配置，以下无需修改：
# docker_apps_newapi_pg_host: "host.docker.internal"
# docker_apps_newapi_pg_port: 5432
# docker_apps_newapi_pg_db: "new_api"
# docker_apps_newapi_pg_user: "admin"

# 如果使用 vps.applications.redis 的默认配置，以下无需修改：
# docker_apps_newapi_redis_host: "host.docker.internal"
# docker_apps_newapi_redis_port: 6379
```

> **重要前提**: 必须在 `secrets/vault.yml` 中定义 `postgresql_db_admin_password` 和 `redis_db_admin_password`，因为 New API 将直接使用这些凭据连接宿主机服务。

## 4. 依赖关系
*   `vps.services.docker`: 必须先安装 Docker 引擎及相关组件。

## 5. 维护与排查
*   **查看日志**: `docker logs <container_name>`
*   **验证状态**: `make verify-services.docker_apps`
*   **配置文件**: 所有配置文件位于 `/opt/dockers/<app_name>/`

### SillyTavern 定时恢复

SillyTavern 当前只启用每日 21:00 的 `docker start` timer；停止 timer
仍部署对应 systemd unit，但明确保持 disabled/stopped，不会在 23:00 自动停止容器。
通用 cleanup 不得删除 stopped container 或 volume。若容器确实缺失，start
service 会明确失败；使用 `make deploy-services.docker_apps.sillytavern`
重新创建容器。`/opt/dockers/sillytavern/` 下的 config、data、plugins 和
extensions 均为 bind mount，重新部署不得删除这些目录。
已有 bind 目录不会从镜像同步覆盖；已有 `config/config.yaml` 也默认保留。
只有明确设置 `sillytavern_config_force: true` 才会重渲染该配置文件。

不要用 `make rollback-services.docker_apps.sillytavern` 回滚 cleanup 代码，
该命令的既有语义是移除容器。cleanup 代码回滚应使用
`make rollback-operations_loop.cleanup`。

### 日志级别调整
如遇到问题需要启用详细日志进行调试：

**临时调整（容器重启后失效）**:
```bash
# SillyTavern - 修改容器内配置文件
docker exec sillytavern sed -i 's/minLogLevel: 2/minLogLevel: 0/' /home/node/app/config/config.yaml
docker restart sillytavern

# Gemini Balance - 重新部署并设置环境变量
docker stop gemini-balance && docker rm gemini-balance
# 手动运行容器，添加 -e LOG_LEVEL=debug

# Singbox - 修改配置并重启
docker exec singbox sed -i 's/"level": "warn"/"level": "debug"/' /etc/sing-box/config.json
docker restart singbox
```

**永久调整（推荐）**:
1. 修改对应的配置文件或模板
2. 重新部署: `make deploy-services.docker_apps.<app_name>`
3. 问题解决后，记得恢复为 warning 级别以节省资源

### 应用更新 (Update Strategy)
本角色支持通过修改变量来实现**稳健更新**：

1.  **锁定版本**: 在 `inventories/group_vars/all.yml` 或 `host_vars` 中定义具体版本号（推荐）。
    ```yaml
    sillytavern_image: "ghcr.io/sillytavern/sillytavern:1.12.0"
    ```
2.  **执行更新**: 运行部署命令，Ansible 会自动检测镜像变更并重新创建容器。
    ```bash
    make deploy-services.docker_apps.sillytavern
    ```
3.  **验证**:
    - 容器内置了 `healthcheck`，部署后可使用 `docker ps` 查看健康状态 (healthy/unhealthy)。
    - 如果新版本启动失败，请立即回滚变量版本号并重新部署。

### Singbox 专项排查
*   **订阅可用性测试**: `curl -s https://域名/x9a8b7c6d5e4f3 | base64 -d | nl`
*   **JSON 配置验证**: `curl -s https://域名/x9a8b7c6d5e4f3.json | jq .`
*   **端口监听检查**: `ss -tulpn | grep -E "30051|30052|30053|30054"`
*   **防火墙规则**: `ufw status | grep -E "30051|30052|30053|30054"`
*   **iptables DNAT**: `iptables -t nat -L PREROUTING -nvx | grep 30051`

#### Hysteria2 测速失败排查 (重要)

**故障现象**:
- 客户端测速显示 `io: read/write on closed pipe`
- 连接立即断开，无数据传输
- sing-box 服务端日志无错误（或仅显示正常连接建立）

**根本原因**:
在 sing-box 1.12+ 版本中，服务端配置 `up_mbps`/`down_mbps` 带宽限制会导致与某些客户端（如 v2rayNG, Hiddify）的带宽协商失败，连接被立即关闭。

**官方文档参考**:
- [Hysteria2 Inbound Configuration](https://sing-box.sagernet.org/configuration/inbound/hysteria2/)
- [Hysteria2 up_mbps/down_mbps](https://sing-box.sagernet.org/configuration/inbound/hysteria2/#up_mbps-down_mbps): 当设置带宽限制时，会使用 Hysteria CC；不设置时客户端使用 BBR CC
- [ignore_client_bandwidth](https://sing-box.sagernet.org/configuration/inbound/hysteria2/#ignore_client_bandwidth): 当设置了 `up_mbps`/`down_mbps` 时，此选项会阻止客户端使用 BBR CC

**测试验证流程 (2026-02-08)**:

| 步骤 | 配置 | 监听 | ignore_client_bandwidth | up/down_mbps | 测试结果 |
|-----|------|------|------------------------|--------------|---------|
| 1 | 基准配置 | `::` | ❌ 无 | ❌ 无 | ✅ **正常** |
| 2 | 添加 ignore | `::` | ✅ 有 | ❌ 无 | ✅ **正常** |
| 3 | 添加带宽限制 | `::` | ✅ 有 | ✅ 48/48 | ❌ **失败** |

**结论**: 带宽限制参数 `up_mbps`/`down_mbps` 是导致测速失败的根本原因。当服务端设置带宽限制而客户端未配置对应参数时，sing-box 1.12+ 的 CC 算法协商失败，导致连接被关闭。

**正确配置示例**:
```json
{
  "type": "hysteria2",
  "tag": "hysteria-in",
  "listen": "::",
  "listen_port": 30051,
  "users": [{"password": "your-password"}],
  "obfs": {
    "type": "salamander",
    "password": "obfs-password"
  },
  "tls": {
    "enabled": true,
    "alpn": ["h3"],
    "certificate_path": "...",
    "key_path": "..."
  }
}
```

**关键要点**:
1. ❌ **不要设置** `up_mbps`/`down_mbps`（除非你知道客户端支持且订阅链接能正确传递带宽参数）
2. ❌ **不要设置** `ignore_client_bandwidth`（除非配合无带宽限制使用）
3. ✅ 监听地址使用 `::`（IPv4/IPv6 双栈）或 `0.0.0.0`（仅 IPv4）均可
4. ✅ 客户端订阅链接中不应包含 `up`/`down` 参数（标准 hysteria2 URI 格式不支持）

**验证配置**:
```bash
# 检查服务端配置是否包含带宽限制
docker exec singbox cat /etc/sing-box/config.json | jq '.inbounds[] | select(.type == "hysteria2") | {up_mbps, down_mbps, ignore_client_bandwidth}'

# 预期输出（无带宽限制）
{
  "up_mbps": null,
  "down_mbps": null,
  "ignore_client_bandwidth": null
}

# 检查订阅链接是否包含带宽参数
curl -s https://your-domain/x9a8b7c6d5e4f3 | base64 -d | grep hysteria2

# 预期输出（无 up/down 参数）
# hysteria2://password@host:30051?insecure=1&sni=bing.com&alpn=h3&obfs=salamander&obfs-password=xxx#hysteria-bing
```

### 订阅 Token 变更操作指南
当前实现中，`make deploy-services.docker_apps.sub_store` 会在 Provider catalog/profile 部署成功后自动补跑 `make deploy-services.nginx.nginx_site_config`，确保订阅入口与最新聚合结果一致。`singbox` 定向部署仍只更新 Singbox；如果只是 Singbox 订阅文件或 Token 变化，请显式执行 Nginx focused target。

如果历史环境已经出现“新订阅文件已生成，但 Nginx 仍指向旧 Token”的状态，可按顺序执行以下操作修复：

1.  **更新 Docker 应用** (生成新的订阅文件):
    ```bash
    make deploy-services.docker_apps.sub_store
    ```
2.  **更新 Nginx 配置** (指向新的订阅路径):
    ```bash
    # 使用轻量级部署，仅更新站点配置，不重装 Nginx/Certbot
    make deploy-services.nginx.nginx_site_config
    ```

## 6. 相关文档
* Singbox 订阅生命周期、Nginx 刷新和验证步骤以本 README 的 `## 3.1 Singbox 订阅系统` 章节为唯一来源；历史 Wiki/Retrospectives 页面已不在本仓库维护。

## 7. 数据库恢复指南

### 7.1 使用 Rustic 恢复数据库 (推荐)

AuroraOps 现已采用基于 Rustic 的块级去重备份方案。所有数据库备份均包含在完整系统备份中。

#### 恢复前准备
```bash
# 1. 获取数据库密码
ansible-vault view secrets/vault.yml | grep -E "postgresql_db_admin_password|redis_db_admin_password"

# 2. 停止依赖数据库的容器
docker stop new-api cliproxyapi
```

#### 自动恢复流程 (推荐)

使用 Ansible playbook 自动从 Rustic 快照恢复数据库:

```bash
# 恢复 PostgreSQL 和 Redis
ansible-playbook -i inventories/prod.ini playbooks/operations_loop.yml \
  --tags rustic_restore \
  -e "rustic_restore_mode=true" \
  -e "rustic_restore_source=onedrive" \
  -e "rustic_restore_target_dir=/tmp/rustic_restore" \
  -e "rustic_restore_databases=true"
```

**工作流程**:
1. 从 OneDrive Rustic 仓库恢复最新快照到 `/tmp/rustic_restore`
2. 自动查找 PostgreSQL SQL 备份 (`/tmp/rustic_restore/tmp/postgresql_all_dbs.sql`)
3. 自动导入 PostgreSQL 数据库
4. 自动查找 Redis RDB 文件 (`/tmp/rustic_restore/var/lib/redis/dump.rdb`)
5. 停止 Redis → 覆盖 RDB 文件 → 启动 Redis

#### 手动恢复流程

**步骤 1: 从 Rustic 快照恢复数据库文件**

```bash
# 设置 Rustic 密码
export RUSTIC_PASSWORD="$(ansible-vault view secrets/vault.yml | grep vault_rustic_password | awk '{print $2}')"

# 查看可用快照 (rustic v0.11.0+ 不支持 --tag, 使用 --filter-tags-exact)
rustic -r "rclone:onedrive:backup/hdy/complete" snapshots

# 恢复数据库文件到临时目录 (v0.11.0+ 目标路径为位置参数)
rustic -r "rclone:onedrive:backup/hdy/complete" restore latest \
  /tmp/rustic_restore \
  --include /tmp/postgresql_all_dbs.sql \
  --include /var/lib/redis/dump.rdb
```

**步骤 2: 恢复 PostgreSQL**

```bash
# 导入数据库
PGPASSWORD='<postgresql_password>' psql -U admin -h localhost \
  -f /tmp/rustic_restore/tmp/postgresql_all_dbs.sql
```

**步骤 3: 恢复 Redis**

```bash
# 停止 Redis
systemctl stop redis-server

# 覆盖 RDB 文件
cp /tmp/rustic_restore/var/lib/redis/dump.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb

# 启动 Redis
systemctl start redis-server

# 验证 Redis
redis-cli -a '<redis_password>' PING
```

**步骤 4: 重启应用**

```bash
docker start new-api cliproxyapi
```

#### 验证恢复结果

```bash
# 检查容器日志
docker logs new-api --tail 20
docker logs cliproxyapi --tail 20

# 测试 API 端点
curl -s http://localhost:30001/api/status
curl -s http://localhost:30011/health

# 验证数据库数据
PGPASSWORD='<postgresql_password>' psql -U admin -d new_api -h localhost \
  -c "SELECT COUNT(*) FROM users;"
```

### 7.2 Rustic 备份架构说明

#### 备份存储位置

| 存储类型 | 路径 | 说明 |
|---------|------|------|
| 本地 | `/opt/backups/complete` | 本地 Rustic 仓库 |
| OneDrive | `rclone:onedrive:backup/hdy/complete` | 云端主备份 |
| GDrive | `rclone:gdrive:backup/hdy/complete` | 云端辅助备份 |

#### 备份内容

Rustic 完整系统备份包含:
- `/opt/dockers`: 所有 Docker 应用数据
- `/tmp/postgresql_all_dbs.sql`: PostgreSQL 数据库导出
- `/var/lib/redis/dump.rdb`: Redis RDB 快照
- `/etc/systemd/system`: systemd 服务配置
- `/etc/nginx`: Nginx 配置
- `/root/.config/rclone/rclone.conf`: rclone 配置

#### 备份频率与保留策略

- **备份频率**: 每 10 分钟
- **保留策略**:
  - 最近 3 个快照 (10分钟级)
  - 最近 1 天快照
  - 最近 1 周快照
  - 最近 1 月快照

#### 查询快照

```bash
# 设置密码
export RUSTIC_PASSWORD="$(ansible-vault view secrets/vault.yml | grep vault_rustic_password | awk '{print $2}')"

# 查看所有快照 (rustic v0.11.0+ 目标路径为位置参数)
rustic -r "rclone:onedrive:backup/hdy/complete" snapshots

# 查看快照内容
rustic -r "rclone:onedrive:backup/hdy/complete" ls latest

# 查找特定文件
rustic -r "rclone:onedrive:backup/hdy/complete" find postgresql_all_dbs.sql
```

### 7.3 旧备份方案 (已废弃)

> **⚠️ 警告**: 以下内容仅供参考，请使用上述 Rustic 方案。

<details>
<summary>点击展开旧方案 (tar 格式)</summary>

**旧备份路径**: `onedrive:backup/hdy/docker/db/docker_db_current.tar.gz`

**旧恢复流程**:
```bash
# 下载备份
rclone copy onedrive:backup/hdy/docker/db/docker_db_current.tar.gz /opt/backups/docker/db/

# 解压
mkdir -p /tmp/db_restore
tar -xzf /opt/backups/docker/db/docker_db_current.tar.gz -C /tmp/db_restore

# 恢复 PostgreSQL
PGPASSWORD='<password>' psql -U admin -d new_api -h localhost < /tmp/db_restore/postgresql_all_dbs.sql

# 恢复 Redis
systemctl stop redis-server
cp /tmp/db_restore/dump.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb
systemctl start redis-server
```

**迁移建议**: 如果你还有旧 tar 格式的备份，建议:
1. 先用旧流程恢复数据
2. 部署 Rustic 备份角色: `make deploy-operations_loop.Rustic`
3. 等待自动备份完成后，删除旧备份文件
</details>

### 7.4 常见问题处理

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Redis 连接被拒绝 | 容器使用 `host.docker.internal` 但 Redis 服务不在该地址 | 确认 `extra_hosts: "host.docker.internal:host-gateway"` 配置 |
| PostgreSQL 连接失败 | 密码错误或用户权限不足 | 检查 `postgresql_db_admin_password` 是否正确 |
| 容器持续重启 | 数据库未恢复或连接配置错误 | 查看日志 `docker logs new-api` 确认错误类型 |
| Redis 无密码配置 | 服务配置被意外修改 | 检查 `/etc/redis/redis.conf` 中的 `requirepass` 配置 |

> **注意**: New API 容器使用 `extra_hosts: "host.docker.internal:host-gateway"` 访问宿主机数据库服务，确保 Docker 网络模式正确配置。
### 关键部署与验证指令 (Deployment Commands)

如果修改了 `docker_apps` 角色（特别是 Sing-box 的配置、模板或 `singbox_nodes.yml`），**必须使用 `switch_remote` 明确切换目标主机环境，再完整下发应用配置并验证：**

```bash
# 1. 部署与验证 hdy (中转节点)
make switch_remote.hdy
make deploy-services.docker_apps.singbox
make verify-services.docker_apps.singbox

# 2. 部署与验证 cc15 (直连核心节点)
make switch_remote.cc15
make deploy-services.docker_apps.singbox
make verify-services.docker_apps.singbox
```

> **注意**: `docker_apps` 属于 Phase 5 (应用服务)，需要精确触达角色，不允许扩大范围，也就是说不允许通过 `make deploy-phase5` 批量全量下发。

---
## 5. 故障修复历史 (Troubleshoot History)

#### 1. 认证链接跳转错误 (GCLI vs Antigravity)
**现象**: 在 Antigravity 模式下点击"开始认证"，跳转的 Google 认证页面显示请求的是 GCLI 权限，导致生成的凭证无法用于 Antigravity。
**原因**: 容器内代码默认将认证模式设为 `geminicli`。
**临时修复**:
执行以下命令手动修改容器内的默认值为 `antigravity` (重启容器后可能失效，需再次执行):
```bash
docker exec gcli2api sed -i 's/mode: Optional\[str\] = "geminicli"/mode: Optional[str] = "antigravity"/g' /app/src/models.py
docker restart gcli2api
```

#### 2. 点击邮箱/额度报错 404
**原因**: Nginx 路由规则未覆盖所有子路径。
**修复**: 已在 `api-gcli.msuai.top.conf.j2` 中修正路由规则为 `location /antigravity/creds/ { ... }`。

---

## 8. Hysteria2 客户端配置（NAS / Raspberry Pi）

> 当前实现只在 `127.0.0.1:10808/10809` 提供本地代理，不启用 TUN、不安装 Privoxy、不修改 Docker 或系统默认路由。认证与混淆凭据必须引用 `hysteria_auth_password`、`hysteria_obfs_password` 权威变量。下方历史字面量示例不得继续用于部署。

### 8.1 概述
本节介绍如何在 NAS 上部署 Hysteria2 客户端，连接到 cc15 (aloha0133.suai.eu.org) 的代理服务。

### 8.2 服务器信息
| 项目 | 值 |
|------|-----|
| 服务器 | handclap6764.suai.eu.org |
| 端口 | 30051 |
| 密码 | `48aK^&8@u4Ty&o@6` |
| SNI | bing.com |
| ALPN | h3 |
| 混淆 | salamander |
| 混淆密码 | `Th1sIs@V3ryS3cur3&R@nd0mKey!` |

### 8.3 客户端配置模板

> **重要**: 使用 SOCKS5 模式而非 TUN 模式，确保兼容性

#### Hysteria2 工作原理
```
NAS (Docker) -> privoxy (8118) -> hysteria2-client (SOCKS5:10808/HTTP:8118) -> cc15 (handclap6764.suai.eu.org:30051) -> Internet
```

#### 架构说明
1. **hysteria2-client**: 同时提供 SOCKS5 (10808) 和 HTTP (8118) 代理
2. **privoxy**: 可选，将 SOCKS5 转为 HTTP（用于 Docker 镜像拉取）
3. **Docker**: 通过 HTTP 代理拉取镜像

#### sing-box 客户端配置 (推荐)
```json
{
  "log": {
    "level": "warn",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "socks",
      "tag": "socks-in",
      "listen": "::",
      "listen_port": 10808
    },
    {
      "type": "http",
      "tag": "http-in",
      "listen": "::",
      "listen_port": 8118
    }
  ],
  "outbounds": [
    {
      "type": "hysteria2",
      "tag": "hysteria2-out",
      "server": "handclap6764.suai.eu.org",
      "server_port": 30051,
      "password": "48aK^&8@u4Ty&o@6",
      "tls": {
        "enabled": true,
        "server_name": "bing.com",
        "alpn": ["h3"],
        "insecure": true
      },
      "obfs": {
        "type": "salamander",
        "password": "Th1sIs@V3ryS3cur3&R@nd0mKey!"
      }
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "rules": [
      {
        "type": "default",
        "outbound": "hysteria2-out"
      }
    ]
  }
}
```

#### Hysteria2 官方客户端配置 (备选)
```yaml
server: handclap6764.suai.eu.org:30051
auth: 48aK^&8@u4Ty&o@6

obfs:
  type: salamander
  salamander:
    password: Th1sIs@V3ryS3cur3&R@nd0mKey!

tls:
  sni: bing.com
  insecure: true
  alpn:
    - h3

socks5:
  listen: 0.0.0.0:10808

http:
  listen: 0.0.0.0:10808
```
auth: 48aK^&8@u4Ty&o@6

transport:
  type: udp

tls:
  sni: bing.com
  alpn:
    - h3
  insecure: true

obfs:
  type: salamander
  password: Th1sIs@V3ryS3cur3&R@nd0mKey!

socks5:
  listen: 127.0.0.1:1080

http:
  listen: 127.0.0.1:8080
```

### 8.4 部署步骤

#### 步骤 1: 配置变量

在 `inventories/host_vars/nas.yml` 中添加:
```yaml
# Hysteria2 客户端配置
docker_apps_hysteria2_client_enabled: true
docker_apps_hysteria2_client_server: "proxy.example.com"
docker_apps_hysteria2_client_port: 30051
docker_apps_hysteria2_client_password: "{{ vault_hysteria2_client_password }}"
docker_apps_hysteria2_client_sni: "bing.com"
docker_apps_hysteria2_client_alpn:
  - h3
docker_apps_hysteria2_client_obfs_type: "salamander"
docker_apps_hysteria2_client_obfs_password: "{{ vault_hysteria2_client_obfs_password }}"
docker_apps_hysteria2_client_insecure: true

# 启用 docker_apps
auroraops_roles:
  services:
    docker_apps: true
```

#### 步骤 2: 一键部署
```bash
FORCE=true make deploy-services.docker_apps ANSIBLE_LIMIT=nas
```

#### 步骤 3: 验证连接
```bash
# 测试代理
ssh nas "curl -x socks5://127.0.0.1:10808 -k https://www.google.com"

# 检查出口 IP
ssh nas "curl -x socks5://127.0.0.1:10808 -k https://ipinfo.io/json"
```

### 8.5 变量配置 (host_vars)

在 `inventories/host_vars/nas.yml` 中添加:
```yaml
# Hysteria2 客户端配置
docker_apps_hysteria2_client_enabled: true
docker_apps_hysteria2_client_server: "proxy.example.com"
docker_apps_hysteria2_client_port: 30051
docker_apps_hysteria2_client_password: "{{ vault_hysteria2_client_password }}"
docker_apps_hysteria2_client_sni: "bing.com"
docker_apps_hysteria2_client_alpn: ["h3"]
docker_apps_hysteria2_client_obfs_type: "salamander"
docker_apps_hysteria2_client_obfs_password: "{{ vault_hysteria2_client_obfs_password }}"
```

### 8.6 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接失败 | 服务器不可达 | 检查 aloha0133.suai.eu.org DNS 解析 |
| TLS 错误 | SNI 不匹配 | 确认 SNI 设置为 bing.com |
| 混淆验证失败 | 混淆密码错误 | 确认混淆密码正确 |
| 速度慢 | 网络延迟 | 尝试其他协议 (VLESS) |

### 8.7 相关命令
```bash
# 启动容器
docker start hysteria2-client

# 停止容器
docker stop hysteria2-client

# 重启容器
docker restart hysteria2-client

# 查看实时日志
docker logs -f hysteria2-client

# 进入容器调试
docker exec -it hysteria2-client sh
```


## 2. 变量说明
TODO: 补充此章节内容。
