# Prerequisite Checks Role

## 1. 概述

通用前置检查角色，供其他角色在执行前验证依赖是否满足。

**设计目的**: 解决角色间软依赖问题，避免使用 `meta/main.yml` 硬依赖导致的重复执行。

新调用方应使用 `prereq_checks_*` 输入。文档中的 `prereq_*` 示例仍受支持，用于说明旧 Role 调用方的向后兼容路径；Role 内部只消费 `prereq_checks_*`。

## 2. 支持的检查类型

| 检查类型 | 变量前缀 | 说明 |
|----------|----------|------|
| Bitwarden CLI | `prereq_checks_bw_*` | 检查 bw CLI 安装、登录状态；兼容旧 `prereq_bw_*` |
| Docker | `prereq_checks_docker_*` | 检查 Docker 安装、运行状态；兼容旧 `prereq_docker_*` |
| Network | `prereq_checks_network_*` | 检查网络连通性；兼容旧 `prereq_network_*` |
| Commands | `prereq_checks_commands_*` | 检查自定义命令可用性；兼容旧 `prereq_commands_*` |

## 3. 使用方式

### 3.1 基本用法

```yaml
# 在角色的 tasks/main.yml 开头引入
- name: Check prerequisites
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_bw_enabled: true
    prereq_docker_enabled: true
```

### 3.2 检查 Bitwarden CLI

```yaml
- name: Check bw CLI is ready
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_bw_enabled: true
    prereq_bw_required: true  # false = 仅警告不报错

# 检查后可使用以下 facts:
#   prereq_bw_installed: bool
#   prereq_bw_version: string
#   prereq_bw_status: "unlocked" | "locked" | "unauthenticated"
#   prereq_bw_ready: bool
```

### 3.3 检查 Docker

```yaml
- name: Check Docker is ready
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_docker_enabled: true
    prereq_docker_required: true

# 检查后可使用以下 facts:
#   prereq_docker_installed: bool
#   prereq_docker_version: string
#   prereq_docker_running: bool
#   prereq_docker_ready: bool
```

### 3.4 检查网络连通性

```yaml
- name: Check network connectivity
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_network_enabled: true
    prereq_network_hosts:
      - {host: "bws.msuai.top", port: 443}
      - {host: "github.com", port: 443, timeout: 10}
    prereq_network_required: false  # 仅警告

# 检查后可使用以下 facts:
#   prereq_network_ready: bool
#   prereq_network_failed: list
```

### 3.5 检查自定义命令

```yaml
- name: Check required commands
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_commands_enabled: true
    prereq_commands:
      - {name: "git", cmd: "git --version"}
      - {name: "python3", cmd: "python3 --version", install_hint: "apt install python3"}
    prereq_commands_required: true

# 检查后可使用以下 facts:
#   prereq_commands_ready: bool
#   prereq_commands_failed: list
```

### 3.6 组合检查

```yaml
- name: Check all prerequisites
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    # Bitwarden CLI
    prereq_bw_enabled: true
    prereq_bw_required: "{{ use_vaultwarden | default(false) }}"
    
    # Docker
    prereq_docker_enabled: true
    prereq_docker_required: true
    
    # Network
    prereq_network_enabled: true
    prereq_network_hosts:
      - {host: "registry.docker.io", port: 443}
    prereq_network_required: false
```

## 4. 变量参考

### 4.1 Bitwarden CLI 检查

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prereq_checks_bw_enabled` | bool | `prereq_bw_enabled` 或 `false` | 启用检查 |
| `prereq_checks_bw_required` | bool | `prereq_bw_required` 或 `true` | 失败时报错 |
| `prereq_checks_bw_session_file` | string | `prereq_bw_session_file` 或 `~/.bw_session` | Session 文件路径 |

### 4.2 Docker 检查

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prereq_checks_docker_enabled` | bool | `prereq_docker_enabled` 或 `false` | 启用检查 |
| `prereq_checks_docker_required` | bool | `prereq_docker_required` 或 `true` | 失败时报错 |

### 4.3 网络检查

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prereq_checks_network_enabled` | bool | `prereq_network_enabled` 或 `false` | 启用检查 |
| `prereq_checks_network_hosts` | list | `prereq_network_hosts` 或 `[]` | 主机列表 |
| `prereq_checks_network_required` | bool | `prereq_network_required` 或 `true` | 失败时报错 |

### 4.4 命令检查

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prereq_checks_commands_enabled` | bool | `prereq_commands_enabled` 或 `false` | 启用检查 |
| `prereq_checks_commands` | list | `prereq_commands` 或 `[]` | 命令列表 |
| `prereq_checks_commands_required` | bool | `prereq_commands_required` 或 `true` | 失败时报错 |

## 5. 输出 Facts

检查完成后，以下 facts 可供后续任务使用：

```yaml
# Bitwarden CLI
prereq_bw_installed: true/false
prereq_bw_version: "2024.7.2"
prereq_bw_status: "unlocked"
prereq_bw_server: "https://bws.msuai.top"
prereq_bw_ready: true/false

# Docker
prereq_docker_installed: true/false
prereq_docker_version: "Docker version 24.0.0"
prereq_docker_running: true/false
prereq_docker_ready: true/false

# Network
prereq_network_ready: true/false
prereq_network_failed: [{item: {host: "...", port: 443}, ...}]

# Commands
prereq_commands_ready: true/false
prereq_commands_failed: [{item: {name: "...", cmd: "..."}, ...}]
```

## 6. 错误处理

### 6.1 required=true (默认)

检查失败时，playbook 会立即停止并显示详细错误信息：

```
============================================================
ERROR: Bitwarden CLI is not ready!
============================================================

Current status:
  Installed: true
  Status: locked

To fix this, run:
  make deploy-services.nodejs.nodejs_bw

============================================================
```

### 6.2 required=false

检查失败时，仅显示警告，playbook 继续执行：

```
WARNING: Bitwarden CLI is not ready, but check is not required.
Some features may not work. Run: make deploy-services.nodejs.nodejs_bw
```

## 7. 最佳实践

## 7. 生命周期口径

- `check` / `deploy`
  - 都执行前置检查本身；这个角色不写入持久化业务状态，`deploy` 的意义是“把检查作为显式 gate 执行一次”。
- `verify`
  - 重新执行同一组检查，确认依赖在 deploy 后仍满足。
- `rollback`
  - 这是显式 no-op。`prereq_checks` 只读探测，不创建要回滚的资源。
- `recheck`
  - 与 `verify` 相同，适合在回滚后确认环境仍处于可继续部署的基线。

### 7.1 在角色中使用

```yaml
# roles/myapp/tasks/main.yml
---
# 1. 前置检查
- name: Check prerequisites
  ansible.builtin.include_role:
    name: vps.services.prereq_checks
  vars:
    prereq_bw_enabled: "{{ myapp_use_vaultwarden | default(false) }}"
    prereq_docker_enabled: true
  tags: [always]

# 2. 根据检查结果决定行为
- name: Get password from Vaultwarden
  ansible.builtin.set_fact:
    myapp_password: "{{ lookup('vps.services.vaultwarden', 'myapp/db') }}"
  when: prereq_bw_ready | default(false)

- name: Use fallback password
  ansible.builtin.set_fact:
    myapp_password: "{{ vault_myapp_password }}"
  when: not (prereq_bw_ready | default(false))

# 3. 继续部署
- name: Deploy application
  ...
```

### 7.2 条件性依赖

```yaml
# 只有启用 Vaultwarden 时才检查
prereq_bw_enabled: "{{ use_vaultwarden_lookup | default(false) }}"
prereq_bw_required: "{{ use_vaultwarden_lookup | default(false) }}"
```

## 8. 与 Phase 系统配合

```
Phase 2: docker, docker_apps (vaultwarden)
Phase 3: nodejs (bw CLI), nginx, certbot
         ↓
         prereq_checks 在这里验证依赖
         ↓
Phase 4: postgresql, applications (使用 lookup 插件)
```

部署顺序保证了依赖关系，`prereq_checks` 作为安全网，在单独部署时提供明确的错误提示。


## 2. 变量说明
TODO: 补充此章节内容。

## 3. 内部逻辑
TODO: 补充此章节内容。

## 4. 依赖关系
TODO: 补充此章节内容。

## 5. 维护与排查
TODO: 补充此章节内容。
