from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/singbox"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_native_singbox_owns_wireguard_endpoint_and_openrc_lifecycle() -> None:
    configure = read("tasks/configure_common.yml")
    native_service = read("tasks/native.yml")

    assert "singbox_wireguard_enabled | default(false) | bool" in configure
    assert "06_wireguard.json.j2" in configure
    assert "state: started" in native_service
    assert "name: sing-box" in native_service
    assert "SINGBOX_CONFIG={{ singbox_native_config_dir }}" in native_service

def test_wireguard_endpoint_is_userspace_safe_for_alpine() -> None:
    template = read("templates/06_wireguard.json.j2")

    assert '"type": "wireguard"' in template
    assert '"system": {{ singbox_wireguard_system | default(false) | lower }}' in template
    assert "persistent_keepalive_interval" in template
    assert "singbox_wireguard_http_inbound" in template
    assert '"listen": "{{ singbox_wireguard_address.split(\'/\')[0] }}"' in template

def test_native_singbox_verify_does_not_require_docker_for_alpine() -> None:
    verify_native = read("tasks/verify_native.yml")
    assert "rc-service sing-box status" in verify_native
    assert "docker_container_info" not in verify_native
