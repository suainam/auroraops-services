# Role: vps.applications.redis

## 1. 概述
该角色用于在 Debian 系统上安装并配置 Redis 服务器，默认配置为安全的本地监听模式，并集成日志轮转。

## 2. 变量说明 (Defaults)
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `redis_port` | `6379` | Redis 监听端口。 |
| `redis_bind_address` | `0.0.0.0` | 绑定地址，默认允许所有接口（适配 Docker）。 |
| `redis_data_dir` | `/var/lib/redis` | 数据持久化目录。 |
| `redis_log_file` | `/var/log/redis/redis-server.log` | 日志文件路径。 |
| `redis_logrotate_enabled` | `true` | 是否部署 Role-local 日志轮转配置。 |

> **注意**: `redis_requirepass` (即 Redis 密码) 必须通过 `secrets/vault.yml` 提供。

## 3. 内部逻辑
- **安装与权限**: 安装 `redis-server` 并确保 `redis` 系统用户对数据和日志目录拥有正确权限。
- **配置模板**: 部署 `redis.conf.j2`，包含密码验证、绑定地址、端口及持久化（RDB/AOF）基础设置。
- **防火墙集成**: 自动配置 UFW 允许本地和 Docker 网段访问。
- **日志集成**: 直接管理 `/etc/logrotate.d/redis-server`；缺少 Logrotate 时仅提示，不执行其他 Role。
- **服务管理**: 确保 `redis-server` 在部署后自动启动并随系统自启。

## 4. 依赖关系
- 系统包: `redis-server`。
- Logrotate 是可选增强；需要时应单独部署 `system.logrotate`。

## 5. 维护与排查
- **状态检查**: `redis-cli ping`。
- **日志查看**: `journalctl -u redis-server`。
- **密码问题**: 检查 `redis.conf` 中的 `requirepass` 配置。
- **持久化**: RDB/AOF 文件存放在 `/var/lib/redis`。
