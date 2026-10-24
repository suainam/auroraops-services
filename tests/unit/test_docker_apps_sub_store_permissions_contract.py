from pathlib import Path
import yaml

ROLES_DIR = (
    Path(__file__).resolve().parents[2]
    / "collections/ansible_collections/vps/services/roles"
)
SUB_STORE_TASKS = ROLES_DIR / "docker_apps/tasks/sub_store.yml"
DOCKER_APPS_DEFAULTS = ROLES_DIR / "docker_apps/defaults/main.yml"
INTERNAL_SUB_ORIGIN_TASKS = ROLES_DIR / "nginx/tasks/internal_sub_origin.yml"


def test_sub_store_tasks_pass_dir_permissions_to_container_deployer() -> None:
    tasks = yaml.safe_load(SUB_STORE_TASKS.read_text(encoding="utf-8"))
    deploy_task = next(
        task for task in tasks if task.get("name") == "Deploy Sub-Store"
    )
    vars_dict = deploy_task.get("vars", {})

    assert vars_dict.get("cdp_dirs") == ["data"]
    assert "docker_apps_sub_store_dir_owner" in vars_dict.get("cdp_dir_owner", "")
    assert "docker_apps_sub_store_dir_group" in vars_dict.get("cdp_dir_group", "")
    assert "docker_apps_sub_store_dir_mode" in vars_dict.get("cdp_dir_mode", "")


def test_sub_store_defaults_align_with_internal_sub_origin_permissions() -> None:
    defaults = yaml.safe_load(DOCKER_APPS_DEFAULTS.read_text(encoding="utf-8"))
    nginx_tasks = yaml.safe_load(INTERNAL_SUB_ORIGIN_TASKS.read_text(encoding="utf-8"))

    nginx_dir_task = next(
        task
        for task in nginx_tasks
        if "Ensure the internal subscription root exists" in task.get("name", "")
    )
    nginx_file = nginx_dir_task["ansible.builtin.file"]

    # Ownership & mode alignment (Issue #356)
    assert "0750" in defaults["docker_apps_sub_store_dir_mode"]
    assert nginx_file["mode"] == "0750"
    assert nginx_file["owner"] == "root"
    assert "root" in defaults["docker_apps_sub_store_dir_owner"]
    assert "nginx_internal_sub_group" in defaults["docker_apps_sub_store_dir_group"]
    assert "www-data" in defaults["docker_apps_sub_store_dir_group"]
