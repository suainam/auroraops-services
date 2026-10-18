# ip2free_gateway

IP2Free 住宅代理网关 — 自动获取 SOCKS5 住宅代理节点，注入 Singbox 做出口路由。

## Architecture

```
hy2-resi inbound (hysteria2, port 30059, conditional on ip2free_gateway=true)
  └── route → 🏠 住宅代理 (urltest in 06_ip2free.json)
                └── SOCKS5 nodes (health-checked, dynamic)

ip2free_agent.py ──→ nodes.json ──→ health_check.py ──→ 06_ip2free.json
  (fetch nodes)        (store)        (test SOCKS5)      (urltest + singbox SIGHUP)
```

## Files

| File | Purpose |
|------|---------|
| `ip2free_agent.py` | Login → fetch nodes → captcha handling (skips click/manual/referral tasks) |
| `health_check.py` | Test SOCKS5 aliveness every 30min, update 06_ip2free.json, trigger agent refresh on all-dead |
| `update_outbounds.py` | Generate `06_ip2free.json` from alive nodes, SIGHUP singbox |

## Schedules

| Timer | Schedule | Default |
|-------|----------|---------|
| `ip2free-agent.timer` | Agent fetch nodes | `07,11,15,19,23:00:01` (4h interval, 7-23) |
| `ip2free-health.timer` | Health check | `*:0/30` (every 30min) |

Transient timeouts and connection failures are retried at most three times with
2s/4s backoff. Exhaustion records one structured degraded event, exits
successfully, and preserves the last-good `nodes.json`; the timer owns the next
attempt. Authentication and response-schema errors remain hard failures.

`nodes.json` is validated and published atomically from a temporary file in the
same directory. Rollback removes managed units but preserves `/opt/ip2free` data.

## All-Dead Auto-Refresh

When health check finds 0 alive nodes:
1. Writes fallback `06_ip2free.json` (selector → direct-out)
2. Starts `ip2free-agent.service` immediately (outside normal schedule)
3. 30min cooldown prevents retry storms

Control in `defaults/main.yml`:
- `COOLDOWN_PERIOD = 1800` (30 min, hardcoded in health_check.py)

## Singbox Integration

The `hy2-resi` inbound (port 30059) and route rule are rendered by singbox templates:
- `docker_apps/templates/singbox/inbounds_direct.json.j2` — hy2-resi inbound
- `docker_apps/templates/singbox/route_direct.json.j2` — hy2-resi → 住宅代理 rule
- `docker_apps/templates/singbox/06_ip2free.json.j2` — placeholder (overwritten by health check)

Condition: `{% if auroraops_roles['services']['ip2free_gateway'] %}`

The `🏠 resi-hy2` subscription node is defined in `inventories/group_vars/all/singbox_nodes.yml` with `external: true` (appears in subscription, not rendered as duplicate inbound).

## Dependencies

```
ip2free_gateway
  ├── vps.system.base                     (pip, aurora venv)
  ├── vps.personalization.user_management  (home dir for systemd)
  └── services.docker_apps.singbox        (config templates, routing)
```

## Deployment

```bash
make deploy-services.ip2free_gateway
make deploy-services.docker_apps.singbox
```

## Subscription Node

| Node | Type | Port | Tag |
|------|------|------|-----|
| `🏠 resi-hy2` | hysteria2 | 30059 | External proxy → residential SOCKS5 pool |

Note: The SOCKS5 backend nodes are NOT included in subscription (internal only).

## 变量与边界
- 关键变量: `auroraops_roles['services']['ip2free_gateway']`（总开关，须经 singbox 在 `direct` 模式且 `singbox` 在容器列表内才部署）、`ip2free_gateway_ip2free_config_file`（ip2free 配置文件）、`ip2free_gateway_ip2free_proxy_source`（上游代理源）、`ip2free_gateway_ip2free_schedule` / `ip2free_gateway_ip2free_health_schedule`（抓取/探活定时器）。
- 部署通过 `include_role` 依赖 `vps.system.base`（pip / aurora venv）、`vps.personalization.user_management`（systemd 家目录），以及 `services.docker_apps.singbox` 提供配置模板与路由；角色不在 `ports.yml` 内分配端口。
- 开关关闭时本角色的幂等清理块会停止并移除四个 systemd 单元与 `06_ip2free.json` 分片，避免残留定时器改写 sing-box 配置。

## 维护与排查
- 查看状态: `systemctl status ip2free-agent ip2free-health`；查看监听: `ss -ltnp | grep ip2free`。
- 出口排查: 确认 `ip2free_gateway_ip2free_config_file` 中配置的上游代理源可达且凭据来自 vault；日志 `journalctl -u ip2free-agent -u ip2free-health`。
- 重新收敛: 在控制节点重跑 `make deploy-services.ip2free_gateway`；失败多为 pip 依赖缺失或 singbox 未处于 direct 模式。
