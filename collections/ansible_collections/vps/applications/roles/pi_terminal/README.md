# Role: pi_terminal

在浏览器中运行受限的 OMP（Oh My Pi）Coding Agent 终端。角色名保留为 `pi_terminal`，以延续现有 Catalog、Make 生命周期和 `pi.suai.eu.org` 入口；容器内部运行时已替换为 OMP。

```text
Browser -> Cloudflare -> Nginx -> 127.0.0.1:30014 -> ttyd -> tmux -> omp
```

## 安全边界

- 容器使用 UID/GID `10001`，不是 root。
- ttyd 仅映射到宿主机 `127.0.0.1`。
- ttyd 强制 Basic Auth、Origin 校验和单客户端限制。
- 容器根文件系统只读，删除全部 Linux capabilities，启用 `no-new-privileges`。
- 只挂载独立 workspace、凭据目录和 OMP home；不挂载 Docker Socket 或宿主机 home。
- 访问密码首次部署随机生成并保存在目标机 `/opt/pi-terminal/secrets/password`。
- OMP 配置通过只读 `/etc/omp/config.yml` 管理，用户 OAuth、会话、插件和 Skills 持久化到 named volume `pi_terminal_omp_home`。
- 旧 Pi named volume `pi_terminal_home` 不再挂载，但迁移验收前不会自动删除。

## OMP Minimal Profile

默认保留：

- `read`、`write`、Hashline/AST 编辑、`grep`、`glob`、`bash`。
- JavaScript eval。
- LSP 懒加载。
- 单层 subagents、todo、job、ask。
- 本地 compaction、read summarization、Skills。
- `web_search`。

默认关闭：

- Browser/Chromium、DAP debug、launch、Python eval。
- MCP 项目自动发现、Advisor、Hindsight、Autolearn。
- 动态工具发现。
- SSH、GitHub 专用工具、图像、语音和协作工具不会进入工具白名单。
- Ollama、llama.cpp、LM Studio、vLLM 自动发现。

## 主要变量
默认 `pi_terminal_enabled: false`。当 Catalog 仍选中本 Role 但该变量关闭时，部署流程只停止已有 `pi-terminal` 容器，不删除 workspace、凭据或构建文件。


| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `pi_terminal_port` | `30014` | ttyd 本地端口 |
| `pi_terminal_bun_image` | `oven/bun:1.3.14-slim` | 固定 Bun 基础镜像 |
| `pi_terminal_omp_version` | `17.2.7` | 固定 OMP 版本 |
| `pi_terminal_omp_tools` | 受限白名单 | OMP 启动工具集合 |
| `pi_terminal_basic_auth_username` | `suai` | 浏览器认证用户名 |
| `pi_terminal_basic_auth_password` | 空 | 为空时首次部署自动生成 |
| `pi_terminal_workspace_dir` | `/opt/pi-terminal/workspace` | OMP 唯一宿主机工作区 |
| `pi_terminal_memory` | `4g` | 容器内存上限 |
| `pi_terminal_cpus` | `3.0` | 容器 CPU 上限 |
| `pi_terminal_pids_limit` | `512` | 容器进程数上限 |

## 依赖边界

- Catalog 仅保留 Docker 的全量部署顺序；focused lifecycle 只做 Docker/Compose/OpenSSL preflight，不执行 Docker Role。
- `container_deployer` 是参数化实现工具，由本 Role 显式调用，不属于 Catalog dependency。
- 公网域名、TLS 证书和 Nginx 站点由 `services.nginx.nginx_site_config` 独立管理。

## 生命周期

```bash
make switch_remote.cc15
make env_show
make check-applications.pi_terminal
make deploy-applications.pi_terminal
make verify-applications.pi_terminal
```

获取浏览器密码：

```bash
ssh cc15 'sudo cat /opt/pi-terminal/secrets/password'
```

首次进入 OMP 后执行 `/login`。认证信息和会话保存在 `pi_terminal_omp_home`，容器重建不会清除。

回滚仅删除当前容器和构建文件，保留 workspace、凭据以及新旧 agent volume：

```bash
make rollback-applications.pi_terminal
```

彻底下线时，还应从 `inventories/host_vars/cc15.yml` 删除 `pi.suai.eu.org` 并重新部署 Nginx。
