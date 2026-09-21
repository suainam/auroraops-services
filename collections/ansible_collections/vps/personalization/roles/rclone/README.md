# Role: vps.personalization.rclone

## 1. 概述
该角色用于安装最新版的 Rclone，并配置云端存储挂载，支持 OneDrive、Google Drive 等多种后端。

## 2. 变量说明

### 2.1 基本配置变量

| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `rclone_include_user_configs` | `true` | 是否包含用户自定义配置目录。 |
| `rclone_backup_path_prefix` | `""` | 云端备份路径前缀（用于区分不同主机的备份位置），例如 `"backup/nas"` 或 `"backup/ccuai"`。 |

### 2.2 代理配置变量

| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `rclone_use_proxy` | `"{{ proxy_enabled \| default(false) }}"` | 是否使用代理（继承全局变量）。 |
| `rclone_http_proxy` | `"{{ proxy_http \| default('') }}"` | HTTP 代理地址（继承全局变量）。 |
| `rclone_https_proxy` | `"{{ proxy_https \| default('') }}"` | HTTPS 代理地址（继承全局变量）。 |

### 2.3 敏感变量（Vault 加密）

| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `rclone_onedrive_token` | `vault_...` | OneDrive 的 OAuth Token (Vault 加密)。 |
| `rclone_onedrive_drive_id` | `vault_...` | OneDrive 的 Drive ID (Vault 加密)。 |
| `rclone_gdrive_token` | `vault_...` | Google Drive 的 OAuth Token (Vault 加密)。 |

## 3. 内部逻辑

- **安装**: 使用官方脚本安装最新版本，替代系统自带的旧版。支持代理配置（如果 `rclone_use_proxy` 为 true）。
- **智能配置 (Smart Token Preservation)**:
    - **提取**: 部署前自动检测现有的 `rclone.conf` 或从 System Backup 中提取 Token。
    - **验证**: 创建临时配置并运行 `rclone lsd` 验证提取的 Token 是否有效（支持代理）。
    - **决策**: 
        - 如果有效 -> 保留使用（避免覆盖后需要重新授权）。
        - 如果失效 -> 自动回退到 Vault 中的默认 Token。
- **配置管理**: 部署 `/root/.config/rclone/rclone.conf`，支持模块化配置片段。
- **权限安全**: 配置目录权限设为 `0700`，配置文件设为 `0600`。

## 4. 使用示例

### 4.1 配置主机变量 (host_vars)

```yaml
# NAS 主机配置
rclone_backup_path_prefix: "backup/nas"
# 代理配置继承自全局变量 (proxy_enabled, proxy_http, proxy_https)
```

```yaml
# ccuai 主机配置
rclone_backup_path_prefix: "backup/ccuai"
```

### 4.2 同步命令示例

```bash
# 本地同步到云端（使用路径前缀）
rclone sync /local/data onedrive:{{ rclone_backup_path_prefix }}/data/

# 双向同步
rclone bisync /local/data onedrive:{{ rclone_backup_path_prefix }}/data/

# 查看云端文件
rclone lsd onedrive:{{ rclone_backup_path_prefix }}/
```

## 4. 依赖关系
- 依赖网络连接以从 `rclone.org` 下载安装脚本（支持代理）。
- 全局代理变量: `proxy_enabled`, `proxy_http`, `proxy_https`。

## 5. 维护与排查
- **查看配置**: `rclone config`。
- **连接测试**: `rclone lsd <remote_name>:`（如果配置了代理，会自动使用代理）。
- **查看远程文件**: `rclone lsl <remote_name>:<file_path>`
- **版本检查**: `rclone version`。
- **代理测试**: 在 NAS 上，确保代理服务器（如 192.168.31.200:7890）可访问。
