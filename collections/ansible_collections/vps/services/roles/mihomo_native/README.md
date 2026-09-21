# Mihomo Native Role (`vps.services.mihomo_native`)

## 作用

在 Linux ARM64 边缘节点运行官方 MetaCubeX Mihomo 原生二进制。
Role 消费 Sub-Store 生成的完整 Mihomo profile；profile 内的 proxy-providers、
proxy-groups、rules 与节点内容仍由 Sub-Store 负责，Role 不解析或重写 YAML。

默认监听 `127.0.0.1:7890`，不向 LAN 暴露 mixed port。CLIProxyAPI、监测探针
和系统级 HTTP(S) 代理都通过这个端口出站；旧透明网关与独立 Hysteria2 客户端不再作为本方案的数据面。

## 刷新与回滚语义

- 二进制版本和 ARM64 SHA-256 固定在 `defaults/main.yml`，不使用 `latest`。
- 首次部署在控制端临时 staging 完整 profile，避免目标还没有 7890 时形成
  bootstrap 循环；systemd timer 之后在目标端通过 Mihomo 出口下载。所有下载内容
  都先写临时文件。
- 用 Mihomo 原生 `-t` 校验临时 profile，校验失败时保留现有 last-known-good 文件。
- 校验通过后在同一文件系统内 `mv` 原子替换，内容未变化时不重启 Mihomo。
- profile URL 放在 root-only 的 `/etc/mihomo-native/refresh.env`，Ansible 相关任务关闭日志。
- verify 会检查 Mihomo provider cache 非空、7890 由 Mihomo 进程占用且只绑定 `127.0.0.1`。
- rollback 移除运行时 unit、脚本和二进制，保留 LKG profile 与 provider state。
- rollback_verify 通过 systemd `LoadState=not-found` 确认运行时 unit 已移除，避免把已删除
  unit 的历史 facts 条目误判为仍在运行。

## 生命周期

角色由父仓 targeted adapter 按九个语义阶段接入 services/phase3：
`preflight -> check -> deploy -> verify -> idempotence -> rollback -> rollback_verify -> redeploy -> recovery_verify`。
其中 `idempotence` 重复 `check` 并要求 `changed=0`；`redeploy` 重用 deploy 实现，
`recovery_verify` 使用独立的 recovery 验证入口。

```bash
make preflight-services.mihomo_native
make check-services.mihomo_native
make deploy-services.mihomo_native
make verify-services.mihomo_native
# idempotence: repeat check and require changed=0
make rollback-services.mihomo_native
make rollback_verify-services.mihomo_native
make redeploy-services.mihomo_native
make recovery_verify-services.mihomo_native
```

Profile 显式启用 `mihomo_native`，其他主机默认关闭。profile 下载代理由
`mihomo_native_profile_download_proxy` 显式指定；如果启用定时刷新，应设置为可达的
出站代理。真实目标调通还需要完整 profile URL 可达，以及目标具备 `curl`、`gzip`、
`systemd`。
