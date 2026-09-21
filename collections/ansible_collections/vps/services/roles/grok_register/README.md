# Grok Register

`vps.services.grok_register` 管理 cc15 上固定版本的
`AaronL725/grok-register` 完整 CLI 运行时。它将上游源码、Python 依赖和
Chromium 放在隔离容器中；配置、浏览器状态、账号输出和 pending 恢复数据放在
受保护的持久目录中。Role 默认部署空闲容器，不会自行创建邮箱或启动注册。

Chromium 的 `HOME` 固定为持久工作目录内的 `browser-home/`；pending 和账号输出
遵循上游在工作目录根部的约定，`screenshots/` 与预留的 `logs/` 也以 `0700` 创建。
运行入口每次重建只同步镜像内源码，不覆盖这些运行时状态。

当前核心 Role 复用已验证的 Cloudflare Worker JWT 和路径契约，并以单浏览器、
单 worker、单次请求作为 cc15 的容量基线。GUI/noVNC、全部高级提供商和正式
入口切换由后续迁移 Role 任务交付，不能以它们未部署为理由改用旧镜像。

## Lifecycle

```bash
make switch_remote.cc15
make env_show
make check-services.grok_register
make deploy-services.grok_register
make verify-services.grok_register
make rollback-services.grok_register
```

`check` 会执行 Docker、固定源版本、容量和只读 Cloudflare Worker 域名探测；
它不会调用邮箱创建接口。`verify` 检查容器状态、无公开端口、源版本、配置权限、
Chromium 与同一只读邮箱能力。`rollback` 只移除容器，保留配置、pending、账户
输出和镜像以便受控恢复。

## Maintenance boundary

上游修订必须是不可变 Git SHA。镜像固定 Debian manifest digest，并固定上游依赖中
唯一的版本范围；升级时同时更新修订、依赖约束与镜像构建版本，重新运行完整生命周期；
不得跟踪上游默认分支。APT 使用基础镜像自带且由 Debian 签名校验的软件源，不能通过
关闭 TLS 验证来追求可复现性。秘密只来自 Vault 或受保护的远端配置文件，禁止写入镜像层、
README、普通日志和 Ansible 输出。
