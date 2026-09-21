# Role: vps.services.dailycheckin

## 1. 概述
该角色部署 DailyCheckIn 的固定版本 Docker 镜像、私有配置、一次性 Systemd Service 和可选 Timer。GitHub Actions 是默认签到 Runner；AuroraOps 默认保持 Timer 停止，只提供受管的手工备用入口。

## 2. 变量说明
| 变量名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `dailycheckin_config_dir` | `"/opt/dailycheckin"` | 配置文件存储目录。 |
| `dailycheckin_docker_image` | `ghcr.io/suainam/dailycheckin:sha-f636611...` | DailyCheckIn 源码仓发布的不可变完整 commit 标签。 |
| `dailycheckin_local_config_src` | `$AURORAOPS_PRIMARY_CHECKOUT/secrets/dailycheckin/config.json` | 主 checkout 中的本地私有 `config.json`，不纳入仓库跟踪。 |
| `dailycheckin_timer_enabled` | `false` | 是否启用 AuroraOps Timer；默认关闭，避免与 GitHub Actions 重复签到。 |
| `dailycheckin_timer_on_calendar` | `"*-*-* 00,17:00:01"` | 仅在显式启用 Timer 时使用的触发规则。 |
| `app_timer_persistent` | `false` | 系统重启后不补执行错过的签到任务。 |
| `dailycheckin_service_timeout` | `"20m"` | 单次 oneshot 运行上限。 |
| `dailycheckin_service_timeout_stop_sec` | `"30s"` | 停止卡住服务的最大等待时间。 |

## 3. 内部逻辑
- **Docker 前置检查**: 定向部署只检查 Docker daemon 是否可用；Docker 未安装或未运行时快速失败，不重复执行完整 Docker role。
- **镜像管理**: 校验 `ghcr.io/suainam/dailycheckin:sha-<40位提交>` 格式并拉取固定版本镜像；目标机不再构建源码或应用补丁。
- **配置部署**: 从本地私有文件 `secrets/dailycheckin/config.json` 读取并部署到指定目录。
- **容器化执行**: 创建一个 Systemd Service，通过 `docker run --rm` 执行一次签到任务，完成后容器退出，不常驻内存。
- **生命周期约束**: Service 使用 `Type=oneshot`、`Restart=no`、`TimeoutSec=20m`、`TimeoutStopSec=30s`；`ExecStop` 与 `ExecStopPost` 均会删除执行容器，确保成功、失败或超时后不残留容器。
- **定时调度**: 创建但默认禁用并停止 Systemd Timer；只有显式设置 `dailycheckin_timer_enabled: true` 才会周期执行。
- **持久化控制**: `Persistent=false`，系统重启后不补执行错过的签到，避免重复签到。
- **合并推送**: 启用 `MERGE_PUSH: true` 后，由 DailyCheckIn 容器内已有通知逻辑合并全部签到结果并统一发送 Telegram 消息。
- **代理配置**: 自动配置 HTTP/SOCKS 代理支持（适用于需要代理的网络环境）。

## 4. 依赖关系
- Role Catalog 声明 `vps.services.docker` 为部署顺序依赖；定向部署通过轻量 preflight 验证 Docker，不执行完整 Docker role。
- `vps.applications.application_service`
- `vps.applications.application_timer`
- Docker 代理配置（如需要外部网络访问）

## 5. 维护与排查
- **幂等部署**: `make deploy-services.dailycheckin` 只收敛镜像、配置、Service 和 Timer，不主动执行签到。
- **查看结果**: `journalctl -u dailycheckin.service -f`。
- **卡住恢复**: 再次执行 `make deploy-services.dailycheckin`，声明状态会停止 oneshot，并由 `ExecStopPost` 清理残留容器。
- **终态验证**: `make verify-services.dailycheckin` 会检查 Timer 符合声明状态（默认 inactive/disabled）、Service 为 inactive、无残留容器、配置权限为 `0600` 且固定镜像存在。
- **回滚终态验证**: `make rollback_verify-services.dailycheckin` 会检查 systemd units 与残留容器已移除，同时保留私有 `config.json` 和已拉取的固定镜像。
- **配置修改**: 编辑 `/opt/dailycheckin/config.json` 后无须重启服务，下次触发自动生效。
- **代理配置**: 如遇网络连接问题，检查 `/opt/dailycheckin/config.json` 中的 `V2EX` 账号配置和 `TG_PROXY`。
- **合并推送**: 设置 `MERGE_PUSH: true` 可将所有签到结果合并为一条推送，减少通知打扰。
- **镜像更新**: 先由 `suainam/dailycheckin` 手工 `Docker Push` workflow 发布 commit 标签，再更新本变量并部署；生产配置禁止使用 `latest`。

## 6. 网络环境要求
- 在需要代理的网络环境中（如 NAS 局域网），确保已配置 Docker 代理。
- DailyCheckIn 服务需要访问外部 API，代理配置必须正确。
- 支持的代理类型：HTTP/SOCKS 代理。

## 7. 配置文件示例
```json
{
  "TG_API_HOST": "api.telegram.org",
  "TG_PROXY": "http://192.168.31.200:7890",
  "TG_BOT_TOKEN": "YOUR_BOT_TOKEN",
  "TG_USER_ID": "YOUR_USER_ID",
  "MERGE_PUSH": true
}
```

## 8. 验证与维护记录

### 2026-08-04 镜像发布与 Runner 边界收敛

- DailyCheckIn 源码仓负责从精确 checkout 构建并发布 GHCR 多架构镜像。
- AuroraOps 只拉取不可变 commit 标签，不再维护目标机 Dockerfile 或运行时 patch 构建链路。
- GitHub Actions 继续承担正式定时签到；AuroraOps Timer 默认 `disabled/stopped`。
- `dailycheckin.service` 保持 `oneshot`，可通过 `systemctl start dailycheckin.service` 手工触发。

### 2026-07-15 一次性任务生命周期收敛

- 调度统一由 Systemd Timer 负责，容器内部不承担常驻调度职责。
- Service 保持 `enabled=false`、`state=stopped`，部署不会触发签到。
- 单次任务最长运行 20 分钟，停止过程最长等待 30 秒。
- `ExecStopPost` 作为终态兜底，无论正常结束还是超时都删除执行容器。
- 2026-07-14 17:17 和 2026-07-15 00:10 两个真实 Timer 窗口均在上限内进入终态、清理容器并恢复下一次调度。
- 生命周期验收与 Provider 签到成功率分开判断：受控 `timeout` 表示调度边界生效，不代表业务签到成功。
- DailyCheckIn 自身继续负责 Provider 执行、结果汇总和 Telegram 推送，不额外包装 HTTP 或通知逻辑。

### 2026-02-25 贴吧签到耗时说明

**现象**: 贴吧配置了较多关注后，签到动辄需要 7 分钟甚至更长时间才能完成。
**原因**: 这是 Sitoi/dailycheckin 脚本的正常且预期行为。为了账号安全，源码内部硬编码了防风控/防封禁的请求随机间隔延迟机制：
- 每个贴吧签到请求之间强制随机休息 1.5-2.5 秒
- 每自动签到 10 个贴吧，强制额外休息 5-10 秒
- 获取贴吧列表的分页请求之间有 1-2 秒延迟
**结论**: 不建议使用补丁强行提速。取消延迟极易触发百度贴吧反作弊频率限制（如报 `340011` 错误）或导致贴吧账号被风控屏蔽。**建议保持现状**，依靠 systemd 定时任务在后台默默执行即可。

### 2026-02-08 Dockerfile 构建模式升级

**升级内容**:
- 改用 Dockerfile + `docker_image` 模块构建自定义镜像，替代原有的 `docker commit` 方式
- 构建过程完全代码化、幂等化
- Dockerfile 位于 `roles/dailycheckin/files/Dockerfile`
- 依赖更新逻辑透明可追溯

**技术实现**:
- 使用 `community.docker.docker_image` 模块的 `build` 参数
- 每次构建前检查镜像是否存在，不存在则构建
- Dockerfile 中固化 pip 依赖升级命令，确保可复现

**优势**:
- 幂等性：Ansible 会检查镜像是否已存在，避免重复构建
- 可追溯：Dockerfile 清晰记录了对原镜像的所有修改
- 可复现：任何环境都可基于 Dockerfile 重新构建相同镜像
- 易于维护：未来如需修改依赖，只需编辑 Dockerfile 即可

### 2026-02-04 镜像优化与合并推送

**优化内容**:
- 添加自动镜像检测和条件更新机制，避免重复更新依赖
- 后续部署时间从 ~2分钟 缩短到 ~5秒
- 启用 `MERGE_PUSH: true`，Telegram 推送从 5次 减少到 1次

**验证结果**: ✅ 服务正常运行

**性能提升**:
- 首次部署: ~2分钟（含构建自定义镜像）
- 后续部署: ~5秒（检测到镜像存在，跳过构建）
- 签到执行: ~20秒（使用自定义镜像，无需更新依赖）

**配置变更**:
- `dailycheckin_docker_image`: `"local/dailycheckin:custom"`
- `MERGE_PUSH`: `true`

### 2026-02-01 功能验证

**验证结果**: ✅ 服务正常运行

**测试方法**:
```bash
# 手动触发签到
systemctl start dailycheckin.service

# 查看执行日志
journalctl -u dailycheckin.service -f
```

**签到平台**:
- ✅ Bilibili (B站) - 签到成功
- ✅ V2EX - 签到成功
- ✅ 百度贴吧 - 签到成功
- ✅ 有道云笔记 - 签到成功
- ✅ 范思社区 - 签到成功

**Telegram 推送**: ✅ 推送成功

### 常见问题排查

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| 签到失败 | Cookie 过期 | 更新 `/opt/dailycheckin/config.json` 中的 cookie |
| Telegram 推送失败 | Bot Token 或 User ID 错误 | 检查 config.json 中的 `TG_BOT_TOKEN` 和 `TG_USER_ID` |
| 容器无法启动 | Docker 未运行 | `systemctl start docker` |
| 网络超时 | 需要代理 | 在 config.json 中配置 proxy |
| 多次推送通知 | 未启用合并推送 | 设置 `MERGE_PUSH: true` |
| 部署时间过长 | 镜像未构建 | 首次部署会自动构建，后续部署 ~5秒 |
