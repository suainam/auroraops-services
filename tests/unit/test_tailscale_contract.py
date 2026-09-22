from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "collections/ansible_collections/vps/services/roles/tailscale"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_tailscale_role_supports_systemd_and_openrc() -> None:
    main = read("tasks/main.yml")
    verify = read("tasks/verify.yml")

    assert "ansible_os_family in ['Debian', 'Alpine']" in main
    assert "tailscale_service_manager == 'systemd'" in main
    assert "tailscale_service_manager == 'openrc'" in main
    assert "rc-service {{ tailscale_openrc_service_name }} status" in verify


def test_tailscale_role_redacts_auth_and_preserves_state_on_rollback() -> None:
    main = read("tasks/main.yml")
    rollback = read("tasks/rollback.yml")

    assert "tailscale_auth_key" in main
    assert "no_log: true" in main
    assert "tailscale_preserve_state_on_rollback" in rollback
    assert "state_dir" in rollback
