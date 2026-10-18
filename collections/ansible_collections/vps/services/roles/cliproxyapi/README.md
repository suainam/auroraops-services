# Role: vps.services.cliproxyapi

Unified CLIProxyAPI gateway for AI CLI providers. `deploy_mode` is the only
platform switch: `native` installs a versioned binary under `/opt/cliproxyapi`
and runs it as a systemd service; `docker` runs
`eceasy/cli-proxy-api:v7.3.2` with a bind-mounted config.

## Overview

The role converges one CLIProxyAPI instance per host. It installs the binary,
renders the config, reconciles the provider auth files, and drives a daily
restart to pick up upstream credential refreshes. Both deploy modes expose the
**same** `cliproxyapi_*` variable interface — the `cliproxyapi_native_*` and
`docker_apps_cliproxyapi_*` aliases in `defaults/main.yml` exist only so the
mode-specific task files stay reusable, and are not the caller interface.

Two things a maintainer must know before touching anything:

1. **The storage driver decides Docker config mode, and nothing else does.**
   `cliproxyapi_object_store_active` is a pure function of
   `cliproxyapi_storage_driver == 's3'`. Inferring the mode from a non-empty
   endpoint is a trap: the R2 credentials live in the Vault, so the endpoint is
   set on *every* host regardless of intent. Inferring it made
   `storage_driver: file` powerless — the container stayed on the object store,
   the bind mounts never came back, and the role reported `changed` forever.
2. **File mode is authoritative by default.** Runtime config and credentials are
   preserved unless `cliproxyapi_force_overwrite: true`. That is why a normal
   deploy reports `changed=0`.

## Variables

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `cliproxyapi_enabled` | `true` | Master switch; installation and convergence. |
| `cliproxyapi_deploy_mode` | `native` | `native` or `docker`. The only platform switch. |
| `cliproxyapi_version` | `v7.3.9` | Native binary version. |
| `cliproxyapi_bind_address` | `127.0.0.1:30011` | Listen address; host/port are split from this. |
| `cliproxyapi_install_dir` | `/opt/cliproxyapi` | Native install prefix. |
| `cliproxyapi_data_dir` | `/opt/cliproxyapi/data` | Native runtime state. |
| `cliproxyapi_restart_hour` | `04` | Daily restart hour, rendered into a systemd calendar. |
| `cliproxyapi_gomemlimit_ratio` | `0.78` | `GOMEMLIMIT` as a fraction of the memory cap. |
| `cliproxyapi_force_overwrite` | `false` | Allow reconciling an existing runtime config. |
| `cliproxyapi_storage_driver` | `file` | `file` or `s3`; decides the Docker config mode. |
| `cliproxyapi_management_key` | Vault | Management API key. Never logged. |
| `cliproxyapi_api_keys` | Vault list | Client API keys. Never logged. |
| `cliproxyapi_ai_providers_file` | `group_vars/all/cliproxyapi_ai_providers.yml` | Provider declarations. |
| `cliproxyapi_auths_dir` | `inventories/files/cliproxyapi/auths` | Provider auth files. |
| `cliproxyapi_image` | `eceasy/cli-proxy-api:v7.3.2` | Docker image. |
| `cliproxyapi_arch_map` | see defaults | `ansible_architecture` → upstream release name. |

## Internal logic and dependencies

**Lifecycle files** — `preflight` → `install` → `configure` → `verify`, with
paired rollback paths per mode:

```
tasks/main.yml
├── preflight.yml          state capture, version/arch resolution
├── resolve.yml            checksum pin per architecture
├── install.yml
├── shared_credentials.yml auth file reconciliation
├── configure.yml
├── verify.yml
│   ├── verify_native.yml   or   verify_docker.yml
├── rollback.yml
│   ├── rollback_native.yml or   rollback_docker.yml
└── rollback_verify.yml
    ├── rollback_verify_native.yml or rollback_verify_docker.yml
```

**Native mode** downloads a pinned release and verifies it against
`cliproxyapi_checksums` before installing. An architecture that is not in
`cliproxyapi_arch_map` fails rather than guessing a release name.

**Docker mode** has two config sources, and the path differs between them:

| Mode | Container reads config from |
| :--- | :--- |
| `file` | `/opt/dockers/cliproxyapi/config.yaml` (bind mount) |
| `s3` | `/opt/dockers/cliproxyapi/objectstore/config/config.yaml` (server-side mirror) |

`cliproxyapi_docker_config_path` selects the one the container actually reads;
`cliproxyapi_docker_host_config_path` is the bind-mount source and is
deliberately a *separate* variable. A volume spec is assembled inside a Jinja
expression where each entry is a string literal, so a nested `{{ }}` is not
re-evaluated and reaches Docker verbatim, which rejects it as an invalid volume
name. Collapsing the two variables reintroduces that bug.

**Dependencies:**

- Vault keys `vault_cliproxyapi_management_key`, `vault_cliproxyapi_api_keys`.
- `group_vars/all/cliproxyapi_ai_providers.yml` and
  `inventories/files/cliproxyapi/auths` — absent files are not fatal; the role
  converges what exists.
- Docker mode needs the `sweb` network; `docker_apps` owns that network.
- Postgres mode uses `host.docker.internal`, so the role and the database must
  share a host.
- `cliproxyapi_docker_dns` is pinned to `8.8.8.8`/`8.8.4.8` deliberately: hosts
  like `cc15` disable IPv6 via sysctl while leaving IPv6 nameservers in
  `/etc/resolv.conf`, and the Go resolver treats an unreachable IPv6 nameserver
  as a whole-resolution failure, which turned R2 bootstrap into
  `network is unreachable`.

## Maintenance and troubleshooting

```bash
# native
systemctl status cliproxyapi
journalctl -u cliproxyapi -n 200 --no-pager
ls -l /opt/cliproxyapi

# docker
docker logs cliproxyapi --tail 200
ls -l /opt/dockers/cliproxyapi/ /opt/dockers/cliproxyapi/objectstore/config/ 2>/dev/null

# reachability from the host
curl -sS -m 5 http://127.0.0.1:30011/healthz
```

Common failures:

- **`changed` reported on every run** — usually the S3 mirror reconciling a path
  the container never reads. Check `cliproxyapi_storage_driver` actually equals
  `s3` before assuming the mirror is the problem.
- **`network is unreachable` during object-store bootstrap** — an IPv6 nameserver
  survived in the host's `/etc/resolv.conf`. Pin `cliproxyapi_docker_dns` to IPv4.
- **`unsupported architecture` at preflight** — the host's
  `ansible_architecture` is missing from `cliproxyapi_arch_map`; add it rather
  than relaxing the check.
- **Container never picks up config edits** — in `s3` mode the container reads
  the mirror, not the host path. Editing `/opt/dockers/cliproxyapi/config.yaml`
  changes nothing while `storage_driver` is `s3`.