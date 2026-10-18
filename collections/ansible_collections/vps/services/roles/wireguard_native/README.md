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
- 原生部署 WireGuard：生成 `wg0.conf`（密钥来自 vault `wireguard_private_key`），渲染 systemd/OpenRC unit 由 `application_service`/`application_timer` 模板角色生成。
- Peer 列表来自 `wireguard_peers`，经 `wg0.conf.j2` 渲染；变更后 `wg syncconf` 热加载，不重建接口。
- 存活探活走 `wireguard_health_url`；密钥轮换通过 `rekey` 子任务单独处理。

## 依赖与边界
- 依赖内核 `wireguard` 模块（Linux）或 `wireguard-go`（macOS/用户态）；基础系统需已加载。
- 依赖 `application_service`/`application_timer` 模板角色就绪与 `python_executor` 解释器。
- 端口由 `ports.yml` 统一分配；NAT 侧需放行 UDP `wireguard_port`。

## 维护与排查
- 查看接口: `wg show wg0`；查看单元: `systemctl status wg-quick@wg0`。
- 握手排查: 确认对端 `PersistentKeepalive` 与 NAT 侧 UDP 放行；日志 `journalctl -u wg-quick@wg0`。
- 重新渲染: 在控制节点重跑 `make deploy-services.wireguard_native`；失败多为密钥缺失或端口冲突。

