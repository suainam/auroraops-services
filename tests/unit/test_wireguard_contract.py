from __future__ import annotations

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/wireguard_native"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_wireguard_role_declares_parameters_and_defaults() -> None:
    defaults = read("defaults/main.yml")

    assert "wireguard_native_enabled: false" in defaults
    assert "wireguard_native_interface: \"wg0\"" in defaults
    assert "wireguard_native_port: 30059" in defaults
    assert "wireguard_native_peers: []" in defaults
    assert "wireguard_native_private_key: \"\"" in defaults


def test_wireguard_role_has_full_lifecycle_tasks() -> None:
    main = read("tasks/main.yml")
    verify = read("tasks/verify.yml")
    rollback = read("tasks/rollback.yml")
    rollback_verify = read("tasks/rollback_verify.yml")

    assert "wireguard-tools" in main
    assert "wg-quick@" in main
    assert "wg show" in verify
    assert "ActiveState == 'active'" in verify
    assert "state: stopped" in rollback
    assert "ActiveState | default('inactive') != 'active'" in rollback_verify


def test_wireguard_template_renders_interface_and_peers() -> None:
    template = read("templates/wg.conf.j2")

    assert "[Interface]" in template
    assert "Address = {{ wireguard_native_address }}" in template
    assert "PrivateKey = {{ wireguard_native_private_key }}" in template
    assert "[Peer]" in template
    assert "PublicKey = {{ peer.public_key }}" in template
    assert "AllowedIPs = {{ peer.allowed_ips }}" in template
    assert "Endpoint = {{ peer.endpoint }}" in template
