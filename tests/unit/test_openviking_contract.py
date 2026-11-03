# pyright: reportAny=false
"""Contract test for OpenViking integration in docker_apps."""

import json
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"


def test_openviking_defaults_registered():
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    assert defaults["docker_apps_openviking_enabled"] is False
    assert defaults["docker_apps_openviking_pull"] is False
    assert defaults["docker_apps_openviking_memory"] == "{{ openviking_memory | default('4GiB') }}"
    assert defaults["docker_apps_openviking_memory_reservation"] == "{{ openviking_memory_reservation | default('1GiB') }}"
    assert defaults["docker_apps_openviking_cpus"] == "{{ openviking_cpus | default('2.0') }}"
    assert "openviking" in defaults["docker_apps_openviking_data_dir"]


def test_openviking_template_renders_valid_json():
    template_content = (ROLE / "templates/openviking_ov.conf.j2").read_text(encoding="utf-8")
    env = jinja2.Environment()
    env.filters["to_json"] = json.dumps
    template = env.from_string(template_content)

    context = {
        "docker_apps_openviking_root_api_key": "test-key-123",
        "docker_apps_openviking_embedding_provider": "openai",
        "docker_apps_openviking_embedding_api_base": "https://api.openai.com/v1",
        "docker_apps_openviking_embedding_api_key": "emb-key",
        "docker_apps_openviking_embedding_model": "text-embedding-3-small",
        "docker_apps_openviking_embedding_dimension": 1536,
        "docker_apps_openviking_vlm_provider": "openai",
        "docker_apps_openviking_vlm_api_base": "https://api.openai.com/v1",
        "docker_apps_openviking_vlm_api_key": "vlm-key",
        "docker_apps_openviking_vlm_model": "gpt-5.4",
    }
    rendered = template.render(context)
    data = json.loads(rendered)

    assert data["service_name"] == "openviking-server"
    assert data["server"]["port"] == 1933
    assert data["server"]["root_api_key"] == "test-key-123"
    assert data["storage"]["workspace"] == "/app/.openviking/workspace"
    assert data["embedding"]["dense"]["provider"] == "openai"
    assert data["embedding"]["dense"]["dimension"] == 1536
    assert data["vlm"]["model"] == "gpt-5.4"


def test_openviking_task_wires_container_deployer_and_checkpoints():
    tasks = yaml.safe_load((ROLE / "tasks/openviking.yml").read_text(encoding="utf-8"))
    # Host dirs task
    assert tasks[0]["ansible.builtin.file"]["state"] == "directory"
    # Template task
    assert tasks[1]["ansible.builtin.template"]["src"] == "openviking_ov.conf.j2"

    # Baseline probe
    probe_task = next(t for t in tasks if "community.docker.docker_container_info" in t)
    assert probe_task["community.docker.docker_container_info"]["name"] == "openviking"

    # Checkpoint ID calculation
    id_task = next(t for t in tasks if "_openviking_checkpoint_id" in t.get("ansible.builtin.set_fact", {}))
    assert id_task is not None

    # Deploy block with rescue
    deploy_block = next(t for t in tasks if "block" in t and any("container_deployer" in str(st) for st in t.get("block", [])))
    assert "rescue" in deploy_block
    deploy_subtask = deploy_block["block"][0]
    assert deploy_subtask["ansible.builtin.include_role"]["name"] == "vps.services.container_deployer"
    assert deploy_subtask["vars"]["cdp_name"] == "openviking"
    assert "openviking" in deploy_block["tags"]
    assert "openviking" in deploy_subtask["ansible.builtin.include_role"]["apply"]["tags"]

def test_openviking_imported_in_main_tasks():
    main_tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    # Check import task in block
    block_tasks = main_tasks[0]["block"]
    openviking_import = next(
        (t for t in block_tasks if t.get("ansible.builtin.import_tasks") == "openviking.yml"),
        None,
    )
    assert openviking_import is not None
    assert "'openviking' in docker_apps_containers" in openviking_import["when"]


def test_openviking_registered_in_verify_tasks():
    verify_tasks = yaml.safe_load((ROLE / "tasks/verify.yml").read_text(encoding="utf-8"))

    names_task = next(
        t for t in verify_tasks if "docker_apps_container_names" in t.get("ansible.builtin.set_fact", {})
    )
    assert names_task["ansible.builtin.set_fact"]["docker_apps_container_names"]["openviking"] == "openviking"

    expected_running_task = next(
        t
        for t in verify_tasks
        if "docker_apps_container_expected_running" in t.get("ansible.builtin.set_fact", {})
    )
    assert (
        expected_running_task["ansible.builtin.set_fact"]["docker_apps_container_expected_running"]["openviking"]
        is True
    )

    openviking_verifies = [
        t for t in verify_tasks if t.get("when") == "verify_docker_app_name | default('') == 'openviking'"
    ]
    assert len(openviking_verifies) == 3
    assert any("assert" in t.get("ansible.builtin.assert", {}) or "assert" in str(t) for t in openviking_verifies)
    assert any("ansible.builtin.uri" in t for t in openviking_verifies)


def test_openviking_rollback_verify_contract():
    rollback_tasks = yaml.safe_load((ROLE / "tasks/rollback_verify.yml").read_text(encoding="utf-8"))
    openviking_rollback = next(
        (t for t in rollback_tasks if t.get("when") == "rollback_docker_app_name | default('') == 'openviking'"),
        None,
    )
    assert openviking_rollback is not None
    assert openviking_rollback["community.docker.docker_container_info"]["name"] == "openviking"
    assert openviking_rollback["failed_when"] == "docker_apps_rollback_openviking_info.exists"
