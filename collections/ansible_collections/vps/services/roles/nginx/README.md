# Role: vps.services.nginx

## 1. 概述
该角色用于在 Debian 或 Alpine 系统上安装 Nginx，并提供标准化的虚拟主机配置和安全加固。Debian 使用 Mainline APT 源，Alpine 使用 APK/OpenRC。

## 2. 变量说明 (Defaults)
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `nginx_http_port` | `80` | HTTP 监听端口，可用于 NAT 节点的非特权映射端口（如 `10080`）。 |
| `nginx_https_port` | `443` | HTTPS 监听端口。 |
| `nginx_client_max_body_size` | `100m` | 上传文件大小限制。 |
| `nginx_logrotate_enabled` | `true` | 是否部署 Role-local 日志轮转配置。 |
| `nginx_site_list_vars.nginx_sites_to_deploy` | `[...]` | 需要部署的站点域名列表。 |
| `nginx_sites_defaults` | `{...}` | 元模板默认配置（backend_port, websocket 等）。 |
| `nginx_sites_config` | `{...}` | 网站配置字典（数据驱动配置）。 |

## 3. 内部逻辑
- **安装**: 使用官方 Mainline 源安装最新版 Nginx。
- **安全加固**:
    - 默认启用 Security Headers (X-Frame-Options, X-XSS-Protection, etc.)。
    - 移除默认欢迎页。
- **配置优化**:
    - 优化 Gzip、连接超时和缓冲区设置。
    - 支持通过变量调整 `client_max_body_size`。
- **站点管理**: 
    - 支持元模板（`meta_site.conf.j2`）和自定义模板
    - 自动化部署和启用虚拟主机配置
    - 配置变更时自动重载 nginx（handler 机制）

## 4. 元模板配置

### 4.1 元模板特性

`meta_site.conf.j2` 支持以下高级特性：

- ✅ 简单反向代理
- ✅ WebSocket 支持
- ✅ 多 location 配置
- ✅ Rewrite 规则
- ✅ 自定义 headers
- ✅ proxy_hide_header
- ✅ 自定义超时设置
- ✅ 静态资源缓存
- ✅ IPv6 支持

### 4.2 配置示例

**简单反向代理**:
```yaml
nginx_sites_config:
  example.com:
    backend_port: "{{ app_port_example }}"
```

**WebSocket + 多 location**:
```yaml
nginx_sites_config:
  ws.example.com:
    websocket: true
    locations:
      - path: "/api"
        backend_port: "{{ app_port_api }}"
        websocket: true
      - path: "/static"
        backend_port: "{{ app_port_static }}"
        static_cache: true
```

**Rewrite 规则**:
```yaml
nginx_sites_config:
  api.example.com:
    locations:
      - path: "/v1/upload"
        rewrite:
          pattern: "^/v1/upload(.*)$"
          replacement: "/upload$1?version=v1"
          flag: "break"
        backend_port: "{{ app_port_api }}"
```

**自定义 headers**:
```yaml
nginx_sites_config:
  secure.example.com:
    locations:
      - path: "/"
        backend_port: "{{ app_port_app }}"
        proxy_hide_headers:
          - X-Frame-Options
        add_headers:
          - {name: "X-Frame-Options", value: "SAMEORIGIN", always: "always"}
          - {name: "X-Custom-Header", value: "custom-value"}
```

### 4.3 自定义模板回退

如果需要更复杂的配置，可以使用自定义模板：

```yaml
nginx_sites_config:
  complex.example.com:
    type: custom  # 使用自定义模板
```

然后创建 `templates/complex.example.com.conf.j2`。

## 5. Handler 机制

配置变更时会自动触发 nginx 重载：

```yaml
# tasks/sites.yml 中的 notify
- name: 部署 Nginx 站点配置（元模板）
  ansible.builtin.template:
    src: "meta_site.conf.j2"
    dest: "/etc/nginx/sites-available/{{ item }}.conf"
  notify: reload nginx  # 自动触发重载
```

Handler 定义在 `handlers/main.yml`：

```yaml
- name: Reload Nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
  listen: "reload nginx"
```

## 6. 依赖关系
- 系统包: `curl`, `gnupg`, `ca-certificates`。
- Nginx 的 Catalog 不依赖 Certbot；`nginx_site_config` 只读检查每个站点引用的证书链和私钥是否已存在，不自动申请证书。
- 证书缺失时先显式部署 `services.certbot`，再重新执行站点配置。
- Logrotate 是可选运维增强；Nginx 直接管理 `/etc/logrotate.d/nginx`，不执行完整 Logrotate Role。
- 定向站点配置不会执行 Certbot、Docker Apps、Nginx 安装或日志轮转任务。
- `nginx_site_config` 在首次 deploy 前保存精确站点配置、启用链接和证书指纹基线；站点集合或证书指纹变化时拒绝复用旧基线。
- 有意迁移或新增站点导致站点集合变化时，临时设置 `nginx_site_baseline_reseed=true` 执行一次无参数的完整
  `check -> deploy -> verify`，它会先记录当前站点的可恢复状态并重建基线；验收后必须移除该临时变量。
- 已存在基线中的单站点可显式执行增量 reconcile：同时传入
  `nginx_site_target=<domain>` 与
  `nginx_site_baseline_allow_additive_reconcile=true`。该模式只修改目标
  站点，并要求目标已有未变化的证书指纹与可恢复的 pre-deploy state；它不
  接受站点删除、替换或无基线的首次定向 deploy。
- 全量 Role 的过时链接清理属于独立 `nginx_site_enable` 行为，不随 `nginx_site_config` subtarget 执行。
- Sub-Store 自定义站点模板（如 `uk.suai.eu.org`、`handclap6764.suai.eu.org`）消费 effective provider catalog；NAT provider 由 `nat_nodes` inventory 自动叠加，退网名单由 `sub_store_retired_provider_names` 过滤。Capability provider source 路径使用稳定 `provider-id`，与订阅名称及 catalog 顺序解耦。

## 7. 部署命令

```bash
# 部署所有站点配置（推荐）
make deploy-services.nginx.nginx_site_config

# 部署完整 nginx 角色
make deploy-services.nginx

# Dry-run 检查
make check-services.nginx.nginx_site_config

# 已存在基线的单站点增量 reconcile（示例）
make check-services.nginx.nginx_site_config \
  ANSIBLE_EXTRA_ARGS='-e nginx_site_baseline_allow_additive_reconcile=true -e nginx_site_target=example.com'
make deploy-services.nginx.nginx_site_config \
  ANSIBLE_EXTRA_ARGS='-e nginx_site_baseline_allow_additive_reconcile=true -e nginx_site_target=example.com'
make verify-services.nginx.nginx_site_config \
  ANSIBLE_EXTRA_ARGS='-e nginx_site_baseline_allow_additive_reconcile=true -e nginx_site_target=example.com'

# 验证所有目标站点配置和启用链接
make verify-services.nginx.nginx_site_config

# 恢复 deploy 前的目标站点配置和链接
make rollback-services.nginx.nginx_site_config

# 独立验证 rollback 终态
make rollback_verify-services.nginx.nginx_site_config

# 验证完整 nginx 角色
make verify-services.nginx
```

定向 verify 只检查 Nginx 拥有的结果：配置语法、目标配置与链接、服务状态和
监听端口。后端应用健康与公共 URL 的业务响应由对应应用 Role 验收；例如
upstream 未启动造成的 HTTP `502` 不表示站点配置部署失败。

## 8. 维护与排查

### 8.1 快速操作

```bash
# 检查配置语法
sudo nginx -t

# 重载配置（手动）
sudo systemctl reload nginx

# 重启服务
sudo systemctl restart nginx

# 查看日志
sudo tail -f /var/log/nginx/error.log
```

### 8.2 配置文件位置

```
/etc/nginx/
├── nginx.conf                    # 主配置文件
├── sites-available/              # 可用站点配置
│   ├── example.com.conf
│   └── ...
└── sites-enabled/                # 启用站点配置（符号链接）
    ├── example.com.conf -> ../sites-available/example.com.conf
    └── ...
```

### 8.3 故障排查

**问题 1: 配置未生效**
```bash
# 1. 检查配置语法
sudo nginx -t

# 2. 检查符号链接
ls -la /etc/nginx/sites-enabled/

# 3. 手动重载
sudo systemctl reload nginx
```

**问题 2: Handler 未触发**
```bash
# 检查是否有配置变更
make deploy-services.nginx.nginx_site_config

# 查看 playbook 输出中的 "RUNNING HANDLER" 部分
# 如果 changed=0，handler 不会触发
```

**问题 3: 密钥未正确应用**
```bash
# 检查 vault.yml 中的密钥
ansible-vault view secrets/vault.yml | grep password

# 检查生成的配置文件
grep "token=" /etc/nginx/sites-available/api-gcli.msuai.top.conf
```

## 9. 最佳实践

1. **使用元模板**: 优先使用元模板，减少重复配置
2. **配置集中化**: 所有网站配置集中在 `nginx.yml`
3. **密钥安全**: 敏感信息存储在 `vault.yml` 中
4. **渐进式迁移**: 先 dry-run，再部署，最后验证
5. **Handler 自动化**: 依赖 handler 机制自动重载服务

## 10. 相关文档

- [Nginx 官方文档](https://nginx.org/en/docs/)
- [AGENTS.md - Agent 规则](../../../../../../AGENTS.md)
- [Nginx 角色部署与验证](#7-部署命令)
