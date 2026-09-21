# easytier

EasyTier 组网角色 — 基于 Docker 的轻量级 mesh VPN，支持虚拟 IP、子网代理、exit node 等功能。

## Architecture

```
EasyTier Container (host network mode)
  │
  ├── TUN device (/dev/net/tun) — 虚拟网卡
  ├── config volume — /config/easytier.toml (from /opt/easytier/)
  └── machine-id volume — 持久化节点身份
       │
       ├── Listen mode (cc15): tcp+udp :11010 ←— 对等节点连接
       └── Peer mode (local):  → tcp+udp → cc15:11010
```

## Files

| File | Purpose |
|------|---------|
| `tasks/main.yml` | 部署入口：加载 TUN 模块 → 创建配置目录 → 渲染模板 → 开放端口 → 启动容器 |
| `tasks/verify.yml` | 验证：容器运行、配置挂载、网络名称、节点状态 |
| `tasks/rollback.yml` | 回滚：停止容器、删除配置、关闭端口 |
| `templates/easytier.toml.j2` | EasyTier 配置文件模板 |
| `defaults/main.yml` | 所有可配置变量及默认值 |
| `handlers/main.yml` | 配置变更后 restart easytier 容器 |

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `easytier_image` | `easytier/easytier:latest` | Docker 镜像 |
| `easytier_network_name` | `auroraops` | 网络标识（同一网络必须一致） |
| `easytier_network_secret` | vault | 网络密钥 |
| `easytier_ipv4` | `""` | 虚拟 IP（子网内唯一） |
| `easytier_dhcp` | `false` | 是否启用 DHCP 分配 IP |
| `easytier_listen` | `true` | 监听模式（等待连接） |
| `easytier_listen_port` | `11010` | 监听端口 |
| `easytier_peers_global` | `[]` | 对等节点列表（全局） |
| `easytier_peers_host` | `[]` | 对等节点列表（主机追加） |
| `easytier_peers_exclude` | `[]` | 排除的对等节点 |
| `easytier_subnet_proxies_*` | `[]` | 共享子网列表（三层分层） |
| `easytier_exit_nodes` | `[]` | 退出节点列表 |
| `easytier_vpn_portal_wg` | `""` | WireGuard 门户配置 |
| `easytier_tun_device` | `/dev/net/tun` | TUN 设备路径 |

## Host Configuration Examples

### cc15 — 监听节点（Server）

```yaml
# inventories/host_vars/cc15.yml
easytier_ipv4: "10.8.8.1"
easytier_listen: true
easytier_network_name: "auroraops"
easytier_network_secret: "{{ vault_easytier_secret }}"
```

### hdy — 对等节点（Client）

```yaml
# inventories/host_vars/hdy.yml
easytier_ipv4: "10.8.8.2"
easytier_listen: false
easytier_network_name: "auroraops"
easytier_network_secret: "{{ vault_easytier_secret }}"
easytier_peers_host:
  - "tcp://cc15.msuai.top:11010"
```

## Dependencies

- Role Catalog 保留 `vps.services.docker` 作为全量部署顺序依赖。
- 定向执行 `easytier` 时只通过只读 preflight 检查 Docker daemon，不执行完整 Docker Role。
- 容器部署逻辑由参数化 Meta Role `vps.services.container_deployer` 提供。
- Docker 不可用时会在修改 EasyTier 配置前明确失败，并提示先部署 `services.docker`。

## Deployment

```bash
make check-services.easytier      # dry-run 验证
make deploy-services.easytier     # 部署
make verify-services.easytier     # 验证
make rollback-services.easytier   # 回滚
```

## Verification

角色验证包括：
1. 容器是否运行
2. 配置文件是否正确挂载
3. 网络名称是否匹配
4. 节点状态是否正常（`easytier-cli node`）

## Lessons Learned

### 1. TOML `listeners` 配置可能不生效，需 CLI flags 兜底

**问题**: 即使 `easytier.toml` 正确配置了 `listeners = ["tcp://0.0.0.0:11010", ...]`，easytier 仍可能监听默认端口 15888（RPC 端口）。

**根因**: `-c /config/easytier.toml` 启动时 TOML 中的 listen 配置未被完全解析。

**修复**: 在 `cdp_command` 中同时传递 CLI flags 强制生效：
```yaml
cdp_command: >-
  -c /config/easytier.toml
  {% if easytier_listen | bool %}-l tcp://0.0.0.0:{{ easytier_listen_port }} -l udp://0.0.0.0:{{ easytier_listen_port }}{% endif %}
```
CLI flags 优先级高于 TOML 配置，确保监听端口正确。

### 2. 默认端口：peer 11010 ≠ RPC 15888

| 用途 | 默认端口 | 说明 |
|------|---------|------|
| Peer 连接 (TCP/UDP) | 11010 | 节点间 mesh 通信 |
| RPC 管理 (CLI/Web) | 15888 | `easytier-cli` 和 Web 控制台 |
| WebSocket | 11011 | 备用传输层 |
| WireGuard | 11013 | WG 客户端集成 |

Peer URL 必须显式指定端口，不要依赖默认值：
```
tcp://host:11010    # ✅ 正确
tcp://host          # ❌ 依赖默认端口，行为不明确
```

### 3. Host 网络模式下 Nginx stream 代理画蛇添足

easytier 使用 `--network=host` 时直接绑定宿主机端口，无需 Nginx TCP/UDP stream 代理。如果同时配置了 Nginx stream 代理监听同一端口，会导致端口冲突。

如果已有 Nginx stream 配置（如 `/etc/nginx/stream.d/easytier.conf`），确认 nginx.conf 未引用 `stream.d` 目录后可直接删除。

### 4. `easytier-cli peer` 可能不显示所有对端

**现象**: cc15 侧 `easytier-cli peer` 正确显示 localhost，但 localhost 侧不显示 cc15。此时双向 ping 仍然正常（0% 丢包）。

**结论**: `easytier-cli peer` 输出有时滞后或有显示问题。**验证连通性的可靠方法是直接 ping 虚拟 IP**，而非依赖 CLI 输出。

### 5. Peer URL 端口必须与服务端 Listener 端口一致

```
客户端 peer URL:  tcp://server.domain:11010
服务端 listener:  tcp://0.0.0.0:11010
```
两端端口必须匹配。如果不加端口，EasyTier 的行为可能不符合预期。

## Notes

- 使用 `host` 网络模式，无需端口映射
- 需要 `NET_ADMIN` + `NET_RAW` capabilities
- 依赖 TUN 模块（`modprobe tun`），任务中自动加载
- 防火墙端口仅在 `easytier_listen=true` 时自动放行
- peer 列表使用 AuroraOps 三层变量合并（global + host - exclude）
