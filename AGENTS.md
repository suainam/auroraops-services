# auroraops-services Agent Operating Directives

## 1. 仓库定位与职责 (Child Capability Repository)
- **定位**：公开子仓库，提供应用服务、网络隧道、容器运行时、数据库以及开发者个性化配置。
- **边界**：
  - 承载按 Profile 挂载的具体业务与服务能力。
  - **严禁**包含通用 OS 底层引导（属于 `auroraops-base`）或巡检备份灾备（属于 `auroraops-ops`）。
  - **严禁**包含真实生产私密变量、域名密码或真实 Token。
- **父仓关系**：被父仓 `auroraops-control` 通过 Release Tag + Commit Hash 精确锁定使用。

---

## 2. 包含角色列表 (共 28 个)
- **网络与穿透** (7): `cloudflared`, `easytier`, `zerotier`, `hysteria2_native`, `mihomo_native`, `ip2free_gateway`, `cliproxyapi_native`
- **运行时与中间件** (7): `docker`, `docker_apps`, `nginx`, `certbot`, `nodejs`, `postgresql`, `redis`
- **业务应用组件** (8): `application_service`, `application_timer`, `container_deployer`, `dailycheckin`, `grok_register`, `openviking`, `pi_terminal`, `qmd`
- **环境检查** (2): `ansibletest`, `prereq_checks`
- **个性化与开发** (4): `user_management`, `zsh`, `vim`, `rclone`

---

## 3. 开发与测试指南
1. **修改 Role**：
   - 保证任务变量提供合理的测试默认值，参数由父仓 Profile 注入覆盖。
2. **重新生成 Playbook**：
   ```bash
   python3 scripts/generate_ansible_playbooks.py
   ```
3. **语法检查**：
   ```bash
   ansible-playbook -i localhost, playbooks/deploy.yml --syntax-check
   ```
4. **提交与推送**：
   - 在本仓库的 `main` 或特性分支提交并推送。
