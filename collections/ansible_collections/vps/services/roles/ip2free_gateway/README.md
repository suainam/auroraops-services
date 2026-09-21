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
