---
# Ansible Test 角色

## 架构说明

支持**两种测试模式**：

### 本地模式（推荐）
直接在本地机器运行 Docker 容器进行测试，无需远程主机。

```
┌─────────────────────────────────────────────────────────────┐
│                    本地控制节点                              │
│  ├── 项目代码: $(pwd)                                       │
│  ├── Docker 镜像: auroraops-test-local                      │
│  │   └── 预装: ansible-core, ansible-lint, dependencies     │
│  └── ansible-playbook (local)                              │
│          └── community.docker.docker_container             │
└─────────────────────────────────────────────────────────────┘
                               │
                               │ docker API
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              本地 Docker 容器                                │
│  ├── 预装: Python, Ansible, community.general 等            │
│  ├── 挂载: 项目代码 (read-only)                             │
│  └── 执行: ansible-test integration                         │
└─────────────────────────────────────────────────────────────┘
```

### 远程模式（向后兼容）
通过 SSH 连接到远程主机，在远程主机上执行测试。

```
┌─────────────────────────────────────────────────────────────┐
│              本地 Docker 容器                                │
│  ├── 预装: Python, Ansible, community.general 等            │
│  ├── 挂载: 项目代码 (读写) + ~/.gitconfig                   │
│  └── 执行: ansible-test integration                         │
└─────────────────────────────────────────────────────────────┘
```

## 关键特性

1. **双模式支持**: 本地模式（默认）和远程模式
2. **自动镜像构建**: 部署时自动构建预构建镜像
3. **镜像持久化**: 镜像带 `dailycheckin_persist=true` 标签
4. **Cleanup 保护**: cleanup 角色不会删除测试镜像
5. **自动清理**: 容器测试后自动销毁

## 变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ansibletest_enabled` | `true` | 是否启用测试 |
| `ansibletest_mode` | `local` | 测试模式: `local` \| `remote` |
| `ansibletest_use_docker` | `true` | 是否使用 Docker |
| **本地模式** ||
| `ansibletest_local_image_name` | `auroraops-test-local` | 本地 Docker 镜像名 |
| `ansibletest_local_container_name` | `auroraops-test-runner` | 本地容器名 |
| `ansibletest_local_project_path` | `$(pwd)` | 本地项目路径 |
| **远程模式** ||
| `ansibletest_docker_image` | `auroraops-test-base` | 远程 Docker 镜像名 |
| `ansibletest_container_home` | `/root/ansible_collections` | 远程容器工作目录 |
| **通用** ||
| `ansibletest_build_image` | `true` | 部署时自动构建镜像 |

Docker 模式只做 CLI 和 daemon API 的只读 preflight；不会隐式部署 `services.docker`，也不会修改 socket 权限。全量部署顺序仍由 Catalog 保留。
| `ansibletest_force_rebuild` | `false` | 强制重新构建 |
| `ansibletest_target` | `system_base` | 测试目标 |

## 使用示例

### 本地测试（推荐）

```bash
# 1. 切换到本地部署模式
make switch_local

# 2. 构建本地测试镜像（首次或需要更新时）
make test-local-build

# 3. 测试单个角色
make test-local ROLE=system_base

# 4. 进入容器交互式 shell
make test-local-shell

# 5. 查看所有可用测试目标
make test-local-list

# 6. 清理本地容器
make test-local-clean

# 7. 完整清理（容器+镜像）
make test-local-full-clean
```

### 远程测试（向后兼容）

```bash
# 部署时自动构建镜像
make test-deploy

# 测试单个角色
make test-up ROLE=system_base

# 查看测试日志
make test-log ROLE=system_base

# 并行测试
make test-parallel ROLES="system_base system_ssh" JOBS=2

# 强制重新构建镜像
make test-deploy -e ansibletest_force_rebuild=true

# 切换到远程模式（显式指定）
make test-up ROLE=system_base -e ansibletest_mode=remote
```

## 镜像构建优化

### 缓存机制

构建命令支持缓存优化，会自动检测并使用已存在的镜像作为缓存：

```bash
# 首次构建（无缓存）
make test-local-build

# 再次构建（自动使用缓存）
make test-local-build  # 构建过程会更快，只更新变动的层

# 查看构建使用的缓存
make test-local-build 2>&1 | grep "cache-from"
```

### 构建要求

- 基础镜像：`debian:12-slim`
- 预装包：`ansible-core`, `ansible-lint`, `locales`
- 网络：需要访问 Docker Hub 或配置的镜像源

## 镜像管理

### 本地镜像

```bash
# 构建本地镜像（首次构建或更新代码后）
make test-local-build

# 查看本地镜像
docker images | grep auroraops-test-local

# 手动运行容器
docker run --rm \
    -v $(pwd):/workspace \
    --entrypoint /usr/local/bin/docker-entrypoint.sh \
    auroraops-test-local --target system_base

# 进入容器 shell
docker run -it --rm \
    -v $(pwd):/workspace \
    --entrypoint /bin/bash \
    auroraops-test-local
```

### 远程镜像

```bash
# 使用 Makefile 命令构建镜像（Ansible 模块执行）
make test-image-build

# 查看镜像
ansible cc15 -i inventories/prod.ini -m command -a "docker images | grep auroraops" -b

# 镜像保护标签
ansible cc15 -i inventories/prod.ini -m command -a "docker inspect auroraops-test-base --format '{{json .Config.Labels}}'" -b
```

## 测试目标

| 域 | 角色数 | 说明 |
|---|---|---|
| system | 14 | 系统基础配置 |
| services | 8 | Docker/Nginx 等服务 |
| applications | 5 | PostgreSQL/Redis 等应用 |
| personalization | 5 | Vim/Zsh 等个性化配置 |
| operations_loop | 8 | 备份/更新等运维 |
| observability | 2 | 监控/健康检查 |
| ci_cd | 2 | CI/CD Runner |

## 日志位置

| 类型 | 位置（远程模式） |
|------|------------------|
| 测试结果 (JSON) | `/tmp/ansibletest_parallel_*.json` |
| 详细日志 | `/var/log/ansibletest/{role}.log` |

## 镜像保护机制

```bash
# Dockerfile 添加保护标签
LABEL dailycheckin_persist="true"

# cleanup 角色排除规则
docker image prune -af \
    --filter=until=24h \
    --filter "image!=auroraops-test-local" \
    --filter "image!=auroraops-test-base" \
    --filter "image!=quay.io/ansible/*"
```

## 快速参考

```bash
# 常用本地命令
make test-local-build                    # 构建镜像
make test-local ROLE=system_base         # 测试角色
make test-local-shell                    # 进入容器
make test-local-list                     # 列出目标
make test-local-clean                    # 清理容器
make test-local-full-clean               # 完整清理

# 常用远程命令
make test-deploy                         # 部署测试环境
make test-up ROLE=system_base            # 测试角色
make test-log ROLE=system_base           # 查看日志
make test-parallel ROLES="..."           # 并行测试
```

## 经验教训与避坑指南

> 以下内容来自本地 Docker 容器测试的实际踩坑记录，务必在编写角色和测试目标时参考。

### ⚠️ 关键认知：测试目标文件路径

`ansible-test integration` **只读取 collection 内部的**测试目标：

```
✅ 正确路径 (ansible-test 实际读取)
collections/ansible_collections/vps/system/tests/integration/targets/test_xxx/

❌ 错误路径 (仅供 docker-entrypoint.sh 做存在性检查)
tests/integration/targets/test_xxx/
```

**修改测试目标后必须同步**到 collection 的 `tests/integration/targets/` 目录，否则 `ansible-test` 运行的是旧版本。

---

### 容器环境 vs 生产环境差异

Docker 容器（Debian 12-slim）与生产服务器（Debian 13 + systemd）有以下关键差异：

| 特性 | 生产环境 | Docker 容器 |
|---|---|---|
| init 系统 | systemd (PID 1) | `/bin/bash` (无 systemd) |
| `ansible.builtin.service` | ✅ 正常工作 | ❌ 找不到服务 |
| `ansible.builtin.systemd` | ✅ 正常工作 | ❌ `Can't operate` |
| `/etc/resolv.conf` | 可写 | ⛔ 只读挂载 (Device busy) |
| `/etc/udev/rules.d` | 存在 | ❌ 不存在 |
| `udevadm` | 可用 | ❌ 未安装 |
| `timedatectl` | 可用 | ❌ 需要 systemd |
| `service_facts` | 返回完整列表 | 返回空或不完整 |

---

### 编写容器兼容角色的规范

#### 1. 使用全局 `auroraops_has_systemd` Fact

`base` 角色（Phase 0）在最顶部设置了全局 Fact：

```yaml
# base/tasks/main.yml 顶部 (Phase 0 首个角色)
- name: 探测 init 系统类型
  ansible.builtin.command: pidof systemd
  register: _systemd_pid_check
  changed_when: false
  failed_when: false

- name: 设置全局 auroraops_has_systemd fact
  ansible.builtin.set_fact:
    auroraops_has_systemd: "{{ _systemd_pid_check.rc == 0 }}"
    cacheable: true
```

**其他角色直接引用**（含 fallback 防止独立执行时未定义）：

```yaml
# 在 service/systemd 相关任务上添加条件
- name: 启用并启动某服务
  ansible.builtin.service:
    name: my_service
    state: started
  when: auroraops_has_systemd | default(false) | bool
```

**独立部署的角色**需自行检测并设定 Fact（如 docker 角色）：

```yaml
- name: Detect systemd (fallback)
  ansible.builtin.command: pidof systemd
  register: _my_systemd_check
  changed_when: false
  failed_when: false
  when: auroraops_has_systemd is not defined

- name: Set local systemd fact
  ansible.builtin.set_fact:
    auroraops_has_systemd: "{{ _my_systemd_check.rc == 0 }}"
  when: auroraops_has_systemd is not defined
```

#### 2. 容器不兼容任务处理策略

| 任务类型 | 处理方式 |
|---|---|
| `ansible.builtin.service` | `when: auroraops_has_systemd` |
| `ansible.builtin.systemd` | 已有 `ignore_errors: true` 则保留；否则加 `when` |
| 修改 `/etc/resolv.conf` | `ignore_errors: true`（Docker 只读挂载） |
| `udevadm` 命令 | `ignore_errors: true`（容器无 udev） |
| handler 中的 service | `when: auroraops_has_systemd \| default(false) \| bool` |

#### 3. handler 中不支持 `block`

**Ansible handler 不支持 `block` 语法**。如需在 handler 中做分支：
- 方案 A：`when:` 条件 + 多个同名 handler（用 `listen`）
- 方案 B：`failed_when: false`（最简单但掩盖错误）
- 方案 C：**推荐** — `block` 在 handler 级别使用，内部用 `when` 分支（仅 Ansible 2.17+）

---

### 编写容器兼容测试目标的规范

测试目标（`tests/integration/targets/test_xxx/tasks/main.yml`）必须：

1. **开头检测 systemd**：
```yaml
- name: Check if systemd is available (container detection)
  ansible.builtin.command: pidof systemd
  register: test_systemd_check
  changed_when: false
  failed_when: false
```

2. **service_facts 加条件**：
```yaml
- name: Get service facts (only on systemd hosts)
  ansible.builtin.service_facts:
  when: test_systemd_check.rc == 0
```

3. **服务状态断言加条件**：
```yaml
- name: Verify service is running
  ansible.builtin.assert:
    that: ...
  when: test_systemd_check.rc == 0
```

4. **文件/命令断言用 `ignore_errors`**：
```yaml
- name: Validate config
  ansible.builtin.command: some_command -t
  register: cmd_result
  ignore_errors: true

- name: Assert config valid
  ansible.builtin.assert:
    that: "cmd_result.rc == 0"
  when: cmd_result.rc is defined and cmd_result.rc == 0
```

---

### 常见故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `Cannot retrieve result as auto_remove is enabled` | `docker_container` 的 `auto_remove: true` 导致容器在退出后被删除，无法读取结果 | 在 `run.yml` 中设为 `auto_remove: false` |
| `could not write config file /root/.gitconfig: Device or resource busy` | `.gitconfig` 以 `:ro` 挂载但 entrypoint 写入 | 移除 `.gitconfig` 挂载 |
| `Collection does not have a MANIFEST.json` | collection 缺少 `galaxy.yml` | 为 `vps/common` 等添加 `galaxy.yml` |
| 测试修改不生效 | 修改了 `tests/` 但 `ansible-test` 读 collection 内的副本 | 同步到 `collections/.../tests/integration/targets/` |
| `Service is in unknown state` | handler 中 `ansible.builtin.service` 在无 systemd 环境执行 | 使用 `when: auroraops_has_systemd` |
| `/etc/resolv.conf: Device or resource busy` | Docker 将 resolv.conf 作为特殊挂载 | `ignore_errors: true` |

---

### Checklist：提交前自检

- [ ] 角色中所有 `ansible.builtin.service` / `ansible.builtin.systemd` 任务是否加了 `when: auroraops_has_systemd` 或 `ignore_errors: true`？
- [ ] 角色的 `handlers/main.yml` 中是否有裸 `service` 调用？如有，是否加了条件？
- [ ] 测试目标是否在开头检测 systemd 并对服务断言加了 `when`？
- [ ] 修改的测试目标是否已同步到 collection 的 `tests/integration/targets/`？
- [ ] 是否有挂载 host 文件到容器（如 `.gitconfig`）但容器内会写入的情况？

