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
