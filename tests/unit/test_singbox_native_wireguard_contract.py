from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/docker_apps"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_native_singbox_owns_wireguard_endpoint_and_openrc_lifecycle() -> None:
    tasks = read("tasks/singbox.yml")
    native_service = read("tasks/singbox_native_service.yml")

    assert "singbox_wireguard_enabled | default(false) | bool" in tasks
    assert "06_wireguard.json.j2" in tasks
    assert "state: started" in native_service
    assert "name: sing-box" in native_service
    assert "SINGBOX_CONFIG=/etc/sing-box" in native_service


def test_wireguard_endpoint_is_userspace_safe_for_alpine() -> None:
    template = read("templates/singbox/06_wireguard.json.j2")

    assert '"type": "wireguard"' in template
    assert '"system": {{ singbox_wireguard_system | default(false) | lower }}' in template
    assert "persistent_keepalive_interval" in template
    assert "singbox_wireguard_http_inbound" in template
    assert '"listen": "{{ singbox_wireguard_address.split(\'/\')[0] }}"' in template


def test_native_singbox_verify_does_not_require_docker_for_alpine() -> None:
    verify = read("tasks/verify.yml")

    native_block = verify.split(
        "- name: Verify Sing-box native service is active and enabled", 1
    )[1].split("- name: Build expected container running state map", 1)[0]
    assert "(docker_apps_singbox_deploy_mode | default('docker')) == 'native'" in native_block
    assert "docker_container_info" not in native_block
