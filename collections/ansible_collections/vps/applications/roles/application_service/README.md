# Role: vps.applications.application_service

## 1. 概述
该角色是一个**元角色（Meta Role）**，用于将任意应用程序封装为 Systemd 服务。它负责创建用户/组、生成服务文件并管理服务状态。

**⚠️ 重要说明**：
- 此角色**不应该直接部署**，而是通过 `include_role` 被其他角色调用
- 启用控制**完全由调用方决定**，不受 `auroraops_roles['applications']['application_service']` 影响
- 与 `container_deployer` 保持一致的设计模式
- `roles.yml` 中的 `application_service: false` 配置**已废弃**，不再生效

## 2. 变量说明

### 必需变量
| 变量名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `app_service_name` | string | 服务名称（必填）。 |
| `app_service_exec_start` | string | 启动命令（必填）。 |

### 可选变量
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `app_service_description` | `"Generic Application Service"` | 服务描述。 |
| `app_service_user` | `"root"` | 运行服务的用户名。 |
| `app_service_group` | `""` | 运行服务的组名。 |
| `app_service_type` | `"simple"` | 服务类型（simple/forking/oneshot/notify）。 |
| `app_service_timeout` | `""` | 服务超时时间（如 `30s`）。 |
| `app_service_timeout_stop_sec` | `""` | 停止服务超时时间（如 `30s`）。 |
| `app_service_restart_on_change` | `true` | 服务文件变化时是否自动重启；设为 `false` 时只 reload systemd 配置。 |
| `app_service_exec_pre` | `""` | 启动前执行命令（可选）。 |
| `app_service_exec_post` | `""` | 启动后执行命令（可选）。 |
| `app_service_exec_stop` | `""` | 停止命令（可选）。 |
| `app_service_working_directory` | `""` | 工作目录。 |
| `app_service_environment` | `[]` 或 `{}` | 环境变量（列表或字典格式）。 |
| `app_service_environment_file` | `""` | 环境变量文件路径。 |
| `app_service_exec_stop_post` | `""` | 服务进入终态后始终执行的清理命令。 |
| `app_service_dependencies` | `[]` | 服务依赖项（如 `["postgresql.service"]`）。 |
| `app_service_requires` | `[]` | 强依赖服务（如 `["docker.service"]`）。 |
| `app_service_enabled` | `true` | 是否启用服务（实例级别控制）。 |
| `app_service_state` | `started` | 服务状态（started/stopped/restarted）。 |

## 3. 内部逻辑
- **权限管理**: 自动创建系统级用户和组（如果指定）。
- **Systemd 集成**: 渲染 `application.service.j2` 模板到 `/etc/systemd/system/`。
- **生命周期**: 处理 `daemon-reload` 并确保服务按预期状态运行。

## 4. 使用示例

### 示例 1：基础服务（cleanup 角色）

```yaml
- name: Create Docker maintenance prune service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: docker-maintenance-prune
    app_service_description: Docker Maintenance Prune Service
    app_service_exec_start: '{{ python_executor }} /usr/local/bin/docker-prune.py'
    app_service_user: root
    app_service_group: root
    app_service_environment:
      - "KEEP_IMAGES={{ docker_prune_keep_images | join(',') }}"
  when: auroraops_roles['operations_loop']['cleanup'] | default(true) | bool
  tags: [deploy, cleanup_system, cleanup, operations_loop, phase6]
```

**关键点**：
- ✅ `when` 条件检查**调用方角色**（`cleanup`），而不是元角色本身
- ✅ `app_service_environment` 使用列表格式传递环境变量

### 示例 2：带依赖的服务（health_checks 角色）

```yaml
- name: Deploy health_check_runner service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: health_check_runner
    app_service_description: Health Check Runner Service
    app_service_exec_start: /usr/local/bin/health_check_runner
    app_service_user: root
    app_service_group: root
    app_service_working_directory: /opt/health_checks
    app_service_dependencies:
      - network-online.target
    app_service_environment:
      HEALTH_CHECKS_CONFIG: /etc/health_checks/config.yml
      LOG_LEVEL: INFO
  when: auroraops_roles['observability']['health_checks'] | default(true) | bool
  tags: [deploy, observability, health_checks, phase5]
```

**关键点**：
- ✅ 使用 `app_service_dependencies` 指定服务依赖
- ✅ 使用字典格式传递环境变量（更清晰）
- ✅ 指定 `working_directory` 确保服务在正确的目录运行

### 示例 3：带环境变量文件的服务（Rustic 角色）

```yaml
- name: Deploy Rustic backup service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: rustic-backup
    app_service_description: Rustic Backup Service
    app_service_exec_start: /usr/local/bin/rustic-backup.sh
    app_service_user: root
    app_service_group: root
    app_service_environment_file: /etc/Rustic/backup.env
    app_service_type: oneshot
  when: auroraops_roles['operations_loop']['Rustic'] | default(true) | bool
  tags: [deploy, operations_loop, Rustic, phase6_5]
```

**关键点**：
- ✅ 使用 `app_service_environment_file` 从文件加载环境变量
- ✅ 使用 `type: oneshot` 适合一次性执行的任务

### 示例 4：禁用服务但保留配置

```yaml
- name: Create maintenance service (disabled)
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: maintenance-task
    app_service_description: Maintenance Task Service
    app_service_exec_start: /usr/local/bin/maintenance.sh
    app_service_enabled: false  # ✅ 实例级别禁用
    app_service_state: stopped
  when: auroraops_roles['operations_loop']['cleanup'] | default(true) | bool
  tags: [deploy, operations_loop, cleanup, phase6]
```

**关键点**：
- ✅ 使用 `app_service_enabled: false` 禁用单个服务实例
- ✅ 服务文件会创建，但不会启用和启动

## 5. ❌ 错误示例（避免）

### 错误 1：检查元角色的启用状态

```yaml
# ❌ 错误：检查元角色本身的启用状态
- name: Create my service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: my-service
    app_service_exec_start: /usr/local/bin/my-service
  when: auroraops_roles['applications']['application_service'] | default(true) | bool  # ❌ 错误！
```

**问题**：`application_service` 在 `roles.yml` 中设置为 `false`，导致服务永远不会创建。

**正确做法**：
```yaml
# ✅ 正确：检查调用方角色的启用状态
when: auroraops_roles['my_domain']['my_role'] | default(true) | bool
```

### 错误 2：直接部署元角色

```yaml
# ❌ 错误：在 playbook 中直接部署元角色
- name: Deploy application_service
  hosts: all
  roles:
    - vps.applications.application_service  # ❌ 错误！
```

**问题**：元角色缺少必需的变量（`app_service_name`, `app_service_exec_start`），会失败。

**正确做法**：元角色只能通过 `include_role` 调用，不能直接部署。

### 错误 3：忘记设置 when 条件

```yaml
# ❌ 错误：没有 when 条件
- name: Create my service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: my-service
    app_service_exec_start: /usr/local/bin/my-service
  # ❌ 缺少 when 条件
```

**问题**：即使调用方角色被禁用，服务仍然会创建。

**正确做法**：
```yaml
when: auroraops_roles['my_domain']['my_role'] | default(true) | bool
```

## 6. 依赖关系
- 依赖于 `ansible.builtin` 核心模块。
- 需要 systemd 支持（Debian 12 默认）。

## 7. 维护与排查

### 查看服务状态
```bash
systemctl status <app_service_name>
```

### 查看服务日志
```bash
journalctl -u <app_service_name> -f
```

### 手动启动/停止服务
```bash
systemctl start <app_service_name>
systemctl stop <app_service_name>
systemctl restart <app_service_name>
```

### 查看服务配置
```bash
cat /etc/systemd/system/<app_service_name>.service
```

### 重新加载 systemd
```bash
systemctl daemon-reload
```

## 8. 设计原则

**元角色的三大原则**：

1. **被动调用**：元角色不应该有自己的 `auroraops_roles` 检查
2. **调用方控制**：启用与否完全由调用方的 `when` 条件决定
3. **实例级别开关**：保留 `app_service_enabled` 用于控制单个服务实例

**与 `container_deployer` 保持一致**：
- ✅ 无 `auroraops_roles` 检查
- ✅ 不在 `roles.yml` 中定义
- ✅ 完全由调用方控制

## 9. 相关元角色

- `vps.applications.application_timer` - 创建 systemd timer
- `vps.services.container_deployer` - 部署 Docker 容器
- `vps.services.nginx` (meta_site.conf.j2) - 生成 Nginx 站点配置


## 4. 依赖关系
TODO: 补充此章节内容。

## 5. 维护与排查
TODO: 补充此章节内容。
