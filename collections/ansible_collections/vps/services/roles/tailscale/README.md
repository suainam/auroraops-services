# Role: vps.services.tailscale

Additive Tailscale transport pilot for Debian/systemd and Alpine/OpenRC nodes.
ZeroTier remains independent until an explicit migration is authorized.

## Contract

- `tailscale_enabled` controls installation and daemon convergence.
- `tailscale_auth_key` is private inventory/Vault input and is never logged.
- `tailscale_tags`, `tailscale_advertise_routes`, `tailscale_accept_routes`, and
  `tailscale_ssh_enabled` define the pilot network contract.
- Rollback stops and disables the daemon while preserving state by default.
- Verification records only daemon state and the assigned `100.64.0.0/10` IPv4
  address; it does not expose peer data or credentials.

Debian uses the distribution package and systemd. Alpine uses the `tailscale`
community package and OpenRC. The role does not claim support for other init
systems.

### 内部逻辑
- 增量部署 Tailscale 传输通道：Debian 走发行包 + systemd，Alpine 走 community 包 + OpenRC；不接管其他 init 系统。
- 单元由 `application_service`/`application_timer` 模板角色生成；auth key 来自 `tailscale_auth_key`（vault），从不日志打印。
- 收敛后记录守护进程状态与 `100.64.0.0/10` 地址；不暴露 peer 数据或凭据。

## 维护与排查
- 查看状态: `tailscale status` / `systemctl status tailscaled`。
- 重连排查: 确认 `tailscale_auth_key` 未过期且 `tailscale_enabled: true`；日志 `journalctl -u tailscaled`。
- 回滚: `make rollback-services.tailscale` 停止单元并保留状态。
