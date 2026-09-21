# Cloudflared

This role manages a Cloudflare Named Tunnel connector on Debian/systemd and Alpine/OpenRC hosts.

The connector uses an official locally configured Cloudflare Named Tunnel. The pinned release package is verified with an architecture-specific SHA-256 before root installation. Downloads honor the host `proxy_http` and `proxy_https` settings; `rasp` uses its loopback Hysteria2 HTTP proxy. AuroraOps renders `/etc/cloudflared/config.yml` and a mode `0600` tunnel credentials file from encrypted Vault data; secrets are never embedded in the systemd unit or command output. The ingress maps `bws-dr-test.msuai.top` and the reserved production hostname to `http://127.0.0.1:30007`, followed by a 404 catch-all.

Normal operation keeps the connector enabled while the Pi Vaultwarden container remains stopped. Connector readiness and application health are deliberately separate. A connected Tunnel with a stopped backend must return a non-200 origin error rather than being treated as a healthy application.

When the connector is enabled, the role also installs a small readiness watchdog. It reuses the local `cloudflared_metrics_url` (`/ready` by default), records consecutive failures under `/var/lib/cloudflared-watchdog`, and restarts `cloudflared` after three failed probes. On systemd hosts the probe runs through the shared `application_service`/`application_timer` roles once per minute; on Alpine/OpenRC it runs as a lightweight supervised loop. Probe failures are written through `logger` so they are available in the host service logs.

The watchdog can be disabled or tuned with `cloudflared_watchdog_enabled`, `cloudflared_watchdog_failure_threshold`, `cloudflared_watchdog_schedule`, `cloudflared_watchdog_on_boot_sec`, and `cloudflared_watchdog_timeout_seconds`. It is gated by the connector role and does not run when `cloudflared_enabled` is false.

Docker is not a connector dependency. `cloudflared_verify_vaultwarden_backend` retains the optional passive-container checks; native backends disable that check and verify their own application health. On `rasp`, the only managed ingress is `clip.suainam.eu.org`, forwarding to native CLIProxyAPI on loopback port 30011.

## Lifecycle

```bash
make switch_remote.rasp
make env_show
make check-services.cloudflared
make deploy-services.cloudflared
make verify-services.cloudflared
make rollback-services.cloudflared
```

Rollback removes only the managed package/binary, connector and watchdog units, watchdog script/state, configuration, and host credential file. It preserves the Named Tunnel, encrypted source credentials, Vaultwarden data, and standby snapshots so the same Tunnel can be redeployed.

DNS mutation is disabled by default. An explicitly configured `cloudflared_dns_hostname` and `cloudflared_dns_zone` enroll one proxied CNAME for an existing custom ingress through the normal Make lifecycle. Preflight refuses unrelated existing records, and a separate ownership baseline lets rollback remove only a record originally created by the role. Credentials remain in Vault and API operations use `no_log`. The separate Vaultwarden test-domain drill remains restricted to `bws-dr-test.msuai.top` and retains its explicit authorization and backup guards.

The legacy `https://bws-vps-health.msuai.top/alive` endpoint belongs to cc15, not the current qqg1299 primary. For current primary health checks and promotion eligibility, follow the [Vaultwarden standby contract](../../../operations_loop/roles/vaultwarden_standby/README.md#人工接管-cli).
