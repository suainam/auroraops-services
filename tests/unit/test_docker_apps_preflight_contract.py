"""Docker Apps preflight remains scoped and read-only."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"


def test_preflight_checks_the_selected_app_and_docker_capabilities_read_only():
    tasks = yaml.safe_load(
        (ROLE / "tasks/preflight.yml").read_text(encoding="utf-8")
    )
    merge = tasks[0]
    assert merge["ansible.builtin.import_tasks"] == (
        "{{ role_path }}/../../../common/tasks/merge_list_vars.yml"
    )
    assert merge["vars"]["merge_var_name"] == "docker_apps_containers"

    target_assertion = next(
        task for task in tasks if task.get("name") == "Assert selected Docker App is configured"
    )
    assert target_assertion["ansible.builtin.assert"]["that"] == [
        "docker_apps_target is defined",
        "docker_apps_target in docker_apps_containers",
    ]

    probes = [task for task in tasks if "ansible.builtin.command" in task]
    assert len(probes) == 2
    assert {tuple(task["ansible.builtin.command"]["argv"]) for task in probes} == {
        ("docker", "info"),
        ("docker", "compose", "version"),
    }
    assert all(task["changed_when"] is False for task in probes)
    assert all(task["failed_when"] is False for task in probes)
    assert all(task["no_log"] is True for task in probes)
    assert all("preflight" in task["tags"] for task in tasks)
