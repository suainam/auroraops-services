from __future__ import annotations

from pathlib import Path
import jinja2
import yaml

SERVICES_ROOT = Path(__file__).resolve().parents[2]
ROLE_ROOT = (
    SERVICES_ROOT
    / "collections/ansible_collections/vps/personalization/roles/rclone"
)


def read_role(relative: str) -> str:
    return (ROLE_ROOT / relative).read_text(encoding="utf-8")


def test_rclone_defaults_define_linux_and_darwin_paths() -> None:
    defaults_text = read_role("defaults/main.yml")
    defaults = yaml.safe_load(defaults_text)

    assert defaults["rclone_config_path"] == "/root/.config/rclone/rclone.conf"
    assert defaults["rclone_config_dir"] == "{{ rclone_config_path | dirname }}"
    assert defaults["rclone_user_config_dir"] == "{{ rclone_config_dir }}/rclone.conf.d"

    assert ".config/rclone/rclone.conf" in defaults["rclone_darwin_config_path"]
    assert "ansible_env.HOME" in defaults["rclone_darwin_config_path"]
    assert defaults["rclone_darwin_config_dir"] == "{{ rclone_darwin_config_path | dirname }}"
    assert defaults["rclone_darwin_user_config_dir"] == "{{ rclone_darwin_config_dir }}/rclone.conf.d"


def test_rclone_tasks_main_dispatches_darwin_and_linux_without_duplication() -> None:
    main_text = read_role("tasks/main.yml")
    tasks = yaml.safe_load(main_text)

    darwin_includes = []
    linux_blocks = []

    for task in tasks:
        include = task.get("ansible.builtin.include_tasks")
        if include == "darwin.yml":
            darwin_includes.append(task)
        if "block" in task and any("ansible_system != 'Darwin'" in cond for cond in task.get("when", [])):
            linux_blocks.append(task)

    assert len(darwin_includes) == 1, f"Expected exactly 1 Darwin dispatch, found {len(darwin_includes)}"
    assert len(linux_blocks) == 1, f"Expected exactly 1 Linux block, found {len(linux_blocks)}"

    darwin_when = darwin_includes[0].get("when", [])
    assert any("ansible_system == 'Darwin'" in cond for cond in darwin_when)


def test_rclone_darwin_tasks_enforce_user_path_permissions_and_no_log() -> None:
    darwin_text = read_role("tasks/darwin.yml")
    tasks = yaml.safe_load(darwin_text)

    # Security invariant: Darwin tasks must not slurp secret files or write /tmp credentials
    assert "slurp" not in darwin_text, "Darwin tasks must not slurp existing config"
    assert "/tmp" not in darwin_text, "Darwin tasks must not create temp files in /tmp"

    dir_task = None
    template_task = None

    for task in tasks:
        assert task.get("become") is not True, f"Darwin task '{task.get('name')}' should not escalate with become: true"
        if "ansible.builtin.file" in task and task["ansible.builtin.file"].get("state") == "directory":
            dir_task = task
        if "ansible.builtin.template" in task and task["ansible.builtin.template"].get("src") == "rclone.conf.j2":
            template_task = task
    assert dir_task is not None, "Missing directory creation task in darwin.yml"
    assert dir_task["ansible.builtin.file"]["mode"] == "0700"

    assert template_task is not None, "Missing template task in darwin.yml"
    assert template_task["ansible.builtin.template"]["dest"] == "{{ rclone_darwin_config_path }}"
    assert template_task["ansible.builtin.template"]["mode"] == "0600"
    assert template_task.get("no_log") is True


def test_rclone_linux_tasks_preserve_backup_and_token_extraction() -> None:
    main_text = read_role("tasks/main.yml")

    assert "rclone__extracted_onedrive_token" in main_text
    assert "rclone__extracted_gdrive_token" in main_text
    assert "rclone_local_conf" in main_text
    assert "rclone_system_backup" in main_text
    assert "dest: \"{{ rclone_config_path }}\"" in main_text


def test_rclone_conf_template_renders_platform_aware_includes() -> None:
    template_text = read_role("templates/rclone.conf.j2")
    env = jinja2.Environment()
    tpl = env.from_string(template_text)

    # Render for Darwin
    rendered_darwin = tpl.render(
        rclone_onedrive_token="fake_od_token",
        rclone_onedrive_drive_id="fake_od_id",
        rclone_gdrive_token="fake_gd_token",
        rclone_include_user_configs=True,
        ansible_system="Darwin",
        rclone_darwin_user_config_dir="/Users/mock/.config/rclone/rclone.conf.d",
    )
    assert "[onedrive]" in rendered_darwin
    assert "[gdrive]" in rendered_darwin
    assert "path = /Users/mock/.config/rclone/rclone.conf.d/*.conf" in rendered_darwin

    # Render for Linux
    rendered_linux = tpl.render(
        rclone_onedrive_token="fake_od_token",
        rclone_onedrive_drive_id="fake_od_id",
        rclone_gdrive_token="fake_gd_token",
        rclone_include_user_configs=True,
        ansible_system="Linux",
        rclone_user_config_dir="/root/.config/rclone/rclone.conf.d",
    )
    assert "path = /root/.config/rclone/rclone.conf.d/*.conf" in rendered_linux

    # Render without user configs
    rendered_no_user = tpl.render(
        rclone_onedrive_token="fake_od_token",
        rclone_onedrive_drive_id="fake_od_id",
        rclone_gdrive_token="fake_gd_token",
        rclone_include_user_configs=False,
        ansible_system="Darwin",
    )
    assert "[include]" not in rendered_no_user


def test_rclone_verify_tasks_are_platform_aware() -> None:
    verify_text = read_role("tasks/verify.yml")
    tasks = yaml.safe_load(verify_text)

    found_darwin_dir_check = False
    found_darwin_file_check = False
    homebrew_path_present = False

    for task in tasks:
        env = task.get("environment", {})
        if "/opt/homebrew/bin" in env.get("PATH", ""):
            homebrew_path_present = True

        if "ansible.builtin.stat" in task:
            path = task["ansible.builtin.stat"].get("path", "")
            if "rclone_darwin_config_dir" in path and "ansible_system == 'Darwin'" in path:
                found_darwin_dir_check = True
            if "rclone_darwin_config_path" in path and "ansible_system == 'Darwin'" in path:
                found_darwin_file_check = True

    assert homebrew_path_present, "Expected /opt/homebrew/bin in verify task PATH environment"
    assert found_darwin_dir_check, "Config dir verification must be platform-aware"
    assert found_darwin_file_check, "Config file verification must be platform-aware"


def test_rclone_conf_template_renders_gdrive_client_credentials() -> None:
    template_text = read_role("templates/rclone.conf.j2")
    tpl = jinja2.Template(template_text)

    rendered = tpl.render(
        rclone_onedrive_token="fake_od_token",
        rclone_onedrive_drive_id="fake_od_id",
        rclone_gdrive_token="fake_gd_token",
        rclone_gdrive_client_id="my_client_id.apps.googleusercontent.com",
        rclone_gdrive_client_secret="my_client_secret",
        rclone_include_user_configs=False,
        ansible_system="Darwin",
    )
    assert "client_id = my_client_id.apps.googleusercontent.com" in rendered
    assert "client_secret = my_client_secret" in rendered


def test_rclone_webdav_templates_and_tasks_contract() -> None:
    defaults = yaml.safe_load(read_role("defaults/main.yml"))
    assert defaults["rclone_webdav_enabled"] is False
    assert defaults["rclone_webdav_remote"] == "gdrive:"
    assert defaults["rclone_webdav_addr"] == "127.0.0.1:5244"
    assert defaults["rclone_webdav_cache_max_size"] == "10G"

    # Verify Darwin LaunchAgent template renders correctly
    darwin_plist_tpl = read_role("templates/com.auroraops.rclone-webdav.plist.j2")
    assert "<string>serve</string>" in darwin_plist_tpl
    assert "<string>webdav</string>" in darwin_plist_tpl
    assert "{{ rclone_webdav_cache_max_size }}" in darwin_plist_tpl

    # Verify Linux systemd service template renders correctly
    linux_svc_tpl = read_role("templates/rclone-webdav.service.j2")
    assert "/usr/bin/rclone serve webdav" in linux_svc_tpl
    assert "--vfs-cache-max-size {{ rclone_webdav_cache_max_size }}" in linux_svc_tpl

    # Verify Darwin tasks include LaunchAgent deployment
    darwin_tasks = yaml.safe_load(read_role("tasks/darwin.yml"))
    plist_tasks = [t for t in darwin_tasks if "Deploy Darwin WebDAV LaunchAgent plist" in t.get("name", "")]
    assert len(plist_tasks) == 1

    # Verify Linux tasks include systemd service deployment
    main_tasks = yaml.safe_load(read_role("tasks/main.yml"))
    linux_block = [t for t in main_tasks if "block" in t and any("ansible_system != 'Darwin'" in c for c in t.get("when", []))][0]
    linux_webdav_tasks = [t for t in linux_block["block"] if "Deploy Linux WebDAV systemd unit" in t.get("name", "")]
    assert len(linux_webdav_tasks) == 1

    # Verify verify.yml includes WebDAV health check
    verify_tasks = yaml.safe_load(read_role("tasks/verify.yml"))
    webdav_verify = [t for t in verify_tasks if "验证 WebDAV 服务健康检查" in t.get("name", "")]
    assert len(webdav_verify) == 1
    assert webdav_verify[0]["ansible.builtin.uri"]["method"] == "PROPFIND"
