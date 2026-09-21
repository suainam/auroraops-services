# CLIProxyAPI Native (vps.services.cliproxyapi_native)

## 1. 概述

本 Role 负责在低内存或边缘计算节点（如 Raspberry Pi 5）上部署原生 systemd 管理的 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 服务。通过消除 Docker 守护进程与容器运行时的常驻开销，显著节约主机系统内存。

服务监听回环地址 `127.0.0.1:30011`，作为应用层 API 代理（Phase 5），通过前置网络服务（如透明网关混合代理 `http://127.0.0.1:12346`）与各类上游 AI 提供商通信。

## 2. 版本锁定与上游校验证据

本 Role 严格锁定官方上游 Release 二进制，并通过 SHA256 校验和验证完整性：
- 官方发布仓库: `router-for-me/CLIProxyAPI`
- 当前稳定版本: `v7.3.9`
- Linux ARM64 (aarch64) SHA256: `827d7b8fb43a137898f7b68ceb6ff1aefcd0528cd5d59ea61317251171832b75`
- Linux AMD64 (x86_64) SHA256: `fd45e915d84e40fc09cefaae6b271a59d542bf284fd3dfee38abe5472412427b`
- 不支持的架构直接在 Preflight 阶段硬性失败，杜绝回退架构错配。

## 3. 认证持久化与架构说明

- **无 SQLite 依赖**: 上游 CLIProxyAPI 采用基于文件系统的认证存储架构。通过 `auth-dir` (`/opt/cliproxyapi/data`) 目录持久化各类提供商的 OAuth 授权凭证、Token 与会话。
- **内存调优**: 设置 `GOMEMLIMIT=220MiB` 软性上限，驱动 Go 运行时更主动地进行垃圾回收，防止在长时间运行下堆内存无限膨胀。
- **定时重启释放内存**: 配套部署 `cliproxyapi-restart.timer` 与 companion oneshot service `cliproxyapi-restart.service`，在每日凌晨 `04:00` 自动重启服务，释放内存碎片。
- **出站代理下载**: 安装包下载显式经由 `http://127.0.0.1:12346` 代理出站，避免边缘节点直连 GitHub release 失败。

## 4. 关键变量说明

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `cliproxyapi_native_enabled`     | `true` | Role 本地启用开关（需与 `auroraops_roles.services.cliproxyapi_native` 取 AND） |
| `cliproxyapi_native_version`     | `"v7.3.9"` | 上游发布版本标签 |
| `cliproxyapi_native_install_dir` | `"/opt/cliproxyapi"` | 二进制程序及配置文件目录 |
| `cliproxyapi_native_data_dir`    | `"/opt/cliproxyapi/data"` | OAuth 与会话数据持久化目录 |
| `cliproxyapi_native_bind_address`| `"127.0.0.1:30011"` | 服务绑定地址及端口 |
| `cliproxyapi_native_restart_hour`| `"04"` | 每日定时重启小时数 (24h) |
| `cliproxyapi_native_gomemlimit`  | `"220MiB"` | Go 运行时内存限制 |
| `cliproxyapi_native_http_proxy`  | `""` | 注入 systemd 的出站 HTTP 代理（留空避免劫持进程内直连） |
| `cliproxyapi_native_proxy_url`   | `"http://127.0.0.1:12346"` | 应用层出站代理（走带自动容灾的混合代理端口） |
| `cliproxyapi_native_download_proxy`| `"http://127.0.0.1:12346"` | 下载发布包所用出站代理 |
| `cliproxyapi_native_management_key` | `cliproxyapi_management_key` | 管理接口密钥（来自 Vault） |
| `cliproxyapi_native_api_keys`    | `docker_apps_cliproxyapi_api_keys` | 外部调用鉴权 API Keys（来自 Vault） |

## 5. 生命周期契约

### 5.1 预检 (Preflight)
执行 `preflight.yml`：
1. 校验架构合法性（严格限制在 aarch64 / amd64）。
2. 校验对应架构的 Release SHA256 校验和存在。
3. 检查基线路径状态。

### 5.2 部署 (Deploy)
执行 `install.yml` 与 `configure.yml`（在 `--check` 模式下只读跳过 mutation）：
1. 经由出站代理下载并校验对应架构发布包，解压部署 `/opt/cliproxyapi/cli-proxy-api` (0755)。
2. 创建敏感持久化目录 `/opt/cliproxyapi/data` (0700)。
3. 渲染配置文件 `/opt/cliproxyapi/config.yaml` (0600，`no_log: true` 保证 `--diff` 零泄露)。
4. 部署 `cliproxyapi-native.service`、`cliproxyapi-restart.service` 和 `cliproxyapi-restart.timer`。
5. 启动并启用服务及定时器。若二进制被安装/更新，在验证前立即完成服务重启生效。

### 5.3 验证 (Verify)
执行 `verify.yml`：
1. 校验配置文件与数据目录权限（0600/0700）。
2. 校验 systemd service 与 timer 均处于 `running` 且 `enabled` 状态。
3. 校验回环端口 `127.0.0.1:30011` 监听状态。
4. 发起带有 `Authorization: Bearer <key>` 鉴权的 GET 请求探测 `/v1/models` 端点（`no_log: true` 保证零凭据泄露，断言 HTTP 200）。

### 5.4 回滚 (Rollback)
执行 `rollback.yml`：
1. 停止并禁用 systemd timer 与 service。
2. 清理 systemd unit 文件并重新加载守护进程。
3. 清理程序二进制与配置文件。
4. **安全红线**: **绝对不删除 `data/` 目录中的 OAuth 凭证与数据**，遵循仓库生命周期合规标准。
