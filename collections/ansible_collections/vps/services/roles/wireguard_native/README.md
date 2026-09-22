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
