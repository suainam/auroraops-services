# Role: vps.services.singbox

Unified sing-box proxy role supporting two runtimes. `singbox_deploy_mode`
(`docker` or `native`, or `auto` to detect) is the platform switch; every
variable below is shared by both branches.

## Overview

Converges one sing-box instance per host with Reality and Hysteria2 inbounds,
an optional relay pair, an optional userspace WireGuard outbound, and a
loopback SOCKS inbound that is the only way a guest without `CAP_NET_ADMIN` or
`/dev/net/tun` can originate mesh traffic.

Two structural facts that drive most of this role's defaults:

1. **`native` runs on OpenRC with `-C` (directory mode).** sing-box reads
   `*.json` fragments from the config dir, so the private key is read by the
   role at render time and shipped as a rendered variable, never as a separate
   config input — a `.key` file beside the fragments is inert to sing-box.
2. **`docker` runs `ghcr.io/sagernet/sing-box:v1.13.21`; `native` pins
   `1.13.11`.** The two are pinned on purpose and are not interchangeable; do
   not "fix" the mismatch without checking both branches' verify tasks.

`docker_apps_singbox_zero_rules: true` is zero-rule mode: no remote `rule_set`
downloads, no FakeIP DNS, no ruleset DNS rules. Default outbound stays
direct-out and Mesh/private/relay routing is untouched. It is off by default so
every non-NAT node keeps its full rules.

## Variables

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `singbox_enabled` | `true` | Master switch. |
| `singbox_deploy_mode` | `auto` | `docker`, `native`, or `auto` (runtime detection). |
| `singbox_version` | `1.13.11` | Native binary version. |
| `singbox_image` | `ghcr.io/sagernet/sing-box:v1.13.21` | Docker image. |
| `singbox_config_dir` | `/opt/dockers/singbox/config` | Docker config fragment dir. |
| `singbox_native_config_dir` | `/etc/sing-box` | Native config fragment dir (`-C`). |
| `singbox_native_workdir` | `/var/lib/sing-box` | Native state dir. |
| `singbox_reality_port` | `30052` | Reality inbound. |
| `singbox_hysteria_port` | `30051` | Hysteria2 inbound. |
| `singbox_relay_reality_port` | `30054` | Relay Reality inbound. |
| `singbox_relay_hysteria_port` | `30053` | Relay Hysteria2 inbound. |
| `singbox_web_port` | `10080` | Web panel. |
| `singbox_zero_rules` | `false` | Zero-rule mode (see `docker_apps_singbox_zero_rules`). |
| `singbox_reality_sni_candidates` | 2 entries | Reality SNI pool. |
| `singbox_reality_short_id_count` | `8` | Short IDs generated per listener. |
| `singbox_verify_rss_max_kb` | `0` (off) | Host-declared RSS ceiling in kB. |
| `singbox_verify_expected_tcp_ports` | `[]` | Defining this enables the listener contract check. |
| `singbox_verify_forbidden_ports` | `[]` | Retired-protocol ports asserted absent. |
| `singbox_verify_allow_udp_transport` | `false` | Exempts a userspace WireGuard transport socket from the UDP-listener assertion. |
| `singbox_verify_mesh_probe_target` | `""` (off) | Mesh data-path probe target, reached **through** the tunnel. |
| `singbox_verify_mesh_probe_port` | `0` | Port on the probe target. |
| `singbox_wireguard_enabled` | `false` | Userspace WireGuard outbound. |
| `singbox_wireguard_server_port` | `""` | Hub port. **Unset on purpose** — see Internal logic. |
| `singbox_wireguard_private_key` | `""` | Empty means generate on host; only the public half is registered. |
| `singbox_mesh_socks_enabled` | `false` | Loopback SOCKS inbound for guests without TUN. |
| `singbox_mesh_socks_listen` | `127.0.0.1` | Loopback-only; the role refuses a non-loopback listen. |

## Internal logic and dependencies

**Lifecycle files:** `preflight` → `resolve` → `common_prep` →
`configure_common` → (`docker.yml` | `native.yml`) → `verify` →
`verify_native` / `verify_docker` / `verify_config_contract`, with `rollback`
and `rollback_verify` pairing each branch.

**Verification seam (#179).** Every new check defaults to zero/off so a host
runs exactly the checks it ran before and opts into each one it can satisfy:

- A blank `singbox_verify_rss_max_kb` **disables** the RSS check. A host
  declares its own budget rather than inheriting one, because a ceiling that is
  wrong for the host is worse than no ceiling — it either fails a healthy node
  or passes an unhealthy one.
- Defining `singbox_verify_expected_tcp_ports` is what enables the listener
  contract. An empty list is "not declared", not "expect nothing".
- `singbox_verify_forbidden_ports` is asserted **absent** so a resurrected
  inbound from a retired protocol cannot pass unnoticed.
- `singbox_verify_allow_udp_transport` exists so the "no UDP listener"
  assertion can stay strict for everyone while recording that a userspace
  WireGuard endpoint holds one ephemeral transport socket.

**Mesh probe replaces a weaker check.** The earlier version only asserted the
loopback SOCKS socket was bound, which passes on a guest whose WireGuard
handshake never completed. The probe connects **through** the SOCKS to the
target instead of pinging: ICMP does not traverse SOCKS, and a direct ping to a
mesh address from a userspace guest is answered by the default gateway — a
false outage on a healthy tunnel.

**WireGuard port authority.** `singbox_wireguard_server_port` has **no default**
because it was `30059`, which is the port surrendered by the retired
residential proxy (#40) — the outbound would have kept dialling a port that now
means something else, reporting nothing. The hub's real port is the authority's
concern: `wireguard_udp_ports.hub`, overridden per host where the provider
forces it (`cc15` is pinned to `30071`). Both `singbox_wireguard_server_port`
and `singbox_wireguard_http_port` are empty on purpose: the endpoint only
renders when `singbox_wireguard_enabled` is true, and an empty value fails
loudly rather than quietly binding something already in use. Do not reintroduce
`| default(10080)` in the template.

**Slim binary path.** The Alpine package is a 46 MiB universal binary;
unpacking it inside a 64 MiB guest's cgroup gets the install OOM-killed, which
leaves an OpenRC init script with no binary behind it. When
`singbox_native_custom_binary: true`, the native branch installs
`singbox_native_slim_source` instead of managing the distro package and
**refuses to run without `singbox_native_slim_sha256`** — silently falling back
to `apk` is exactly what OOMs the guest.

**Dependencies:**

- `meta/main.yml` declares no role dependencies: `docker_apps` is invoked only
  in the docker branch, and `ports.yml` is the authority for every port above.
- Certificate domain comes from `docker_apps_singbox_certificate_domain`
  (default `suai.eu.org`).
- `singbox_socks_outbounds` credentials belong in the controller's Vault.
- WireGuard peers are reached over the mesh; the hub must already be converged.

## Maintenance and troubleshooting

```bash
# native (OpenRC)
rc-service sing-box status
rc-service sing-box restart
ls -l /etc/sing-box/

# docker
docker logs singbox --tail 200
ls -l /opt/dockers/singbox/config/

# what is actually listening
ss -lntup | grep -E '300(5[1-9])|10080'
```

Common failures:

- **RSS check fails on a healthy node** — `singbox_verify_rss_max_kb` was
  inherited rather than declared for that host. Set it from a measured value or
  zero it.
- **Mesh probe fails while the tunnel is up** — the probe reaches over SOCKS.
  Confirm `singbox_mesh_socks_enabled` and that the target port answers; a
  target of `0` disables the probe rather than failing it.
- **Hysteria2测速失败** — usually the port pair, not the client: Hysteria2 is
  `30051` and its relay is `30053`. Check `ports.yml` before the client config.
- **Slim install leaves an init script with no binary** — the guest was
  OOM-killed unpacking the 46 MiB universal package. Enable
  `singbox_native_custom_binary` with a pinned sha256.
- **Reality clients all fail after a redeploy** — `short_id` count or the SNI
  candidate pool changed. `singbox_reality_short_id_count` regenerating breaks
  previously issued small IDs; keep it stable once clients exist.