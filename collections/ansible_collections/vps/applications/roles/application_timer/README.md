# Role: vps.applications.application_timer

## 1. 概述
该角色是一个**元角色（Meta Role）**，用于将任意定时任务封装为 Systemd Timer。它负责创建 Timer 配置文件并管理 Timer 状态。

**⚠️ 重要说明**：
- 此角色**不应该直接部署**，而是通过 `include_role` 被其他角色调用
- 启用控制**完全由调用方决定**，不受 `auroraops_roles['applications']['application_timer']` 影响
- 与 `container_deployer` 保持一致的设计模式
- `roles.yml` 中的 `application_timer: false` 配置**已废弃**，不再生效

## 2. 变量说明

### 必需变量
| 变量名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `app_timer_name` | string | Timer 名称（必填，对应的 service 必须存在）。 |
| `app_timer_on_calendar` | string | Timer 调度时间（必填，例如 `*-*-01 02:00:00`、`daily`、`weekly`）。 |

### 可选变量
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `app_timer_description` | `"Generic Application Timer"` | Timer 描述。 |
| `app_timer_accuracy` | `""` | Timer 精度（可选，例如 `1m`、`5m`）。 |
| `app_timer_persistent` | `true` | 是否持久化（系统关机后是否补执行）。`false` 时系统重启后不补执行错过的任务。 |
| `app_timer_randomized_delay` | `""` | 随机延迟（可选，例如 `1h`）。 |
| `app_timer_enabled` | `true` | 是否启用 Timer（实例级别控制）。 |
| `app_timer_state` | `started` | Timer 状态（started/stopped/restarted）。 |

## 3. 内部逻辑
- **Systemd Timer**: 渲染 `application.timer.j2` 模板到 `/etc/systemd/system/`。
- **生命周期**: 处理 `daemon-reload` 并确保 Timer 按预期状态运行。
- **依赖关系**: Timer 会自动触发同名的 service（如 `myapp.timer` 触发 `myapp.service`）。

## 4. 使用示例

### 示例 1：基础定时任务（cleanup 角色）

```yaml
- name: Create Docker maintenance prune timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: docker-maintenance-prune
    app_timer_description: Docker Maintenance Prune Timer
    app_timer_on_calendar: '{{ docker_prune_timer_on_calendar | default("*-*-01/3 03:00:00") }}'
    app_timer_randomized_delay: "30m"
  when: auroraops_roles['operations_loop']['cleanup'] | default(true) | bool
  tags: [deploy, cleanup_system, cleanup, operations_loop, phase6]
```

**关键点**：
- ✅ `when` 条件检查**调用方角色**（`cleanup`），而不是元角色本身
- ✅ `app_timer_on_calendar` 使用变量，支持主机级别覆盖
- ✅ `app_timer_randomized_delay` 避免多台服务器同时执行

### 示例 2：每日定时任务（health_checks 角色）

```yaml
- name: Create health check timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: health_check_runner
    app_timer_description: Health Check Runner Timer
    app_timer_on_calendar: "daily"
    app_timer_accuracy: "1m"
  when: auroraops_roles['observability']['health_checks'] | default(true) | bool
  tags: [deploy, observability, health_checks, phase5]
```

**关键点**：
- ✅ 使用 `daily` 简化配置（等同于 `*-*-* 00:00:00`）
- ✅ 使用 `app_timer_accuracy` 设置精度（允许 1 分钟误差）

### 示例 3：每周定时任务（audit 角色）

```yaml
- name: Create security audit timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: security-audit
    app_timer_description: Security Audit Timer
    app_timer_on_calendar: "weekly"
    app_timer_persistent: true
    app_timer_randomized_delay: "2h"
  when: auroraops_roles['operations_loop']['audit'] | default(true) | bool
  tags: [deploy, operations_loop, audit, phase6_8]
```

**关键点**：
- ✅ 使用 `weekly` 简化配置（等同于 `Mon *-*-* 00:00:00`）
- ✅ `persistent: true` 确保系统关机期间错过的任务会在启动后执行
- ✅ `randomized_delay: 2h` 在 2 小时内随机延迟执行

## 5. ❌ 错误示例（避免）

### 错误 1：检查元角色的启用状态

```yaml
# ❌ 错误：检查元角色本身的启用状态
- name: Create my timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: my-timer
    app_timer_on_calendar: "daily"
  when: auroraops_roles['applications']['application_timer'] | default(true) | bool  # ❌ 错误！
```

**问题**：`application_timer` 在 `roles.yml` 中设置为 `false`，导致 timer 永远不会创建。

**正确做法**：
```yaml
# ✅ 正确：检查调用方角色的启用状态
when: auroraops_roles['my_domain']['my_role'] | default(true) | bool
```

### 错误 2：忘记创建对应的 service

```yaml
# ❌ 错误：只创建 timer，没有创建对应的 service
- name: Create my timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: my-task
    app_timer_on_calendar: "daily"
  # ❌ 缺少对应的 application_service 调用
```

**问题**：Timer 会触发 `my-task.service`，但该 service 不存在，导致执行失败。

**正确做法**：
```yaml
# ✅ 正确：先创建 service，再创建 timer
- name: Create my service
  ansible.builtin.include_role:
    name: vps.applications.application_service
  vars:
    app_service_name: my-task
    app_service_exec_start: /usr/local/bin/my-task.sh

- name: Create my timer
  ansible.builtin.include_role:
    name: vps.applications.application_timer
  vars:
    app_timer_name: my-task
    app_timer_on_calendar: "daily"
```

## 6. Systemd Calendar 格式参考

### 常用格式

| 格式 | 说明 | 等价于 |
|------|------|--------|
| `daily` | 每天午夜 | `*-*-* 00:00:00` |
| `weekly` | 每周一午夜 | `Mon *-*-* 00:00:00` |
| `monthly` | 每月 1 号午夜 | `*-*-01 00:00:00` |
| `yearly` | 每年 1 月 1 号午夜 | `*-01-01 00:00:00` |
| `hourly` | 每小时 | `*-*-* *:00:00` |

### 自定义格式示例

```
格式: Year-Month-Day Hour:Minute:Second
示例:
  *-*-* 02:00:00        # 每天凌晨 2 点
  *-*-01 03:00:00       # 每月 1 号凌晨 3 点
  *-*-01/3 03:00:00     # 每 3 天凌晨 3 点（1, 4, 7, 10...）
  Mon *-*-* 09:00:00    # 每周一上午 9 点
  *-*-* 00/6:00:00      # 每 6 小时（0:00, 6:00, 12:00, 18:00）
```

### 验证格式

```bash
# 验证 calendar 格式是否正确
systemd-analyze calendar "daily"
systemd-analyze calendar "*-*-01/3 03:00:00"
```

## 7. 依赖关系
- 依赖于 `ansible.builtin` 核心模块。
- 需要 systemd 支持（Debian 12 默认）。
- **必须先创建对应的 service**，timer 才能正常工作。

## 8. 维护与排查

### 查看 Timer 状态
```bash
systemctl status <app_timer_name>.timer
```

### 查看 Timer 日志
```bash
journalctl -u <app_timer_name>.timer -f
```

### 查看下次触发时间
```bash
systemctl list-timers <app_timer_name>.timer
```

### 手动触发 Timer
```bash
systemctl start <app_timer_name>.service  # 直接触发 service
```

### 查看 Timer 配置
```bash
cat /etc/systemd/system/<app_timer_name>.timer
```

## 9. 设计原则

**元角色的三大原则**：

1. **被动调用**：元角色不应该有自己的 `auroraops_roles` 检查
2. **调用方控制**：启用与否完全由调用方的 `when` 条件决定
3. **实例级别开关**：保留 `app_timer_enabled` 用于控制单个 timer 实例

**与 `container_deployer` 保持一致**：
- ✅ 无 `auroraops_roles` 检查
- ✅ 不在 `roles.yml` 中定义
- ✅ 完全由调用方控制

## 10. 相关元角色

- `vps.applications.application_service` - 创建 systemd service
- `vps.services.container_deployer` - 部署 Docker 容器
- `vps.services.nginx` (meta_site.conf.j2) - 生成 Nginx 站点配置


## 4. 依赖关系
TODO: 补充此章节内容。

## 5. 维护与排查
TODO: 补充此章节内容。
