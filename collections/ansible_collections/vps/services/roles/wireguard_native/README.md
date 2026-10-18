# Role: vps.services.wireguard_native

原生 Linux 内核 WireGuard 传输层角色，为 AuroraOps 节点提供零常驻内存开销的全互联网络与安全内网隧道。

## 合同与变量

- `wireguard_native_enabled`: 是否启用 (默认 false)
- `wireguard_native_role`: `server` 或 `client` (默认 client)
- `wireguard_native_interface`: 虚拟网卡接口名 (默认 `wg0`)
- `wireguard_native_address`: 本机 CIDR IP 地址 (如 `10.144.10.15/32`)
- `wireguard_native_port`: 服务端监听端口 (默认 `30059`)
- `wireguard_native_private_key`: 本机 WireGuard 私钥
- `wireguard_native_peers`: 对端列表配置
  - `public_key`: 对端公钥
  - `allowed_ips`: 允许路由网段 (如 `10.144.10.0/24` 或 `10.144.10.2/32`)
  - `endpoint`: 对端公网端点 (可选，客户端必填)
  - `persistent_keepalive`: 保活探测间隔秒数 (可选，默认 25)

## 生命周期保证

- `preflight`: 校验操作系统支持 (Debian / Ubuntu / Alpine) 与必要私钥/IP 参数。
- `deploy`: 安装 `wireguard-tools`，渲染权限为 `0600` 的配置文件，启动并启用 `wg-quick@wg0` systemd 服务。
- `verify`: 校验服务 active & enabled 状态及 `wg show` 命令执行正常。
- `rollback`: 停止并禁用 systemd 单元，自动清除虚拟网卡接口。
- `rollback_verify`: 独立断言服务处于 inactive / disabled 状态且接口已注销。

### 内部逻辑
- 原生部署 Linux 内核 WireGuard：渲染 `wg.conf.j2` 到 `wireguard_native_config_path`（默认 `/etc/wireguard/{{ wireguard_native_interface }}.conf`），由本角色自带 handler `restart wireguard_native` 触发 `systemd` 重启 `wg-quick@{{ wireguard_native_interface }}`（不依赖 `application_service`/`application_timer`）。
- 配置来自 `wireguard_native_peers`（含 `public_key`/`allowed_ips`/`endpoint`/`persistent_keepalive`），私钥取自 `wireguard_native_private_key`；Debian/Ubuntu 走 `apt`，Alpine 走 `apk` 安装 `wireguard-tools`。
- 健康检查直接读运行态内核接口：`wg show <iface> listen-port`、接口地址与 `latest-handshakes`，与运行配置比对，而非只看配置文件；客户端角色还要求至少一个 peer 完成过握手。

## 依赖与边界
- 仅支持 Debian / Ubuntu / Alpine；preflight 显式断言平台、以及 `wireguard_native_address`、`wireguard_native_private_key`、`wireguard_native_port` 均已配置（端口无默认值，强制从端口权威显式传入）。
- 监听端口 `wireguard_native_port` 与对端 `endpoint` 来自 playbook / host_vars 的端口分配，角色内部不维护 `ports.yml`；NAT 侧需放行对应 UDP 端口。
- 当前以 `wg-quick` systemd 单元收敛；依赖目标已加载内核 `wireguard` 模块（或对应内核支持），非 macOS `wireguard-go` 用户态方案。

## 维护与排查
- 查看接口: `wg show {{ wireguard_native_interface }}`；查看单元: `systemctl status wg-quick@{{ wireguard_native_interface }}`。
- 握手排查: 确认对端 `persistent_keepalive` 与 NAT 侧 UDP 放行；日志 `journalctl -u wg-quick@{{ wireguard_native_interface }}`。
- 重新收敛: 在控制节点重跑 `make deploy-services.wireguard_native`；失败多为私钥/地址/端口未配置或与端口权威不一致。

