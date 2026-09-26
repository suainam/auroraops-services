from __future__ import annotations

from pathlib import Path

ROLE = Path(__file__).resolve().parents[1] / "collections/ansible_collections/vps/services/roles/singbox"


def test_verify_contract_rejects_unresolved_route_outbounds() -> None:
    text = (ROLE / "tasks/verify_config_contract.yml").read_text(encoding="utf-8")
    assert "singbox_config_route_outbound_refs | difference(singbox_config_outbound_tags) | length == 0" in text
    assert "relay-failover-cluster" in text
    assert "verify_config_contract.yml" in (ROLE / "tasks/verify_native.yml").read_text(encoding="utf-8")
    assert "verify_config_contract.yml" in (ROLE / "tasks/verify_docker.yml").read_text(encoding="utf-8")


def test_singbox_preflight_is_read_only_and_fail_closed() -> None:
    text = (ROLE / "tasks/preflight.yml").read_text(encoding="utf-8")
    assert "changed_when: false" in text
    assert "failed_when: false" in text
    assert "singbox_effective_mode != 'native' or singbox_preflight_version.rc == 0" in text


def test_generated_client_profile_is_idempotent() -> None:
    template = (ROLE / "templates/singbox_client_profile.yaml.j2").read_text(encoding="utf-8")
    assert "now()" not in template
    assert "生成时间" not in template


def test_native_singbox_rollback_skips_docker_container_removal() -> None:
    text = (ROLE.parent / "docker_apps/tasks/rollback.yml").read_text(encoding="utf-8")
    assert "docker_apps_singbox_deploy_mode" in text
    assert "singbox_deploy_mode" in text
    assert "rollback_docker_app_name == 'singbox'" in text


def test_singbox_rollback_resolves_effective_mode() -> None:
    rollback = (ROLE / "tasks/rollback.yml").read_text(encoding="utf-8")
    verify = (ROLE / "tasks/rollback_verify.yml").read_text(encoding="utf-8")
    assert "import_tasks: resolve.yml" in rollback
    assert "import_tasks: resolve.yml" in verify
