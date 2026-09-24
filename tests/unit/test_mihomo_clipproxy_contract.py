from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "collections/ansible_collections/vps/services/roles"
MIHOMO = SERVICES / "mihomo_native"
CLIPROXY = SERVICES / "cliproxyapi"


def test_mihomo_role_owns_loopback_profile_and_controller_bootstrap():
    defaults = (MIHOMO / "defaults/main.yml").read_text(encoding="utf-8")
    configure = (MIHOMO / "tasks/configure.yml").read_text(encoding="utf-8")
    service = (MIHOMO / "templates/mihomo-native.service.j2").read_text(encoding="utf-8")

    assert 'mihomo_native_version: "v1.19.31"' in defaults
    assert 'mihomo_native_mixed_host: "127.0.0.1"' in defaults
    assert 'mihomo_native_mixed_port: 7890' in defaults
    assert "mihomo_native_profile_use_controller_staging" in defaults
    assert "Download complete Sub-Store Mihomo profile on controller" in configure
    assert "-t" in configure
    assert "-d {{ mihomo_native_install_dir }}" in service
    assert "-f {{ mihomo_native_profile_path }}" in service


def test_generated_playbook_orders_mihomo_before_cliproxyapi():
    playbook = (ROOT / "playbooks/services/deploy.yml").read_text(encoding="utf-8")
    assert "vps.services.mihomo_native" in playbook
    assert "vps.services.cliproxyapi" in playbook
    assert playbook.index("vps.services.mihomo_native") < playbook.index(
        "vps.services.cliproxyapi"
    )


def test_roles_have_dedicated_rollback_verification():
    for role in (MIHOMO, CLIPROXY):
        path = role / "tasks/rollback_verify.yml"
        assert path.is_file()
        assert "rollback_verify" in path.read_text(encoding="utf-8")


def test_mihomo_rollback_verification_checks_systemd_load_state():
    rollback_verify = (MIHOMO / "tasks/rollback_verify.yml").read_text(encoding="utf-8")

    assert "ansible.builtin.systemd:" in rollback_verify
    assert "LoadState" in rollback_verify
    assert "default('not-found') == 'not-found'" in rollback_verify
