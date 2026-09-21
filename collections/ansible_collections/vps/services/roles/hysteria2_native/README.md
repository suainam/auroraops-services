# Hysteria2 Native Role (`vps.services.hysteria2_native`)

## 概述

`vps.services.hysteria2_native` 角色为 Linux 节点（支持 ARM64 与 AMD64，如树莓派 rasp）提供原生的 systemd Hysteria2 客户端服务。

相比容器化 Hysteria2 方案，原生 systemd 模式具备更低内存开销、零 Docker 桥接网络损耗、并在宿主机 loopback 直接暴露 SOCKS5 与 HTTP 端口。

## 监听与网络架构

- **单端口混合代理 (SOCKS5 + HTTP/HTTPS)**: `127.0.0.1:10808`
- 依据 Hysteria 2.4.1+ 单端口混合监听能力，将 `socks5.listen` 与 `http.listen` 绑定至同一地址，少开 10809 端口。
- 仅监听 loopback 回环接口（`127.0.0.1`），避免向局域网未授权暴露。

## 变量说明

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `hysteria2_native_enabled` | `{{ auroraops_roles['services']['hysteria2_native'] \| default(false) }}` | 是否启用该角色 |
| `hysteria2_native_version` | `"2.12.3"` | 上游 apernet/hysteria 稳定发布版本 |
| `hysteria2_native_install_dir` | `"/opt/hysteria2"` | 二进制与配置安装目录（mode 0750） |
| `hysteria2_native_dir_mode` | `"0750"` | 统一目录权限 |
| `hysteria2_native_binary_path` | `"/opt/hysteria2/hysteria2-client"` | 二进制可执行文件完整路径 |
| `hysteria2_native_config_path` | `"/opt/hysteria2/config.yaml"` | 配置文件路径（mode 0600） |
| `hysteria2_native_service_name` | `"hysteria2-native"` | systemd 服务名称（`hysteria2-native.service`） |
| `hysteria2_native_socks5_port` | `10808` | 本地 SOCKS5 监听端口 |
| `hysteria2_native_http_port` | `10808` | 本地 HTTP 监听端口（与 SOCKS5 共享 10808 单端口混合监听） |
| `hysteria2_native_server` | `{{ singbox_domain }}` | 上游服务端域名或 IP |
| `hysteria2_native_server_port` | `{{ app_port_singbox_hysteria \| default(30051) }}` | 上游服务端端口 |
| `hysteria2_native_auth_password` | `{{ hysteria_auth_password }}` | Hysteria 认证密钥（Vault 注入） |
| `hysteria2_native_sni` | `"bing.com"` | TLS SNI |
| `hysteria2_native_insecure` | `true` | 是否允许不安全证书 |
| `hysteria2_native_alpn` | `['h3']` | ALPN 协议列表 |
| `hysteria2_native_obfs_type` | `"salamander"` | 混淆类型 |
| `hysteria2_native_obfs_password` | `{{ hysteria_obfs_password }}` | 混淆密钥（Vault 注入） |
| `hysteria2_native_use_controller_staging` | `true` | 在 Ansible 控制端下载校验后传输，避免远端未配代理时 bootstrap 失败 |

## 迁移与共存策略

当目标节点（如 rasp）存在历史原生 `hysteria2.service`（如位于 `/home/admin/unibox/services/hysteria2`，仅监听 `0.0.0.0:10808` 且无 HTTP 端口时）：
1. 部署切流（cutover）时停止并禁用旧的 `hysteria2.service`。
2. 绝对保留其磁盘上的配置与二进制文件用于应急回滚。
3. 如果执行回滚（`rollback.yml`），角色会停止并移除 `hysteria2-native.service`，并自动重新启动原有的 `hysteria2.service`。

## 生命周期与 Tags

- **Check/Deploy**: `tags: [deploy, services, hysteria2_native, phase3]`
- **Preflight**: `tags: [deploy, services, hysteria2_native, hysteria2_native_preflight, phase3]`
- **Install**: `tags: [deploy, services, hysteria2_native, hysteria2_native_install, phase3]`
- **Configure**: `tags: [deploy, services, hysteria2_native, hysteria2_native_config, phase3]`
- **Verify**: `tags: [verify, services, hysteria2_native, hysteria2_native_verify, phase3]`
- **Rollback**: `tags: [rollback, services, hysteria2_native, hysteria2_native_rollback, phase3]`
