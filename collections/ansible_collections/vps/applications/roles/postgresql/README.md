# Role: vps.applications.postgresql

## 1. 概述
该角色用于在 Debian 系统上安装、配置并管理 PostgreSQL 数据库。支持自定义数据库、用户权限、HBA 认证规则以及日志轮转集成。

## 2. 变量说明 (Defaults)
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `postgresql_version` | `17` | 安装的 PostgreSQL 版本。 |
| `postgresql_port` | `5432` | 数据库监听端口。 |
| `postgresql_listen_addresses` | `localhost` | 监听地址，默认仅限本地。 |
| `postgresql_app_db_name` | `app_db` | 默认创建的应用数据库名称。 |
| `postgresql_app_db_user` | `admin` | 默认的应用数据库用户名。 |
| `postgresql_shared_buffers` | `256MB` | 共享内存缓冲区大小。 |
| `postgresql_logrotate_enabled` | `true` | 是否部署 Role-local 日志轮转配置。 |

> **注意**: `postgresql_root_password` 和 `postgresql_db_admin_password` 必须在 `vault.yml` 中定义。

## 3. 内部逻辑
- **分层任务**:
    - `install.yml`: 自动添加 PostgreSQL 官方仓库并安装指定版本的软件包。
    - `configure.yml`: 渲染 `postgresql.conf` 和 `pg_hba.conf`，并确保存储目录权限正确。
    - `users_dbs.yml`: 管理数据库角色、权限及数据库创建。
    - `logrotate.yml`: 直接管理 `/etc/logrotate.d/postgresql-common`；缺少 Logrotate 时仅提示，不执行其他 Role。
- **认证增强**: 默认强制使用 `scram-sha-256` 认证算法。
- **本地化配置**: 默认配置为 `Asia/Shanghai` 时区及 `UTF8` 编码。
- **环境修复**: 初始化集群时设置 `TMPDIR=/tmp` 环境变量，解决 postgres 用户临时目录权限问题。

## 4. 依赖关系
- 集合: `community.postgresql`。
- 系统包: `postgresql-<version>`, `python3-psycopg2`。
- Catalog 保留 `system.python_environment` 全量部署顺序；定向生命周期只检查当前 Ansible Python 解释器及 `psycopg2`，不执行完整依赖 Role。
- Logrotate 是可选增强；需要时应单独部署 `system.logrotate`。
- **重要**: 需在 `ansible.cfg` 中设置 `remote_tmp = /tmp` 以避免权限问题。

## 5. 维护与排查
- **配置检查**: `sudo -u postgres psql -c "SELECT version();"`。
- **日志查看**: `journalctl -u postgresql`。
- **权限问题**: 检查 `pg_hba.conf` 中的认证规则。
- **性能调优**: 调整 `postgresql_shared_buffers` 等参数后需重启服务。
