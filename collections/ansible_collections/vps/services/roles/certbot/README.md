# Role: vps.services.certbot

## 1. 概述
该角色用于自动获取和续订 Let's Encrypt 证书，默认使用 DNS-01 挑战（Cloudflare 插件），并集成 Nginx 自动重载。
**重大变更**：该角色现已迁移至使用 **统一 Python 虚拟环境 (`/opt/aurora_venv`)** 运行，彻底解决了系统级包冲突问题。

## 2. 变量说明
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `certbot_admin_email` | `"your_email@example.com"` | 管理员邮箱。 |
| `certbot_certs` | `[]` | 包含 `domains` 列表的任务字典。 |
| `certbot_dns_plugin` | `cloudflare` | DNS 服务商插件名称。 |
| `system_python_venv_path` | `"/opt/aurora_venv"` | 依赖的统一虚拟环境物理路径。 |
| `certbot_logrotate_enabled` | `true` | 是否部署 Role-local 日志轮转配置。 |
| `certbot_proxy_enabled` | `proxy_enabled` 或 `false` | Role 内代理开关；兼容旧 inventory 输入 `proxy_enabled`。 |
| `certbot_proxy_http` | `proxy_http` 或空字符串 | HTTP 代理；兼容旧 inventory 输入 `proxy_http`。 |
| `certbot_proxy_https` | `proxy_https` 或空字符串 | HTTPS 代理；兼容旧 inventory 输入 `proxy_https`。 |

## 3. 内部逻辑
- **环境隔离**: 强制向 `/opt/aurora_venv` 安装 `certbot` 及其插件，不依赖系统级 `apt` 包。
- **冲突清理**: 自动检测并移除 `/usr/local/bin/certbot` 等可能导致 PATH 混淆的旧版二进制文件。
- **路径锁定**: 所有内部任务（证书申请、续订、验证）均使用绝对路径 `/opt/aurora_venv/bin/certbot` 执行。
- **进程清理**: 部署前自动终止残留 certbot 进程，防止文件锁冲突。
- **自动化**:
    - 配置 Systemd Timer 驱动的自动续订。
    - 自动配置 `--deploy-hook "systemctl reload nginx"`。
- **日志轮转**: 直接管理 `/etc/logrotate.d/certbot`；缺少 Logrotate 时仅提示。

## 4. 使用示例
```yaml
certbot_certs:
  - domains:
      - "example.com"
      - "*.example.com"
```

## 5. 依赖关系
- **`vps.system.python_environment`**: 必须在 Phase 1 预先部署以建立基础环境。
- Logrotate 是可选增强；需要时应单独部署 `system.logrotate`。

## 6. 维护与排查
- **状态验证**: `make verify-services.certbot`。
- **证书状态**: `/opt/aurora_venv/bin/certbot certificates`。
- **手动续订**: `/opt/aurora_venv/bin/certbot renew --dry-run`。
- **软链接**: 系统执行 `certbot` 命令应通过 `/usr/bin/certbot` 软链至统一环境。
