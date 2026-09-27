"""Docker Apps rollback verification must assert the selected app is absent."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
ROLE = (
    ROOT
    / "collections/ansible_collections/vps/services/roles/docker_apps"
)


def test_selected_app_rollback_verify_is_read_only_and_fails_if_container_remains():
    tasks = yaml.safe_load((ROLE / "tasks/rollback_verify.yml").read_text())

    task = next(
        item
        for item in tasks
        if item.get("name") == "Verify selected Docker app is absent after rollback"
    )
    assert task["community.docker.docker_container_info"] == {"name": "sub_store"}
    assert task["failed_when"] == "docker_apps_rollback_container_info.exists"
    assert task["when"] == "rollback_docker_app_name | default('') == 'sub_store'"
    assert task["changed_when"] is False
    assert task["no_log"] is True
    assert {
        "rollback_verify",
        "services",
        "docker_apps",
        "docker_apps_manifest",
        "sub_store",
        "phase5",
    } <= set(task["tags"])
