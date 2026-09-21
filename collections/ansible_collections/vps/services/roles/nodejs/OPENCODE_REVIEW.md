# OpenCode Ansible 配置审查报告

## 📋 审查日期
2026-03-28

## ✅ ECC (Everything Claude Code) 集成概览

本次更新将 `everything-claude-code` 仓库中的优秀实践集成到 AuroraOps OpenCode 部署流程中，增强安全审查、规划、文档、重构和权限控制能力。

### 文件结构

```
collections/ansible_collections/vps/services/roles/nodejs/
├── tasks/
│   ├── opencode.yml                    # 主入口（含 opencode_ecc）
│   ├── opencode_install.yml            # 安装任务
│   ├── opencode_config.yml             # 全局配置
│   ├── opencode_project_config.yml     # 项目配置
│   ├── opencode_antigravity.yml        # Antigravity 认证
│   ├── opencode_ecc.yml                # ECC 集成部署（新增）
│   └── opencode_server.yml             # Server 模式
├── templates/
│   ├── prompts/agents/                 # Agent Prompt 模板（新增）
│   │   ├── planner.txt.j2
│   │   ├── security-reviewer.txt.j2
│   │   ├── doc-updater.txt.j2
│   │   └── refactor-cleaner.txt.j2
│   ├── commands/                       # Command 模板（新增）
│   │   ├── plan.md.j2
│   │   ├── security.md.j2
│   │   ├── update-docs.md.j2
│   │   ├── update-codemaps.md.j2
│   │   └── refactor-clean.md.j2
│   ├── plugins/                        # Plugin 模板（新增）
│   │   ├── session-audit.js.j2
│   │   └── permission-gate.js.j2
│   ├── opencode.json.j2                # 全局配置模板
│   └── opencode_project.json.j2        # 项目配置模板
├── vars/
│   ├── opencode_base.yml               # 基础配置
│   ├── opencode_providers.yml          # 提供商配置
│   ├── opencode_mcp.yml                # MCP 服务器配置
│   └── opencode_project.yml            # 项目配置（已更新：ECC 集成）
└── defaults/
    └── main.yml                        # 默认变量
```

## 🆕 新增功能

### 1. Agent 扩展（4 个新 Agent）

| Agent | 用途 | Prompt 来源 |
|-------|------|-------------|
| `planner` | 实施计划专家 | `{file:prompts/agents/planner.txt}` |
| `security-reviewer` | 安全审查专家 | `{file:prompts/agents/security-reviewer.txt}` |
| `doc-updater` | 文档与 Codemap 专家 | `{file:prompts/agents/doc-updater.txt}` |
| `refactor-cleaner` | 重构与清理专家 | `{file:prompts/agents/refactor-cleaner.txt}` |

**原有的 `doc-writer` 已被 `doc-updater` 替代**，增加 Role Codemap 生成和文档一致性验证功能。

### 2. Command 扩展（5 个新命令）

```bash
/plan              # 创建实施计划
/security          # 安全审查
/update-docs       # 更新文档
/update-codemaps   # 更新 Codemap
/refactor-clean    # 清理冗余代码
```

### 3. Plugin 扩展（2 个新 Plugin）

| Plugin | 功能 |
|--------|------|
| `session-audit.js` | Session 结束审计：检查 `debug: yes`、明文密码、缺失 tags、vault 直接编辑 |
| `permission-gate.js` | 精细化权限控制：auto-approve 读操作，ask 其他操作 |

### 4. Instructions 扩展

```yaml
instructions:
  - "AGENTS.md"
  - ".opencode/skill/auroraops/SKILL.md"
  - ".opencode/skills/ansible-builder/SKILL.md"
  - ".opencode/skills/ansible-deployer/SKILL.md"
  - ".opencode/skills/ansible-troubleshooter/SKILL.md"
```

## 📦 部署方式

### ECC 集成部署

```bash
# 部署完整的 OpenCode + ECC 集成（需要 nodejs_apps 中包含 opencode）
make deploy-services.nodejs.opencode

# 验证部署
make verify-services.nodejs.opencode
```

### 单独部署命令

```bash
# Agent prompts
make deploy-services.nodejs.opencode_ecc

# Command 模板
make deploy-services.nodejs.opencode_project_config

# Plugins
make deploy-services.nodejs.opencode_ecc
```

### 触发条件

在 `host_vars/<host>.yml` 中需要配置：

```yaml
# 启用 OpenCode 应用
nodejs_apps_host:
  - opencode

# 启用项目配置（ECC 集成需要）
opencode_enabled: true
opencode_project_enabled: true

# 可选：OpenCode Server
opencode_server_enabled: true
```

## 🔧 本次更新内容

### `vars/opencode_project.yml` 更新

1. **Plugin 配置**: 添加 `plugin: ["./plugins"]`
2. **更新 Agent**: 
   - 移除 `doc-writer`
   - 新增 `doc-updater`（含 Codemap 生成能力）
   - 新增 `planner`
   - 新增 `security-reviewer`
   - 新增 `refactor-cleaner`
3. **更新 Command**:
   - `/doc` agent 改为 `doc-updater`
   - 新增 `/plan`, `/security`, `/update-docs`, `/update-codemaps`, `/refactor-clean`
4. **扩展 Instructions**: 追加 4 个 skill 路径

### `tasks/opencode_project_config.yml` 更新

新增任务：确保项目目录存在

```yaml
- name: Ensure project directory exists
  ansible.builtin.file:
    path: "{{ opencode_project_dir }}"
    state: directory
```

### `tasks/opencode.yml` 更新

新增 ECC 集成任务 include：

```yaml
- name: Include OpenCode ECC integration tasks
  ansible.builtin.include_tasks: opencode_ecc.yml
  when: opencode_project_enabled | default(false) | bool
```

### `tasks/opencode_ecc.yml` 新建

部署任务：
- Agent prompt 文件 → `.opencode/prompts/agents/`
- Command 模板文件 → `.opencode/commands/`
- Plugin 文件 → `.opencode/plugins/`

## ✅ 验证结果（cc15 主机）

```
✅ OpenCode CLI:     v1.1.65
✅ Root config:      EXISTS
✅ Admin config:     EXISTS
✅ Service:          active / enabled / PID 24467
✅ Port 4096:        LISTENING
⚠️  Health endpoint:  401 (需要认证，预期行为)

Agents:      ansible-expert, code-reviewer, doc-updater, planner, refactor-cleaner, security-reviewer
Commands:    check-role, deploy-role, doc, plan, refactor-clean, review, security, update-codemaps, update-docs
Instructions: AGENTS.md + 4 skill paths
Plugins:     ./plugins (含 session-audit.js, permission-gate.js)
```

## 📱 Web 访问

- **URL**: https://opencode-test.suai.eu.org/
- **认证**: 需要密码（由 `opencode_server_password` 配置）
- **状态**: HTTP 401（正常，需要 Basic Auth）

## 📚 相关文档

- [ECC 集成方案](../../../../../../docs/plans/archive/ecc_integration_plan.md) - 历史实施方案
- [.opencode/README.md](../../../../../../.opencode/README.md) - Skill 使用说明
- [.opencode/SETUP.md](../../../../../../.opencode/SETUP.md) - 环境配置指南
- [AGENTS.md](../../../../../../AGENTS.md) - Agent 操作指南

## 🎯 最佳实践

### 1. 使用新 Agent

```bash
# 在 OpenCode 中使用 Planner 创建实施计划
/plan 新增一个 nginx 站点配置

# 使用 Security Reviewer 扫描安全风险
/security vps.services.nginx

# 使用 Doc Updater 更新文档
/update-docs system.firewall
```

### 2. 使用新 Command

```bash
# 创建实施计划
/plan 为 NAS 配置一个新的 Docker 应用

# 安全审查
/security collections/ansible_collections/vps/services/roles/nginx

# 更新文档
/update-docs services.nodejs

# 更新 Codemap
/update-codemaps services.nginx

# 清理冗余代码
/refactor-clean services.docker_apps
```

### 3. 验证部署

```bash
# 部署后验证
make verify-services.nodejs.opencode
```

## ⚠️ 注意事项

1. **ECC 集成依赖项目目录**: `opencode_project_enabled: true` 需要项目目录存在
2. **Prompt 模板需生效**: 需要重新部署 `opencode_project_config` 后 Agent Prompt 才可用
3. **Plugin 需要重启**: 新增的 plugin 需要重启 OpenCode Server 使其生效
4. **权限控制**: `permission-gate.js` 会自动批准安全操作，危险操作需要确认
5. **Session Audit**: Session 结束时会自动扫描编辑的 YAML/J2 文件

## 🔗 官方资源

- 官网: https://opencode.ai
- 文档: https://opencode.ai/docs
- GitHub: https://github.com/opencode-ai/opencode
- ECC 源仓库: https://github.com/affaan-m/everything-claude-code
