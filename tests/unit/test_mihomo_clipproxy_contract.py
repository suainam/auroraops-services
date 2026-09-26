from pathlib import Path

import yaml


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


def test_cliproxyapi_routes_through_mihomo_and_has_no_legacy_gateway():
    """CLIProxyAPI's outbound goes through mihomo, and there is no second path.

    The previous version asserted

        cliproxyapi_proxy_url: "{{ cliproxyapi_proxy_url }}"

    which is a self-referential definition and would be a circular reference if it
    were real. The two variable names were transposed: the alias that exists is
    `cliproxyapi_native_proxy_url`, deriving from `cliproxyapi_proxy_url`. The test
    therefore failed on origin/main for as long as the role has been unified, and
    being a pre-existing failure it was carried along rather than read.

    Asserting that one string was weak anyway. The property that matters is the
    link between two roles, so that is what is checked: the proxy URL must resolve
    to where mihomo actually listens, and it must be *consumed* by the config
    template. A value pointing at the right port that nothing reads would satisfy
    the original assertion and route nothing.
    """
    defaults_text = (CLIPROXY / "defaults/main.yml").read_text(encoding="utf-8")
    service = (CLIPROXY / "templates/cliproxyapi-native.service.j2").read_text(encoding="utf-8")
    mihomo_defaults = yaml.safe_load(
        (MIHOMO / "defaults/main.yml").read_text(encoding="utf-8")
    )
    defaults = yaml.safe_load(defaults_text)
    expected = f"http://{mihomo_defaults['mihomo_native_mixed_host']}:{mihomo_defaults['mihomo_native_mixed_port']}"

    assert defaults["cliproxyapi_proxy_url"] == expected, (
        "CLIProxyAPI's proxy URL must point at mihomo's mixed listener; mihomo "
        f"listens on {expected} and CLIProxyAPI is set to "
        f"{defaults['cliproxyapi_proxy_url']}"
    )
    assert defaults["cliproxyapi_download_proxy"] == expected

    # And it has to be read, or the value above routes nothing.
    for template in (
        CLIPROXY / "templates/cliproxyapi_config.yaml.j2",
        CLIPROXY / "templates/cliproxyapi_config_native.yaml.j2",
    ):
        assert "cliproxyapi_proxy_url" in template.read_text(encoding="utf-8"), (
            f"{template.name} does not consume the proxy URL, so the value above "
            "is decorative and CLIProxyAPI's outbound does not go through mihomo"
        )

    # The alias the original test meant to check, names the right way round.
    assert defaults["cliproxyapi_native_proxy_url"] == "{{ cliproxyapi_proxy_url }}"
    assert defaults["cliproxyapi_native_download_proxy"] == "{{ cliproxyapi_download_proxy }}"

    # No second egress path.
    assert "mihomo-native.service" in service
    assert "transparent-gateway.service" not in service
    assert "hysteria2-native.service" not in service
    assert "12346" not in defaults_text, (
        "12346 belonged to the retired legacy gateway; if it reappears the "
        "outbound has a path that bypasses mihomo"
    )


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
