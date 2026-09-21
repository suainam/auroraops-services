# Role: vps.services.docker

## 1. 概述
该角色用于在 Debian 系统上安装 Docker Engine 及 Docker Compose 插件并进行守护进程加固，同时支持原生主机迁移场景下的**安全退役与卸载 (Docker Retirement)** 生命周期。
## 2. 变量说明 (Defaults)
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `docker__users` | `[admin, ansible_user]` | 需要加入 `docker` 用户组的用户列表。默认包含 admin 用户和当前 Ansible 执行用户。 |
| `docker__install_compose_plugin` | `true` | 是否安装 Docker Compose 插件。 |
| `docker__daemon_options` | `{...}` | `daemon.json` 配置字典。默认启用 `live-restore` 和 `no-new-privileges`。 |
| `docker_logrotate_configs` | Docker/backup 四个 fragment | Docker 容器日志与备份文件的权威 logrotate 声明；普通部署与受控 fragment recovery 共用同一来源。 |
| `docker_state` | `present` | 角色终态声明。`present` 安装并配置 Docker；`absent` 执行安全退役卸载。 |
| `docker_retirement_require_no_running_containers` | `true` | 退役前置条件：若存在运行中的容器则阻断卸载。 |
| `docker_retirement_required_active_services` | `[]` | 退役前置条件：必须处于 active 状态的原生系统服务列表（如 `['hysteria2', 'cliproxyapi']`）。 |
| `docker_retirement_require_standby_snapshot` | `false` | 退役前置条件：是否要求验证过且可用的 Vaultwarden standby 快照。 |
| `docker_retirement_standby_latest_path` | `/opt/vaultwarden-standby/latest.json` | Standby 快照最新标记路径。 |
| `docker_retirement_standby_script_path` | `/usr/local/sbin/vaultwarden_standby.py` | Standby 校验脚本路径。 |
| `docker_retirement_packages` | `[docker-ce, docker-ce-cli, containerd.io, ...]` | 目标卸载的 Docker/containerd 软件包列表。仅卸载已安装项。 |
| `docker_retirement_allowed_removal_packages` | `[docker-ce, docker-ce-cli, containerd.io, ..., runc]` | APT 模拟允许卸载的白名单。若模拟产生额外依赖级联删除则阻断卸载。 |
| `docker_retirement_fact_path` | `/etc/ansible/facts.d/docker_retirement.fact` | 退役恢复基线持久化路径，供回滚精准恢复软件包与服务状态。 |
| `docker_retirement_preserve_data` | `true` | 数据保留开关。强制保留 `/var/lib/docker` 与 `/opt/dockers`，严禁任何数据删除。 |

## 3. 内部逻辑
- **安装源配置**: 自动添加 Docker 官方 GPG 密钥及 APT 仓库。
- **防火墙兼容性**: 修正 UFW 与 Docker 的路由冲突。
- **配置加固**: 部署 `/etc/docker/daemon.json`，启用：
    - **Live Restore**: 允许守护进程更新时不中断容器运行。
    - **No New Privileges**: 禁止容器进程获取额外权限（提权防护）。
    - **日志限制**: 限制容器日志大小，防止磁盘耗尽。
- **权限管理**: 自动将 `docker__users` 列表中的用户加入 `docker` 组。自动排除 root 用户（避免安全风险）。
- **日志轮转**: `tasks/logrotate.yml` 通过完整 `system.logrotate` 合同部署；`tasks/logrotate_repair.yml` 只重建 fragment，不触碰 Docker daemon、容器或 baseline。
- **安全退役与卸载 (Docker Retirement, `docker_state: absent`)**:
    - **显式 Opt-in 契约**: 通过主机变量指定 `docker_state: absent`。注意：`auroraops_roles.services.docker` **必须保持为 true（或默认缺省）**，不能设为 false。若设为 false，Ansible 将直接跳过整个角色，导致 Docker 保持安装运行而无法执行卸载；保持角色启用并设置 `docker_state: absent` 方可走完 Make check/deploy/verify 生命周期。
    - **前置硬阻断 (Check/Preflight)**:
        1. 若检测到任何运行中的容器，立即失败阻断，杜绝运行中业务中断。
        2. 若配置了 `docker_retirement_required_active_services`，断言各原生服务（如 Hysteria2、CLIProxyAPI）为 active 状态，否则阻断。
        3. 若开启 `docker_retirement_require_standby_snapshot`，校验 standby 最新快照存在并调用 verify 校验通过，否则阻断。
        4. **APT 模拟安全防护**: 卸载前执行 `apt-get remove --simulate`，分析计划移除的依赖包；若出现预设允许列表以外的反向依赖包被级联移除，立即阻断退出。
    - **状态持久化与受控停止**: 探测记录当前已安装包精确版本、服务 enabled/active 状态及数据目录存在性，保存至 `/etc/ansible/facts.d/docker_retirement.fact`。随后停用并禁用 `docker.service`、`docker.socket`、`containerd.service`。
    - **精准卸载与零数据破坏**: 仅对实际安装的 Docker 软件包执行 `apt: state=absent`，且显式设置 `purge: false`、`autoremove: false`。绝不执行 autoremove，绝不执行 purge，绝对保留 `/var/lib/docker`、`/opt/dockers`、`/opt/vaultwarden-standby` 及所有恢复资产。
    - **完整回滚能力 (`make rollback-services.docker`)**: 从 `/etc/ansible/facts.d/docker_retirement.fact` 读取退役前记录，重新安装原有软件包并恢复服务的 enabled 与 started 状态；**回滚时绝对不启动先前已停止的容器，也绝对不改动用户数据**。旧有的破坏性 `/var/lib/docker` 删除逻辑已被彻底移除。
    - **终态验证 (`make verify-services.docker`)**: 在 `docker_state: absent` 下断言 `docker`、`dockerd`、`containerd` 二进制均不存在，相关包已卸载，服务非 active，且验证 `/var/lib/docker` 数据依然完整保留。

## 4. 依赖关系
- 系统包: `ca-certificates`, `curl`, `gnupg`, `python3-docker`。

## 5. 维护与排查
- **状态检查**: `docker info` 或 `systemctl status docker`。
- **配置修改**: 修改 `docker__daemon_options` 变量后需重新部署以触发重启。

## 6. 限制与边界 (Limitations)
1. **平台限制**: 退役与回滚流程基于 Debian/Ubuntu APT 包管理器与 systemd 服务管理器。
2. **数据保留边界**: Docker 退役仅停用服务并卸载可执行包，不清理 `/var/lib/docker` 或 `/opt/dockers` 中的业务数据。若未来需要彻底释放磁盘数据，必须在完成全量 Rustic 远程备份并由运维明确授权后，由专门的数据清理流程执行，严禁在退役生命周期中自动删除数据。
