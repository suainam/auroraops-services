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
        if "ansible.builtin.template" in task:
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
