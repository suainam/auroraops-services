from __future__ import annotations

from pathlib import Path

ROLE = Path(__file__).resolve().parents[2] / "collections/ansible_collections/vps/services/roles/singbox"


def read(relative: str) -> str:
    return (ROLE / relative).read_text(encoding="utf-8")


def test_unified_singbox_role_structure() -> None:
    assert (ROLE / "meta/main.yml").exists()
    assert (ROLE / "defaults/main.yml").exists()
    assert (ROLE / "handlers/main.yml").exists()
    assert (ROLE / "tasks/main.yml").exists()
    assert (ROLE / "tasks/resolve.yml").exists()
    assert (ROLE / "tasks/common_prep.yml").exists()
    assert (ROLE / "tasks/configure_common.yml").exists()
    assert (ROLE / "tasks/docker.yml").exists()
    assert (ROLE / "tasks/native.yml").exists()
    assert (ROLE / "tasks/verify.yml").exists()
    assert (ROLE / "tasks/verify_docker.yml").exists()
    assert (ROLE / "tasks/verify_native.yml").exists()


def test_fail_closed_mode_resolution() -> None:
    resolve = read("tasks/resolve.yml")
    assert "singbox_effective_mode" in resolve
    assert "singbox_effective_mode in ['native', 'docker']" in resolve


def test_shared_templates_coexist_in_unified_role() -> None:
    templates = ROLE / "templates"
    for expected in (
        "base.json.j2",
        "outbounds_direct.json.j2",
        "dns.json.j2",
        "inbounds_direct.json.j2",
        "route_direct.json.j2",
        "06_wireguard.json.j2",
        "singbox_provider_profile.yaml.j2",
    ):
        assert (templates / expected).exists(), f"Missing template {expected}"


def test_wireguard_endpoint_inbound_is_strictly_system_mode_guarded() -> None:
    wg_template = read("templates/06_wireguard.json.j2")
    assert "singbox_wireguard_system | default(false) | bool" in wg_template
    assert "singbox_wireguard_http_inbound | default(false) | bool" in wg_template

def test_reality_public_key_fallback_handles_empty_inventory_override() -> None:
    import re
    import yaml
    from jinja2 import Environment

    env = Environment()
    env.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes", "on") if not isinstance(v, bool) else v
    env.tests["search"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    env.tests["regex"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    env.filters["to_json"] = lambda v: '""'
    env.globals["now"] = lambda: "2026-09-27T00:00:00Z"
    context = {
        "singbox_nodes": [
            {
                "name": "vless-aws",
                "type": "vless",
                "uuid": "test-uuid",
                "port": 30052,
                "sni": "aws.amazon.com",
                "reality": True,
            }
        ],
        "singbox_reality_public_key": "",
        "singbox_reality_public_key_generated": "SIMULATED_GEN_KEY",
        "singbox_domain": "handclap6764.suai.eu.org",
        "singbox_sub_token": "token",
        "singbox_reality_short_ids": ["8b1ec27f"],
        "docker_apps_country_flags": {"UNKNOWN": "🌍"},
        "auroraops_roles": {"services": {"ip2free_gateway": False}},
    }

    provider_tpl = env.from_string(read("templates/singbox_provider_profile.yaml.j2"))
    provider_out = yaml.safe_load(provider_tpl.render(context))
    assert provider_out["proxies"][0]["reality-opts"]["public-key"] == "SIMULATED_GEN_KEY"

    client_tpl = env.from_string(read("templates/singbox_client_profile.yaml.j2"))
    client_out = yaml.safe_load(client_tpl.render(context))
    assert client_out["proxies"][0]["reality-opts"]["public-key"] == "SIMULATED_GEN_KEY"
