# Container Deployer

一个通用的 Docker 应用部署 Meta 角色，支持单容器和 Docker Compose 两种部署模式。

## 概述

`container_deployer` 是一个 Meta 角色，用于标准化 Docker 应用的部署流程。调用方只需提供必填的 `cdp_name` 和 `cdp_image`；未传入的可选 `cdp_*` 参数统一通过 Role defaults 归一化，任务文件不直接读取未定义的原始变量。它封装了常见的部署任务：

- 数据目录创建
- 从镜像初始化数据
- 权限修正
- 单容器部署
- Docker Compose 部署
- 日志管理（默认 json-file, 5m, 3 files）
- 验证和回滚

## 使用方式

### 单容器部署示例

```yaml
- include_role:
    name: vps.services.container_deployer
  vars:
    cdp_name: "vaultwarden"
    cdp_image: "{{ vaultwarden_image }}"
    cdp_dirs: ["data"]
    cdp_networks: [{name: "sweb"}]
    cdp_ports: ["30007:80"]
    cdp_volumes: ["/opt/dockers/vaultwarden/data:/data"]
    cdp_env_file: "{{ role_path }}/files/vaultwarden.env"
  tags: [deploy, services, docker_apps, vaultwarden, phase2]
```

### Docker Compose 部署示例

```yaml
- include_role:
    name: vps.services.container_deployer
  vars:
    cdp_name: "newapi-suite"
    cdp_image: "{{ newapi_image }}"
    cdp_compose_enabled: true
    cdp_compose_template: "newapi_suite_compose.yml.j2"
    cdp_dirs: ["new-api/data", "new-api/logs"]
    cdp_compose_vars:
      app_port: "30001"
  tags: [deploy, services, docker_apps, newapi_suite, phase2]
```

### 带数据初始化的示例

```yaml
- include_role:
    name: vps.services.container_deployer
  vars:
    cdp_name: "flare"
    cdp_image: "{{ flare_image }}"
    cdp_dirs: ["app"]
    cdp_init_enabled: true
    cdp_init_dirs: ["app"]
    cdp_networks: [{name: "sweb"}]
    cdp_ports: ["30004:5005"]
    cdp_volumes: ["/opt/dockers/flare/app:/app"]
    cdp_command: "flare --nologin=0"
  tags: [deploy, services, docker_apps, flare, phase2]
```

## 变量说明

### 基础变量（必需）

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `cdp_name` | string | 应用名称，用于容器和目录命名 |
| `cdp_image` | string | Docker 镜像名称 |

### 目录配置

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_dirs` | list | [] | 需要创建的目录列表 |
| `cdp_base_path` | string | /opt/dockers | 数据存储根目录 |
| `cdp_dir_owner` | string | root | 目录所有者 |
| `cdp_dir_group` | string | root | 目录组 |
| `cdp_dir_mode` | string | 0755 | 目录权限 |

### 数据初始化

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_init_enabled` | bool | false | 是否从镜像初始化数据 |
| `cdp_init_dirs` | list | [] | 需要初始化的目录 |
| `cdp_init_container_path` | string | /app | 容器内对应路径 |

### 权限修正

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_fix_permissions` | bool | false | 是否递归修正权限 |
| `cdp_fix_uid` | string | 1000 | 修正后的 UID |
| `cdp_fix_gid` | string | 1000 | 修正后的 GID |
| `cdp_fix_mode` | string | 0777 | 修正后的权限 |

### 网络配置

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_networks` | list | [] | 网络配置列表 |
| `cdp_network_mode` | string | "" | network_mode（与 networks 互斥） |

### 容器配置

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_ports` | list | [] | 端口映射 ["30004:5005"] |
| `cdp_volumes` | list | [] | 卷挂载 |
| `cdp_env` | dict | {} | 环境变量 |
| `cdp_env_file` | string | "" | 环境变量文件路径 |
| `cdp_healthcheck` | dict | {} | 健康检查；通过本 Meta 角色部署的检查统一使用最小 `1800s` 间隔 |
| `cdp_command` | string | "" | 启动命令 |
| `cdp_user` | string | "" | 容器内用户 |
| `cdp_working_dir` | string | "" | 工作目录 |
| `cdp_recreate` | bool | false | 部署时强制重建同名容器；仅在调用方需要明确替换镜像或运行配置时启用 |

### 资源限制

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_capabilities` | list | [] | 容器能力 |
| `cdp_privileged` | bool | false | 特权模式 |
| `cdp_memory` | string | `512m` | 内存硬限制；显式空值也会回退到默认值 |
| `cdp_shm_size` | string | "" | 容器 `/dev/shm` 大小；Chromium 等共享内存密集型应用可设置为 `1g` |
| `cdp_cpu_shares` | int | "" | CPU 份额 |
| `cdp_cpus` | string | `1.0` | CPU 硬限制；显式空值也会回退到默认值 |
| `cdp_memory_reservation` | string | `128m` | 内存软预留；显式空值也会回退到默认值 |
| `cdp_oom_score_adj` | int | "" | OOM 评分调整 |

### 日志管理

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_log_driver` | string | json-file | 日志驱动 |
| `cdp_log_options` | dict | {max-size: 5m, max-file: 3} | 日志选项 |

### Compose 配置

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_compose_enabled` | bool | false | 是否使用 Compose |
| `cdp_compose_template` | string | "" | Compose 模板路径 |
| `cdp_compose_vars` | dict | {} | 传递给模板的变量 |
| `cdp_compose_build` | bool | false | 是否构建镜像 |
| `cdp_compose_pull` | string | missing | 拉取策略 |
| `cdp_compose_remove_orphans` | bool | false | 是否移除当前 Compose 文件中已不存在的旧服务容器；仅在服务边界收缩时显式启用。 |
| `cdp_compose_restart_after_deploy` | bool | true | `state: present` 收敛后是否再执行一次 Compose restart；遇到旧容器镜像已丢失等场景可由调用方关闭，避免冗余重启读取损坏状态。 |

### 钩子

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cdp_pre_tasks` | list | [] | 预部署任务列表 |
| `cdp_post_tasks` | list | [] | 后部署任务列表 |

## 标签

所有任务使用以下标签：

```yaml
tags: [deploy, services, container_deployer, phase2]
```

## 验证

```bash
make verify-services.container_deployer
```

## 回滚

```bash
make rollback-services.container_deployer
```

## 依赖

- `community.docker` collection
- Docker 引擎已安装

## 作者

AuroraOps Team


## 1. 概述
TODO: 补充此章节内容。

## 2. 变量说明
TODO: 补充此章节内容。

## 3. 内部逻辑
TODO: 补充此章节内容。

## 4. 依赖关系
TODO: 补充此章节内容。

## 5. 维护与排查
TODO: 补充此章节内容。
