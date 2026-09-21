---
name: openviking
description: OpenViking - AI Agent 上下文数据库 Role
---

# OpenViking Role

## 1. 概述

本 Role 负责安装和配置 OpenViking - 开源上下文数据库，为 AI Agent 提供长期记忆和向量检索能力。

## 2. 变量说明

### 基础配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `openviking_enabled` | `true` | 是否启用安装 |
| `openviking_install_method` | `uv` | 安装方式 |
| `openviking_venv_path` | `/opt/openviking` | 虚拟环境路径 |
| `openviking_python_version` | `3.11` | Python 版本 |

### 服务配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `openviking_port` | `{{ app_port_openviking }}` | 服务端口 |
| `openviking_host` | `127.0.0.1` | 绑定地址 |
| `openviking_data_dir` | `/opt/openviking/data` | 数据目录 |
| `openviking_log_dir` | `/var/log/openviking` | 日志目录 |

### API 配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `openviking_embedding_api_base` | - | Embedding API 地址 |
| `openviking_embedding_api_key` | - | Embedding API Key |
| `openviking_embedding_model` | - | Embedding 模型 |
| `openviking_embedding_dimension` | `1536` | 向量维度 |
| `openviking_vlm_api_base` | - | VLM API 地址 |
| `openviking_vlm_api_key` | - | VLM API Key |
| `openviking_vlm_model` | - | VLM 模型 |

## 3. 内部逻辑

- **虚拟环境**: 使用 uv 创建 Python 3.11 虚拟环境
- **安装**: 通过 uv tool install 安装 openviking
- **配置**: 渲染 ov.conf.j2 模板到用户目录
- **服务**: 通过 application_service 元角色注册为 systemd 服务
- **启动**: systemd 管理服务启动并验证 health 端点

## 4. 依赖关系

- 操作系统: Debian / Ubuntu
- 必需: uv (通过 nodejs role 安装)
- 必需: application_service 元角色 (用于注册 systemd 服务)
- 端口: 使用 app_port_openviking 变量

## 5. 使用

### 部署
```bash
make deploy-applications.openviking
```

### 验证
```bash
make verify-applications.openviking
```

### 回滚
```bash
make rollback-applications.openviking
```

## 6. OpenCode 联动

在 host_vars 中配置 `opencode_personal_config` 以添加 OpenViking provider：

```yaml
openviking_enabled: true

# 在 opencode_personal_config 中添加 provider
opencode_personal_config:
  provider:
    openviking:
      npm: "@ai-sdk/openai-compatible"
      name: "OpenViking"
      options:
        baseURL: "http://127.0.0.1:{{ app_port_openviking }}"
        apiKey: ""
      models:
        chat:
          name: "glm-4-flash"
```

## 7. 维护与排查

- **查看日志**: `journalctl -u openviking -f`
- **检查进程**: `systemctl status openviking`
- **健康检查**: `curl http://127.0.0.1:30012/health`
- **重启服务**: `systemctl restart openviking`
- **停止服务**: `systemctl stop openviking`

## 8. 文件结构

```
~/.local/pipx/venvs/openviking/       # pipx venv
~/.local/share/uv/tools/openviking/    # uv tool 安装位置
~/.local/bin/openviking                # symlink
/root/.openviking/ov.conf            # 配置文件（本 role 管理）
/opt/openviking/data/                 # 数据目录
/etc/systemd/system/openviking.service # systemd 服务文件
```


## 5. 维护与排查
TODO: 补充此章节内容。
